from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEBUI_ENTRY = PROJECT_ROOT / "webui" / "App.py"
SOCIAL_PAGE = PROJECT_ROOT / "webui" / "social_publishing_page.py"
EXPECTED_STREAMLIT_VERSION = "1.59.1"


def _find_available_port(host: str, preferred: int) -> int:
    candidates = [preferred] + [port for port in range(8502, 8600) if port != preferred]
    for port in candidates:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"No available WebUI port found in 8501-8599 for {host}")


def _streamlit_version() -> str:
    try:
        import streamlit

        return str(streamlit.__version__)
    except Exception:
        return "unknown"


def main() -> int:
    os.chdir(PROJECT_ROOT)
    os.environ["PYTHONPATH"] = str(PROJECT_ROOT) + (
        os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else ""
    )

    if not WEBUI_ENTRY.is_file():
        raise RuntimeError(f"WebUI entry not found: {WEBUI_ENTRY}")
    if not SOCIAL_PAGE.is_file():
        raise RuntimeError(f"Social publishing page not found: {SOCIAL_PAGE}")

    version = _streamlit_version()
    if version != EXPECTED_STREAMLIT_VERSION:
        print(
            f"***** WARNING: Streamlit {version}; expected {EXPECTED_STREAMLIT_VERSION}. "
            "Run 'uv sync --frozen' before testing this checkout. *****",
            flush=True,
        )

    host = os.environ.get("MPT_WEBUI_HOST", "127.0.0.1").strip() or "127.0.0.1"
    try:
        preferred_port = int(os.environ.get("MPT_WEBUI_PORT", "8501"))
    except ValueError as exc:
        raise RuntimeError("MPT_WEBUI_PORT must be an integer") from exc

    port = _find_available_port(host, preferred_port)
    if port != preferred_port:
        print(
            f"***** Port {preferred_port} is unavailable; using {port}. "
            f"Open the exact URL below rather than an older {preferred_port} tab. *****",
            flush=True,
        )

    print(f"***** Platform: {sys.platform} *****", flush=True)
    print(f"***** Project root: {PROJECT_ROOT} *****", flush=True)
    print(f"***** WebUI entry: {WEBUI_ENTRY} *****", flush=True)
    print(f"***** Streamlit version: {version} *****", flush=True)
    print(f"***** WebUI address: http://{host}:{port} *****", flush=True)
    print("***** Expected primary tabs: Video Generation | Social Publishing *****", flush=True)

    args = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(WEBUI_ENTRY),
        f"--server.address={host}",
        f"--server.port={port}",
        f"--browser.serverAddress={host}",
        "--browser.gatherUsageStats=False",
        "--client.toolbarMode=minimal",
        "--logger.hideWelcomeMessage=True",
        "--server.showEmailPrompt=False",
        "--server.enableCORS=True",
    ]
    return subprocess.run(args, cwd=PROJECT_ROOT, check=False).returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
