import os
import sys
from pathlib import Path

import streamlit as st

root_dir = str(Path(__file__).resolve().parents[2])
if root_dir in sys.path:
    sys.path.remove(root_dir)
sys.path.insert(0, root_dir)

from app.config import config
from app.services.hardware_acceleration import check_intel_qsv


st.set_page_config(
    page_title="NAS 硬件加速",
    page_icon="⚙️",
    layout="wide",
)


@st.cache_data(ttl=60, show_spinner=False)
def _cached_qsv_check() -> dict:
    return check_intel_qsv().to_dict()


def _yes_no(value: bool) -> str:
    return "✅ 正常" if value else "❌ 异常"


st.title("NAS 硬件加速自检")
st.caption(
    "针对 Intel 核显 / Quick Sync 的运行时检测。这里不仅检查 /dev/dri 和 FFmpeg，"
    "还会实际编码一段约 0.35 秒的测试视频，以确认 MoneyPrinterTurbo 能真正调用 QSV。"
)

refresh_col, info_col = st.columns([1, 4], vertical_alignment="center")
with refresh_col:
    if st.button("重新检测", icon=":material/refresh:", use_container_width=True):
        _cached_qsv_check.clear()
        st.rerun()
with info_col:
    st.caption("检测结果缓存 60 秒；点击“重新检测”可立即重新执行实际编码测试。")

with st.spinner("正在检测 Intel Quick Sync..."):
    result = _cached_qsv_check()

if result["available"]:
    st.success("Intel Quick Sync 可用：MoneyPrinterTurbo 可以使用 h264_qsv 进行硬件 H.264 编码。")
else:
    st.error("Intel Quick Sync 当前不可用：视频生成会有可能回退到 libx264 CPU 编码。")
    if result.get("error"):
        st.warning(result["error"])

configured_codec = result.get("configured_codec") or "libx264"
if configured_codec == "h264_qsv":
    st.info("当前视频编码配置：h264_qsv（Intel Quick Sync）")
else:
    st.warning(
        f"当前视频编码配置为 {configured_codec}，不是 h264_qsv。"
        "如果这是旧部署生成的 config.toml，请在 [app] 中设置 video_codec = \"h264_qsv\"。"
    )

status_cols = st.columns(4)
status_cols[0].metric("/dev/dri", "已映射" if result["dri_present"] else "未映射")
status_cols[1].metric(
    "Render 节点",
    "可访问" if result["render_node_accessible"] else "不可访问",
)
status_cols[2].metric(
    "FFmpeg h264_qsv",
    "已支持" if result["qsv_encoder_present"] else "不支持",
)
status_cols[3].metric(
    "实际 QSV 编码",
    "通过" if result["encode_test_passed"] else "失败",
)

st.subheader("检测明细")
detail_rows = {
    "Docker GPU 设备映射": _yes_no(result["dri_present"]),
    "Render 节点权限": _yes_no(result["render_node_accessible"]),
    "FFmpeg QSV 编码器": _yes_no(result["qsv_encoder_present"]),
    "实际硬件编码测试": _yes_no(result["encode_test_passed"]),
    "Render 节点": result.get("render_node") or "未发现",
    "FFmpeg": result.get("ffmpeg_path") or "未知",
    "LIBVA_DRIVER_NAME": result.get("libva_driver") or "未设置",
    "video_codec": configured_codec,
}
for label, value in detail_rows.items():
    left, right = st.columns([1, 3])
    left.write(f"**{label}**")
    right.code(str(value), language=None)

st.subheader("结果说明")
if result["available"] and configured_codec == "h264_qsv":
    st.write(
        "当前链路完整：Docker 已拿到 Intel 核显设备，FFmpeg 包含 h264_qsv，"
        "实际编码测试成功，并且 MoneyPrinterTurbo 已配置使用 h264_qsv。"
    )
elif result["available"]:
    st.write(
        "QSV 硬件本身可以正常工作，但当前 MoneyPrinterTurbo 配置没有选择 h264_qsv。"
        "修改 config.toml 后重启容器即可。"
    )
else:
    st.write(
        "只有“实际 QSV 编码”通过才代表硬件加速真正可用。仅看到 /dev/dri 或"
        " FFmpeg 列出了 h264_qsv，并不足以证明驱动、权限和运行时链路正常。"
    )

with st.expander("故障排查命令"):
    st.code(
        "docker exec moneyprinterturbo-webui ls -l /dev/dri\n"
        "docker exec moneyprinterturbo-webui ffmpeg -hide_banner -encoders | grep qsv\n"
        "docker exec moneyprinterturbo-webui env | grep LIBVA_DRIVER_NAME",
        language="bash",
    )

st.caption(
    f"运行环境：{'Docker / Container' if config.is_running_in_container() else '非容器'} · "
    f"PID {os.getpid()}"
)
