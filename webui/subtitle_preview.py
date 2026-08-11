import os
import re

import streamlit as st
from loguru import logger
from PIL import Image, ImageDraw, ImageFont

from app.models.schema import VideoAspect
from app.services import video


def _ui_text(ui_language: str, chinese: str, english: str) -> str:
    language = str(ui_language or "").lower()
    return chinese if language.startswith("zh") else english


def _normalize_color(value, fallback="#000000") -> str:
    value = str(value or "").strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        return value
    return fallback


def _resolve_video_size(params) -> tuple[int, int]:
    try:
        aspect = VideoAspect(params.video_aspect)
    except Exception:
        aspect = VideoAspect.portrait
    return aspect.to_resolution()


def build_subtitle_preview_image(params, preview_text: str, font_dir: str) -> Image.Image:
    """按成片分辨率和字幕布局规则生成一张静态预览图。"""
    video_width, video_height = _resolve_video_size(params)

    # 中性背景只帮助观察字幕，不参与最终视频。参考线对应 top/center/bottom
    # 的关键纵向位置，方便自定义位置时判断字幕所处区域。
    image = Image.new("RGB", (video_width, video_height), (38, 42, 48))
    canvas = ImageDraw.Draw(image)
    grid_step = max(80, int(min(video_width, video_height) * 0.08))
    for x in range(0, video_width, grid_step):
        canvas.line((x, 0, x, video_height), fill=(48, 53, 60), width=1)
    for y in range(0, video_height, grid_step):
        canvas.line((0, y, video_width, y), fill=(48, 53, 60), width=1)
    for ratio in (0.05, 0.5, 0.95):
        y = int(round(video_height * ratio))
        canvas.line((0, y, video_width, y), fill=(82, 89, 99), width=2)

    preview_text = str(preview_text or "").strip()
    if not getattr(params, "subtitle_enabled", True) or not preview_text:
        return image

    font_size = max(1, int(getattr(params, "font_size", 60) or 60))
    stroke_width = max(0, int(float(getattr(params, "stroke_width", 0) or 0)))
    font_path = os.path.join(font_dir, str(getattr(params, "font_name", "") or ""))
    try:
        font = ImageFont.truetype(font_path, font_size)
    except Exception as exc:
        logger.warning(f"failed to load subtitle preview font: {font_path}, {exc}")
        return image

    raw_background = getattr(params, "text_background_color", False)
    if isinstance(raw_background, bool):
        background_color = "#000000" if raw_background else None
    else:
        background_color = str(raw_background or "").strip() or None

    rounded_background = bool(
        getattr(params, "rounded_subtitle_background", False) and background_color
    )
    max_width = video_width * 0.9
    padding_ratio = 0.4 if rounded_background else 0.6
    pad_x = int(font_size * padding_ratio) if background_color else 0
    text_max_width = max(1, int(max_width) - 2 * pad_x)

    # 直接复用正式视频服务的换行算法，避免中文长句、英文长词在预览和成片中
    # 产生不同的换行结果。
    wrapped_text, text_height = video.wrap_text(
        preview_text,
        max_width=text_max_width,
        font=font_path,
        fontsize=font_size,
    )
    interline = int(font_size * 0.25)
    line_count = wrapped_text.count("\n") + 1
    vertical_padding = int(font_size * 0.35)
    text_clip_margin_y = max(int(font_size * 0.3), int(stroke_width * 2))
    clip_height = int(text_height + vertical_padding + interline * line_count)

    # 圆角背景在正式渲染中按真实文字宽度收缩；普通矩形背景则保持 90% 画宽。
    if rounded_background:
        try:
            measured_text_width = max(
                int(font.getbbox(line)[2] - font.getbbox(line)[0])
                for line in wrapped_text.split("\n")
                if line
            )
        except Exception as exc:
            logger.debug(f"failed to measure subtitle preview width: {exc}")
            measured_text_width = int(max_width)
        clip_width = max(1, min(int(max_width), measured_text_width + 2 * pad_x))
    else:
        clip_width = int(max_width)

    text_color = _normalize_color(
        getattr(params, "text_fore_color", "#FFFFFF"), "#FFFFFF"
    )
    stroke_color = _normalize_color(
        getattr(params, "stroke_color", "#000000"), "#000000"
    )

    # PIL 与 MoviePy 对字体 baseline 的透明画布处理略有不同，因此这里同样按
    # 可见字形 bbox 居中，让预览更接近正式字幕背景中的视觉中心。
    measure_layer = Image.new(
        "RGBA", (clip_width, max(1, clip_height)), (0, 0, 0, 0)
    )
    measure_draw = ImageDraw.Draw(measure_layer)
    text_bbox = measure_draw.multiline_textbbox(
        (0, 0),
        wrapped_text,
        font=font,
        spacing=interline,
        align="center",
        stroke_width=stroke_width,
    )
    visible_height = text_bbox[3] - text_bbox[1]
    if background_color:
        clip_height = max(clip_height, visible_height + 2 * text_clip_margin_y)

    subtitle_layer = Image.new("RGBA", (clip_width, clip_height), (0, 0, 0, 0))
    subtitle_draw = ImageDraw.Draw(subtitle_layer)
    if background_color:
        fill = _normalize_color(background_color)
        if rounded_background:
            radius = max(8, int(font_size * 0.4))
            rgba = (*tuple(int(fill[i : i + 2], 16) for i in (1, 3, 5)), 140)
            subtitle_draw.rounded_rectangle(
                (0, 0, clip_width - 1, clip_height - 1),
                radius=radius,
                fill=rgba,
            )
        else:
            subtitle_draw.rectangle(
                (0, 0, clip_width - 1, clip_height - 1),
                fill=fill,
            )

    text_bbox = subtitle_draw.multiline_textbbox(
        (0, 0),
        wrapped_text,
        font=font,
        spacing=interline,
        align="center",
        stroke_width=stroke_width,
    )
    visible_width = text_bbox[2] - text_bbox[0]
    visible_height = text_bbox[3] - text_bbox[1]
    text_x = (clip_width - visible_width) / 2 - text_bbox[0]
    text_y = (clip_height - visible_height) / 2 - text_bbox[1]
    subtitle_draw.multiline_text(
        (text_x, text_y),
        wrapped_text,
        font=font,
        fill=text_color,
        spacing=interline,
        align="center",
        stroke_width=stroke_width,
        stroke_fill=stroke_color,
    )

    # 与 app.services.video.generate_video 中 create_text_clip 的定位规则保持一致。
    position = str(getattr(params, "subtitle_position", "bottom") or "bottom")
    if position == "bottom":
        y = video_height * 0.95 - clip_height
    elif position == "top":
        y = video_height * 0.05
    elif position == "custom":
        margin = 10
        max_y = video_height - clip_height - margin
        min_y = margin
        custom_position = float(getattr(params, "custom_position", 70.0) or 70.0)
        custom_y = (video_height - clip_height) * (custom_position / 100.0)
        y = max(min_y, min(custom_y, max_y))
    else:
        y = (video_height - clip_height) / 2

    x = (video_width - clip_width) / 2
    image.paste(subtitle_layer, (int(round(x)), int(round(y))), subtitle_layer)
    return image


def render_subtitle_preview(params, font_dir: str, ui_language: str) -> None:
    """在字幕设置面板底部渲染与当前控件实时联动的静态预览。"""
    st.divider()
    st.markdown(f"**{_ui_text(ui_language, '字幕预览', 'Subtitle Preview')}**")

    source_text = re.sub(
        r"\s+",
        " ",
        str(
            getattr(params, "video_script", "")
            or getattr(params, "video_subject", "")
            or ""
        ),
    ).strip()
    default_text = (
        source_text[:80]
        if source_text
        else _ui_text(
            ui_language,
            "这是一段字幕预览文字",
            "This is a subtitle preview",
        )
    )
    st.session_state.setdefault("subtitle_preview_text_input", default_text)
    preview_text = st.text_input(
        _ui_text(ui_language, "预览文字", "Preview text"),
        key="subtitle_preview_text_input",
        disabled=not getattr(params, "subtitle_enabled", True),
    )

    try:
        preview_image = build_subtitle_preview_image(params, preview_text, font_dir)
        st.image(preview_image, use_container_width=True)
        width, height = _resolve_video_size(params)
        st.caption(
            _ui_text(
                ui_language,
                f"按最终视频 {width} × {height} 的真实坐标渲染，页面中仅等比缩小显示。",
                f"Rendered at the final {width} × {height} video coordinates and only scaled down in the page.",
            )
        )
    except Exception as exc:
        logger.warning(f"failed to render subtitle preview: {exc}")
        st.caption(
            _ui_text(
                ui_language,
                "当前字幕预览暂不可用，但不会影响视频生成。",
                "Subtitle preview is currently unavailable; video generation is unaffected.",
            )
        )
