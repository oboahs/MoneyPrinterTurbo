from __future__ import annotations

import os
from collections.abc import Mapping

import streamlit as st
from loguru import logger

from app.config import config
from app.models import const
from app.services import state as sm
from app.services.social_auto_upload import social_auto_upload_service


BROWSER_PLATFORMS = [
    ("douyin", "抖音 / Douyin"),
    ("xiaohongshu", "小红书 / Xiaohongshu"),
    ("kuaishou", "快手 / Kuaishou"),
    ("bilibili", "哔哩哔哩 / Bilibili"),
    ("tencent", "视频号 / WeChat Channels"),
]
UPLOAD_POST_PLATFORMS = [
    ("tiktok", "TikTok"),
    ("instagram", "Instagram"),
    ("youtube", "YouTube Shorts"),
]
PLATFORM_LABELS = dict(BROWSER_PLATFORMS + UPLOAD_POST_PLATFORMS)


st.set_page_config(
    page_title="社交平台发布 · MoneyPrinterTurbo",
    page_icon="📤",
    layout="wide",
)


def _is_english() -> bool:
    language = str(
        st.session_state.get("ui_language") or config.ui.get("language", "") or ""
    ).lower()
    return language.startswith("en")


def _t(zh: str, en: str) -> str:
    return en if _is_english() else zh


def _snapshot() -> dict:
    try:
        return config.snapshot_config_with_pending(config.app)
    except Exception:
        return dict(config.app)


def _set_app_config(key: str, value) -> bool:
    updated = config.update_config_nonblocking(config.app, key, value)
    if not updated:
        logger.debug(f"deferred social publishing config update: key={key}")
    return updated


def _save_config() -> bool:
    saved = config.try_save_config()
    if not saved:
        logger.debug("deferred social publishing config save until active task completes")
    return saved


def _normalize_list(value) -> list[str]:
    if isinstance(value, str):
        value = value.split(",")
    return [str(item).strip() for item in (value or []) if str(item).strip()]


def _short(value, limit=120) -> str:
    text = str(value or "").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}…"


def _collect_result_platforms(value) -> set[str]:
    platforms: set[str] = set()
    if isinstance(value, Mapping):
        platform = str(value.get("platform") or "").strip().lower()
        if platform:
            platforms.add(platform)
        for item in value.get("platforms") or []:
            normalized = str(item or "").strip().lower()
            if normalized:
                platforms.add(normalized)
        for nested in value.get("results") or []:
            platforms.update(_collect_result_platforms(nested))
    elif isinstance(value, list):
        for item in value:
            platforms.update(_collect_result_platforms(item))
    return platforms


def _cross_post_state_label(state: str | None) -> str:
    return {
        const.CROSS_POST_STATE_PENDING: _t("等待发布", "Pending"),
        const.CROSS_POST_STATE_PROCESSING: _t("发布中", "Publishing"),
        const.CROSS_POST_STATE_COMPLETE: _t("发布成功", "Complete"),
        const.CROSS_POST_STATE_FAILED: _t("发布失败", "Failed"),
    }.get(state, _t("未发布", "Not published"))


def _render_header(snapshot: dict) -> None:
    st.title(_t("社交平台发布", "Social publishing"))
    st.caption(
        _t(
            "在这里统一配置生成后自动发布、检查账号登录状态，并查看最近的发布任务。视频生成成功后，发布会在后台执行；平台上传失败不会让已生成的视频任务失败。",
            "Configure automatic publishing, validate account sessions, and review recent publishing jobs here. Publishing runs in the background after video generation; an upload failure does not invalidate the generated video.",
        )
    )

    browser_platforms = _normalize_list(
        snapshot.get("social_auto_upload_platforms", [])
    )
    upload_post_platforms = _normalize_list(snapshot.get("upload_post_platforms", []))
    browser_active = bool(
        snapshot.get("social_auto_upload_enabled", False)
        and snapshot.get("social_auto_upload_auto_upload", False)
        and browser_platforms
    )
    api_active = bool(
        snapshot.get("upload_post_enabled", False)
        and snapshot.get("upload_post_auto_upload", False)
        and upload_post_platforms
        and snapshot.get("upload_post_api_key", "")
        and snapshot.get("upload_post_username", "")
    )
    active_platforms = []
    if browser_active:
        active_platforms.extend(browser_platforms)
    if api_active:
        active_platforms.extend(upload_post_platforms)

    runtime = social_auto_upload_service.runtime_status()
    metric_cols = st.columns(4)
    metric_cols[0].metric(
        _t("自动发布", "Auto publish"),
        _t("已开启", "Enabled") if (browser_active or api_active) else _t("未开启", "Disabled"),
    )
    metric_cols[1].metric(
        _t("已选平台", "Selected platforms"),
        len(set(active_platforms)),
    )
    metric_cols[2].metric(
        _t("浏览器发布环境", "Browser uploader"),
        _t("就绪", "Ready") if runtime.get("ready") else _t("未就绪", "Not ready"),
    )
    metric_cols[3].metric(
        "Upload-Post",
        _t("已配置", "Configured")
        if snapshot.get("upload_post_api_key") and snapshot.get("upload_post_username")
        else _t("未配置", "Not configured"),
    )


def _render_browser_provider(snapshot: dict) -> None:
    st.subheader(_t("国内平台 · 浏览器自动发布", "Browser-based publishing"))
    st.caption(
        _t(
            "抖音、小红书、快手、B站和视频号使用 social-auto-upload + Patchright 浏览器自动化。账号登录态保存在 NAS 的持久化 cookies 目录中。",
            "Douyin, Xiaohongshu, Kuaishou, Bilibili, and WeChat Channels use social-auto-upload with Patchright browser automation. Login sessions are persisted in the NAS cookies directory.",
        )
    )

    enabled_col, auto_col = st.columns(2)
    enabled = enabled_col.checkbox(
        _t("启用浏览器发布", "Enable browser publishing"),
        value=bool(snapshot.get("social_auto_upload_enabled", False)),
        key="social_publish_browser_enabled",
    )
    auto_upload = auto_col.checkbox(
        _t("视频生成后自动发布", "Publish automatically after generation"),
        value=bool(snapshot.get("social_auto_upload_auto_upload", False)),
        key="social_publish_browser_auto",
        disabled=not enabled,
    )
    _set_app_config("social_auto_upload_enabled", enabled)
    _set_app_config("social_auto_upload_auto_upload", auto_upload if enabled else False)

    valid_platform_ids = [platform for platform, _ in BROWSER_PLATFORMS]
    saved_platforms = [
        platform
        for platform in _normalize_list(snapshot.get("social_auto_upload_platforms", []))
        if platform in valid_platform_ids
    ]
    selected_platforms = st.multiselect(
        _t("自动发布平台", "Auto-publish platforms"),
        options=valid_platform_ids,
        default=saved_platforms,
        format_func=lambda platform: PLATFORM_LABELS.get(platform, platform),
        key="social_publish_browser_platforms",
        disabled=not enabled,
    )
    _set_app_config("social_auto_upload_platforms", selected_platforms if enabled else [])

    raw_accounts = snapshot.get("social_auto_upload_accounts", {}) or {}
    accounts = dict(raw_accounts) if isinstance(raw_accounts, Mapping) else {}
    default_account = st.text_input(
        _t("默认账号别名", "Default account alias"),
        value=str(snapshot.get("social_auto_upload_default_account", "") or ""),
        key="social_publish_default_account",
        help=_t(
            "某个平台没有单独填写账号时使用。账号别名对应 social-auto-upload 的 cookie 文件。",
            "Used when a selected platform has no platform-specific account alias. The alias maps to a social-auto-upload cookie file.",
        ),
        disabled=not enabled,
    ).strip()
    _set_app_config("social_auto_upload_default_account", default_account)

    if selected_platforms:
        st.markdown(f"**{_t('平台账号', 'Platform accounts')}**")
        account_columns = st.columns(2)
        updated_accounts = dict(accounts)
        for index, platform in enumerate(selected_platforms):
            account_value = account_columns[index % 2].text_input(
                PLATFORM_LABELS.get(platform, platform),
                value=str(accounts.get(platform, "") or ""),
                key=f"social_publish_account_{platform}",
                placeholder=default_account or "creator",
                disabled=not enabled,
            ).strip()
            if account_value:
                updated_accounts[platform] = account_value
            else:
                updated_accounts.pop(platform, None)
        _set_app_config("social_auto_upload_accounts", updated_accounts)

        missing_accounts = [
            platform
            for platform in selected_platforms
            if not updated_accounts.get(platform) and not default_account
        ]
        if auto_upload and missing_accounts:
            st.warning(
                _t("以下平台尚未配置账号：", "Accounts are missing for: ")
                + "、".join(PLATFORM_LABELS.get(item, item) for item in missing_accounts)
            )
    else:
        _set_app_config("social_auto_upload_accounts", accounts)

    tags = st.text_input(
        _t("默认标签", "Default tags"),
        value=", ".join(_normalize_list(snapshot.get("social_auto_upload_tags", []))),
        key="social_publish_tags",
        placeholder="AI, 科普",
        disabled=not enabled,
    )
    _set_app_config(
        "social_auto_upload_tags",
        [tag.strip().lstrip("#") for tag in tags.split(",") if tag.strip()],
    )

    description = st.text_area(
        _t("默认发布说明", "Default description"),
        value=str(snapshot.get("social_auto_upload_description", "") or ""),
        key="social_publish_description",
        height=90,
        help=_t(
            "留空时会使用视频主题作为说明。",
            "If left empty, the video subject is used as the description.",
        ),
        disabled=not enabled,
    ).strip()
    _set_app_config("social_auto_upload_description", description)

    with st.expander(_t("高级设置", "Advanced settings"), expanded=False):
        advanced_cols = st.columns(3)
        bilibili_tid = advanced_cols[0].number_input(
            "Bilibili TID",
            min_value=1,
            max_value=99999,
            value=int(snapshot.get("social_auto_upload_bilibili_tid", 249) or 249),
            step=1,
            key="social_publish_bilibili_tid",
            disabled=not enabled,
        )
        timeout = advanced_cols[1].number_input(
            _t("单个平台超时（秒）", "Per-platform timeout (seconds)"),
            min_value=60,
            max_value=3600,
            value=max(60, int(snapshot.get("social_auto_upload_timeout", 900) or 900)),
            step=30,
            key="social_publish_timeout",
            disabled=not enabled,
        )
        headless = advanced_cols[2].checkbox(
            _t("无头浏览器", "Headless browser"),
            value=bool(snapshot.get("social_auto_upload_headless", True)),
            key="social_publish_headless",
            disabled=not enabled,
        )
        _set_app_config("social_auto_upload_bilibili_tid", int(bilibili_tid))
        _set_app_config("social_auto_upload_timeout", int(timeout))
        _set_app_config("social_auto_upload_headless", bool(headless))

        command = st.text_input(
            _t("CLI 命令", "CLI command"),
            value=str(snapshot.get("social_auto_upload_command", "sau") or "sau"),
            key="social_publish_command",
            disabled=not enabled,
        ).strip()
        workdir = st.text_input(
            _t("运行目录", "Working directory"),
            value=str(
                snapshot.get("social_auto_upload_workdir", "/opt/social-auto-upload")
                or "/opt/social-auto-upload"
            ),
            key="social_publish_workdir",
            disabled=not enabled,
        ).strip()
        _set_app_config("social_auto_upload_command", command or "sau")
        _set_app_config("social_auto_upload_workdir", workdir or "/opt/social-auto-upload")


def _render_upload_post_provider(snapshot: dict) -> None:
    st.subheader(_t("海外平台 · Upload-Post API", "Upload-Post API"))
    st.caption(
        _t(
            "TikTok、Instagram 和 YouTube Shorts 继续使用 Upload-Post API，与国内平台浏览器发布可以同时开启。",
            "TikTok, Instagram, and YouTube Shorts continue to use the Upload-Post API and can run alongside browser-based publishing.",
        )
    )

    enabled_col, auto_col = st.columns(2)
    enabled = enabled_col.checkbox(
        _t("启用 Upload-Post", "Enable Upload-Post"),
        value=bool(snapshot.get("upload_post_enabled", False)),
        key="social_publish_upload_post_enabled",
    )
    auto_upload = auto_col.checkbox(
        _t("视频生成后自动发布", "Publish automatically after generation"),
        value=bool(snapshot.get("upload_post_auto_upload", False)),
        key="social_publish_upload_post_auto",
        disabled=not enabled,
    )
    _set_app_config("upload_post_enabled", enabled)
    _set_app_config("upload_post_auto_upload", auto_upload if enabled else False)

    credential_cols = st.columns(2)
    username = credential_cols[0].text_input(
        _t("Upload-Post 用户名", "Upload-Post username"),
        value=str(snapshot.get("upload_post_username", "") or ""),
        key="social_publish_upload_post_username",
        disabled=not enabled,
    ).strip()
    api_key = credential_cols[1].text_input(
        "Upload-Post API Key",
        value=str(snapshot.get("upload_post_api_key", "") or ""),
        type="password",
        key="social_publish_upload_post_api_key",
        disabled=not enabled,
    ).strip()
    _set_app_config("upload_post_username", username)
    _set_app_config("upload_post_api_key", api_key)

    valid_platform_ids = [platform for platform, _ in UPLOAD_POST_PLATFORMS]
    saved_platforms = [
        platform
        for platform in _normalize_list(snapshot.get("upload_post_platforms", []))
        if platform in valid_platform_ids
    ]
    selected_platforms = st.multiselect(
        _t("自动发布平台", "Auto-publish platforms"),
        options=valid_platform_ids,
        default=saved_platforms or ["tiktok", "instagram"],
        format_func=lambda platform: PLATFORM_LABELS.get(platform, platform),
        key="social_publish_upload_post_platforms",
        disabled=not enabled,
    )
    _set_app_config("upload_post_platforms", selected_platforms if enabled else [])

    privacy = st.selectbox(
        _t("YouTube 可见性", "YouTube visibility"),
        options=["public", "unlisted", "private"],
        index=["public", "unlisted", "private"].index(
            str(snapshot.get("upload_post_youtube_privacy_status", "public") or "public")
            if str(snapshot.get("upload_post_youtube_privacy_status", "public") or "public")
            in {"public", "unlisted", "private"}
            else "public"
        ),
        key="social_publish_youtube_privacy",
        disabled=not enabled or "youtube" not in selected_platforms,
    )
    _set_app_config("upload_post_youtube_privacy_status", privacy)

    if enabled and auto_upload and (not username or not api_key):
        st.warning(
            _t(
                "已开启自动发布，但 Upload-Post 用户名或 API Key 尚未填写。",
                "Auto publishing is enabled, but the Upload-Post username or API key is missing.",
            )
        )


def _render_runtime_and_accounts(snapshot: dict) -> None:
    st.subheader(_t("运行环境与账号状态", "Runtime and account status"))
    runtime = social_auto_upload_service.runtime_status()
    runtime_cols = st.columns(4)
    runtime_cols[0].metric(
        "sau CLI",
        _t("可用", "Available") if runtime.get("command") else _t("不可用", "Unavailable"),
    )
    runtime_cols[1].metric(
        _t("Chromium", "Chromium"),
        _t("就绪", "Ready") if runtime.get("browser_ready") else _t("未就绪", "Not ready"),
    )
    runtime_cols[2].metric(
        _t("运行目录", "Working directory"),
        _t("正常", "Ready") if runtime.get("workdir_ready") else _t("缺失", "Missing"),
    )
    runtime_cols[3].metric(
        _t("Cookie 目录", "Cookie directory"),
        _t("正常", "Ready") if runtime.get("cookies_dir_ready") else _t("缺失", "Missing"),
    )

    if not runtime.get("ready"):
        st.warning(
            _t(
                "浏览器发布运行环境未完全就绪。若刚更新代码，请重新构建 Docker 镜像，而不是只重启容器。",
                "The browser publishing runtime is not fully ready. If you just updated the code, rebuild the Docker image instead of only restarting the container.",
            )
        )
        with st.expander(_t("运行环境详情", "Runtime details")):
            st.code(
                "\n".join(
                    [
                        f"command: {runtime.get('command') or runtime.get('configured_command') or '-'}",
                        f"workdir: {runtime.get('workdir') or '-'}",
                        f"cookies: {runtime.get('cookies_dir') or '-'}",
                        f"browser: {runtime.get('browser_root') or '-'}",
                    ]
                ),
                language="text",
            )

    selected_platforms = _normalize_list(
        snapshot.get("social_auto_upload_platforms", [])
    )
    raw_accounts = snapshot.get("social_auto_upload_accounts", {}) or {}
    accounts = dict(raw_accounts) if isinstance(raw_accounts, Mapping) else {}
    default_account = str(snapshot.get("social_auto_upload_default_account", "") or "")

    if not selected_platforms:
        st.info(_t("尚未选择浏览器自动发布平台。", "No browser publishing platforms are selected."))
        return

    st.caption(
        _t(
            "“检查登录”只验证当前 Cookie 是否有效，不会上传任何内容。首次登录或 Cookie 失效时，需要在 NAS 终端中执行下方登录命令并扫码。",
            "Check login only validates the current cookie and does not upload anything. For first-time login or an expired cookie, run the command below in the NAS terminal and scan the QR code.",
        )
    )

    for platform in selected_platforms:
        if platform not in PLATFORM_LABELS:
            continue
        account = str(accounts.get(platform) or default_account or "").strip()
        with st.container(border=True):
            row = st.columns([1.5, 1.3, 1.2, 2.4], vertical_alignment="center")
            row[0].write(f"**{PLATFORM_LABELS[platform]}**")
            row[1].write(account or _t("未配置账号", "No account"))

            status_key = f"social_publish_account_status_{platform}"
            cached_status = st.session_state.get(status_key)
            if cached_status:
                row[2].write(
                    "✅ " + _t("登录有效", "Valid")
                    if cached_status.get("success")
                    else "⚠️ " + _t("需要登录", "Login required")
                )
            else:
                row[2].write(_t("未检查", "Not checked"))

            if row[3].button(
                _t("检查登录", "Check login"),
                key=f"social_publish_check_{platform}",
                use_container_width=True,
                disabled=not bool(account) or not runtime.get("command"),
            ):
                with st.spinner(_t("正在检查登录状态…", "Checking login…")):
                    result = social_auto_upload_service.check_account(platform, account)
                st.session_state[status_key] = result
                st.rerun()

            cached_status = st.session_state.get(status_key)
            if cached_status and not cached_status.get("success"):
                st.caption(
                    _t("检查结果：", "Check result: ")
                    + _short(cached_status.get("error") or cached_status.get("message"), 240)
                )

            if account:
                st.code(
                    f"docker exec -it moneyprinterturbo-webui sau {platform} login --account {account}",
                    language="bash",
                )


@st.fragment(run_every="3s")
def _render_recent_publish_status() -> None:
    st.subheader(_t("最近自动发布状态", "Recent auto-publish status"))
    try:
        tasks, _ = sm.state.get_all_tasks(1, 50)
    except Exception as exc:
        logger.warning(f"failed to load publishing status: {exc}")
        st.warning(_t("暂时无法读取任务状态。", "Publishing status is temporarily unavailable."))
        return

    publish_tasks = [task for task in tasks if task.get("cross_post_state")]
    if not publish_tasks:
        st.info(
            _t(
                "还没有自动发布记录。开启自动发布后，新生成的视频会在这里显示等待、发布中、成功或失败状态。",
                "There are no auto-publishing records yet. New videos will appear here as pending, publishing, complete, or failed after auto publishing is enabled.",
            )
        )
        return

    state_counts = {
        const.CROSS_POST_STATE_PENDING: 0,
        const.CROSS_POST_STATE_PROCESSING: 0,
        const.CROSS_POST_STATE_COMPLETE: 0,
        const.CROSS_POST_STATE_FAILED: 0,
    }
    for task in publish_tasks:
        state = task.get("cross_post_state")
        if state in state_counts:
            state_counts[state] += 1

    metrics = st.columns(4)
    metrics[0].metric(_t("等待", "Pending"), state_counts[const.CROSS_POST_STATE_PENDING])
    metrics[1].metric(_t("发布中", "Publishing"), state_counts[const.CROSS_POST_STATE_PROCESSING])
    metrics[2].metric(_t("成功", "Complete"), state_counts[const.CROSS_POST_STATE_COMPLETE])
    metrics[3].metric(_t("失败", "Failed"), state_counts[const.CROSS_POST_STATE_FAILED])

    rows = []
    for task in publish_tasks[:15]:
        results = task.get("cross_post_results") or []
        platforms = sorted(_collect_result_platforms(results))
        subject = (
            task.get("video_subject")
            or (_short(task.get("script"), 46) if task.get("script") else "")
            or str(task.get("task_id") or "")[:12]
        )
        rows.append(
            {
                _t("状态", "Status"): _cross_post_state_label(task.get("cross_post_state")),
                _t("视频", "Video"): _short(subject, 46),
                _t("平台", "Platforms"): ", ".join(
                    PLATFORM_LABELS.get(platform, platform) for platform in platforms
                )
                or "-",
                _t("错误", "Error"): _short(task.get("cross_post_error"), 90) or "-",
                _t("任务 ID", "Task ID"): str(task.get("task_id") or "")[:12],
            }
        )

    st.dataframe(
        rows,
        hide_index=True,
        use_container_width=True,
    )
    st.caption(_t("状态每 3 秒自动刷新。", "Status refreshes automatically every 3 seconds."))


def _render_page() -> None:
    snapshot = _snapshot()
    _render_header(snapshot)

    provider_tabs = st.tabs(
        [
            _t("国内平台", "Browser platforms"),
            _t("海外平台", "Upload-Post"),
            _t("账号与运行状态", "Accounts & runtime"),
        ],
        key="social_publish_provider_tabs",
        on_change="rerun",
    )

    if provider_tabs[0].open:
        with provider_tabs[0]:
            _render_browser_provider(snapshot)
    elif provider_tabs[1].open:
        with provider_tabs[1]:
            _render_upload_post_provider(snapshot)
    elif provider_tabs[2].open:
        with provider_tabs[2]:
            _render_runtime_and_accounts(snapshot)

    if not _save_config():
        st.caption(
            _t(
                "当前有视频任务正在使用配置；刚修改的发布设置会在任务释放配置后自动保存并对后续任务生效。",
                "A video task is currently using the configuration. Your publishing changes will be saved automatically after it releases the configuration and will apply to subsequent tasks.",
            )
        )

    st.divider()
    _render_recent_publish_status()


_render_page()
