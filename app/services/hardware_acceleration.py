import os
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from app.config import config
from app.utils import utils


@dataclass(frozen=True)
class QsvCheckResult:
    available: bool
    configured_codec: str
    ffmpeg_path: str
    dri_present: bool
    render_node: str
    render_node_accessible: bool
    qsv_encoder_present: bool
    encode_test_passed: bool
    libva_driver: str
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _find_render_node() -> str:
    dri_dir = Path("/dev/dri")
    if not dri_dir.is_dir():
        return ""

    # renderD128 is the normal Intel render node on Linux. Fall back to any
    # renderD* node so the diagnostic remains useful on unusual hosts.
    preferred = dri_dir / "renderD128"
    if preferred.exists():
        return str(preferred)

    render_nodes = sorted(dri_dir.glob("renderD*"))
    return str(render_nodes[0]) if render_nodes else ""


def _ffmpeg_has_qsv_encoder(ffmpeg_path: str) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            [ffmpeg_path, "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"无法读取 FFmpeg 编码器列表: {exc}"

    output = f"{proc.stdout}\n{proc.stderr}"
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout or "FFmpeg 编码器检测失败").strip()
    return "h264_qsv" in output, ""


def _run_qsv_encode_test(ffmpeg_path: str) -> tuple[bool, str]:
    """Run a tiny real H.264 QSV encode, matching the app's actual codec path."""
    with tempfile.TemporaryDirectory(prefix="mpt-qsv-check-") as temp_dir:
        output_file = os.path.join(temp_dir, "qsv-test.mp4")
        command = [
            ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=128x128:r=30:d=0.35",
            "-an",
            "-c:v",
            "h264_qsv",
            "-pix_fmt",
            "nv12",
            output_file,
        ]
        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=20,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, f"QSV 实际编码测试无法执行: {exc}"

        if proc.returncode != 0:
            message = (proc.stderr or proc.stdout or "QSV 实际编码失败").strip()
            # Keep diagnostics readable in the WebUI while retaining the useful tail.
            return False, message[-1800:]

        try:
            if os.path.getsize(output_file) <= 0:
                return False, "QSV 测试命令成功返回，但输出文件为空"
        except OSError as exc:
            return False, f"无法验证 QSV 测试输出: {exc}"

    return True, ""


def check_intel_qsv() -> QsvCheckResult:
    """Perform an end-to-end Intel Quick Sync availability check."""
    configured_codec = str(config.app.get("video_codec", "libx264") or "libx264")
    ffmpeg_path = utils.get_ffmpeg_binary()
    dri_present = os.path.isdir("/dev/dri")
    render_node = _find_render_node()
    render_node_accessible = bool(
        render_node
        and os.path.exists(render_node)
        and os.access(render_node, os.R_OK | os.W_OK)
    )
    qsv_encoder_present, encoder_error = _ffmpeg_has_qsv_encoder(ffmpeg_path)

    encode_test_passed = False
    error = ""
    if not dri_present:
        error = "容器内未发现 /dev/dri；请检查 Docker devices 映射。"
    elif not render_node:
        error = "已发现 /dev/dri，但没有 renderD* 设备节点。"
    elif not render_node_accessible:
        error = f"容器没有读写 {render_node} 的权限。"
    elif not qsv_encoder_present:
        error = encoder_error or "当前 FFmpeg 不包含 h264_qsv 编码器。"
    else:
        encode_test_passed, error = _run_qsv_encode_test(ffmpeg_path)

    available = all(
        (
            dri_present,
            bool(render_node),
            render_node_accessible,
            qsv_encoder_present,
            encode_test_passed,
        )
    )

    return QsvCheckResult(
        available=available,
        configured_codec=configured_codec,
        ffmpeg_path=ffmpeg_path,
        dri_present=dri_present,
        render_node=render_node,
        render_node_accessible=render_node_accessible,
        qsv_encoder_present=qsv_encoder_present,
        encode_test_passed=encode_test_passed,
        libva_driver=os.environ.get("LIBVA_DRIVER_NAME", ""),
        error=error,
    )
