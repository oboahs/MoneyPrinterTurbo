from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


REPO_URL = "https://github.com/dreammis/social-auto-upload.git"
REPO_REF = "008e4ff66abdf48eb1f4b999272ef979711af436"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = PROJECT_ROOT / "storage" / "social-auto-upload"
SOURCE_DIR = RUNTIME_ROOT / "runtime"
VENV_DIR = RUNTIME_ROOT / "venv"
BROWSER_DIR = RUNTIME_ROOT / "browsers"
PATCH_SCRIPT = PROJECT_ROOT / "scripts" / "patch_social_auto_upload_runtime.py"
RUNTIME_MARKER = SOURCE_DIR / ".mpt-runtime.json"


def run(args: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(str(arg) for arg in args), flush=True)
    subprocess.run(args, cwd=cwd, env=env, check=True)


def venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def venv_sau() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "sau.exe"
    return VENV_DIR / "bin" / "sau"


def venv_patchright() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "patchright.exe"
    return VENV_DIR / "bin" / "patchright"


def _read_marker() -> dict:
    try:
        return json.loads(RUNTIME_MARKER.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}


def runtime_ready() -> bool:
    marker = _read_marker()
    browser_executable = Path(str(marker.get("browser_executable") or ""))
    return bool(
        SOURCE_DIR.is_dir()
        and (SOURCE_DIR / "cookies").is_dir()
        and venv_python().is_file()
        and venv_sau().is_file()
        and venv_patchright().is_file()
        and marker.get("upstream_ref") == REPO_REF
        and browser_executable.is_file()
    )


def ensure_source() -> None:
    git = shutil.which("git")
    if not git:
        raise RuntimeError("Git was not found. Install Git first, then rerun this setup.")

    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    if not (SOURCE_DIR / ".git").is_dir():
        if SOURCE_DIR.exists():
            shutil.rmtree(SOURCE_DIR)
        run([git, "clone", "--filter=blob:none", "--no-checkout", REPO_URL, str(SOURCE_DIR)])

    run([git, "fetch", "--depth", "1", "origin", REPO_REF], cwd=SOURCE_DIR)
    run([git, "checkout", "--detach", "--force", "FETCH_HEAD"], cwd=SOURCE_DIR)
    (SOURCE_DIR / "cookies").mkdir(parents=True, exist_ok=True)


def ensure_venv() -> None:
    python = venv_python()
    if not python.is_file():
        if VENV_DIR.exists():
            shutil.rmtree(VENV_DIR)
        RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
        run([sys.executable, "-m", "venv", str(VENV_DIR)])

    python = venv_python()
    run([str(python), "-m", "pip", "install", "--disable-pip-version-check", "--upgrade", "pip"])
    run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "setuptools>=69",
            "loguru==0.7.3",
            "patchright==1.58.2",
            "opencv-python>=4.13.0.92",
            "qrcode==8.2",
            "requests==2.32.3",
            "segno>=1.6.6",
        ]
    )
    run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-deps",
            "--no-build-isolation",
            "-e",
            str(SOURCE_DIR),
        ]
    )


def _browser_env() -> dict[str, str]:
    return {**os.environ, "PLAYWRIGHT_BROWSERS_PATH": str(BROWSER_DIR)}


def ensure_browser() -> Path:
    BROWSER_DIR.mkdir(parents=True, exist_ok=True)
    env = _browser_env()
    # Patchright's install command is idempotent. Running it on every setup makes
    # a copied checkout self-healing if the browser cache is partial or stale.
    run([str(venv_patchright()), "install", "chromium"], env=env)

    code = (
        "from patchright.sync_api import sync_playwright; "
        "p=sync_playwright().start(); "
        "print(p.chromium.executable_path); "
        "p.stop()"
    )
    output = subprocess.check_output(
        [str(venv_python()), "-c", code],
        env=env,
        text=True,
    ).strip()
    browser_executable = Path(output)
    if not browser_executable.is_file():
        raise RuntimeError(
            f"Patchright reported a Chromium executable that does not exist: {browser_executable}"
        )
    return browser_executable


def patch_runtime(browser_executable: Path) -> None:
    run(
        [
            sys.executable,
            str(PATCH_SCRIPT),
            "--source",
            str(SOURCE_DIR),
            "--browser-executable",
            str(browser_executable),
            "--browser-root",
            str(BROWSER_DIR),
            "--upstream-ref",
            REPO_REF,
        ]
    )


def main() -> int:
    if "--check" in sys.argv:
        if runtime_ready():
            print("Social publishing runtime is ready.")
            return 0
        print("Social publishing runtime is not ready.")
        return 1

    print("Setting up local social publishing runtime...")
    print(f"Platform: {sys.platform}")
    print(f"Runtime root: {RUNTIME_ROOT}")
    ensure_source()
    ensure_venv()
    browser_executable = ensure_browser()
    patch_runtime(browser_executable)

    if not runtime_ready():
        raise RuntimeError("Setup finished but runtime validation still failed.")

    print("\nSocial publishing runtime is ready.")
    print(f"CLI: {venv_sau()}")
    print(f"Workdir: {SOURCE_DIR}")
    print(f"Cookies: {SOURCE_DIR / 'cookies'}")
    print(f"Browsers: {BROWSER_DIR}")
    print(f"Chromium: {browser_executable}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nSetup cancelled.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"\n[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
