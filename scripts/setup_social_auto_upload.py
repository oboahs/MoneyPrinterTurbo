from __future__ import annotations

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


def browser_ready() -> bool:
    if not BROWSER_DIR.is_dir():
        return False
    try:
        return any(BROWSER_DIR.iterdir())
    except OSError:
        return False


def runtime_ready() -> bool:
    return (
        SOURCE_DIR.is_dir()
        and (SOURCE_DIR / "cookies").is_dir()
        and venv_python().is_file()
        and venv_sau().is_file()
        and venv_patchright().is_file()
        and browser_ready()
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

    conf_file = SOURCE_DIR / "conf.py"
    if not conf_file.exists():
        shutil.copy2(SOURCE_DIR / "conf.example.py", conf_file)
    (SOURCE_DIR / "cookies").mkdir(parents=True, exist_ok=True)


def ensure_venv() -> None:
    python = venv_python()
    if not python.is_file():
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


def ensure_browser() -> None:
    BROWSER_DIR.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PLAYWRIGHT_BROWSERS_PATH": str(BROWSER_DIR)}
    if browser_ready():
        return
    run([str(venv_patchright()), "install", "chromium"], env=env)


def main() -> int:
    if "--check" in sys.argv:
        if runtime_ready():
            print("Social publishing runtime is ready.")
            return 0
        print("Social publishing runtime is not ready.")
        return 1

    print("Setting up local social publishing runtime...")
    print(f"Runtime root: {RUNTIME_ROOT}")
    ensure_source()
    ensure_venv()
    ensure_browser()

    if not runtime_ready():
        raise RuntimeError("Setup finished but runtime validation still failed.")

    print("\nSocial publishing runtime is ready.")
    print(f"CLI: {venv_sau()}")
    print(f"Workdir: {SOURCE_DIR}")
    print(f"Cookies: {SOURCE_DIR / 'cookies'}")
    print(f"Browsers: {BROWSER_DIR}")
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
