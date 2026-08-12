from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


DOUYIN_ORIGINAL = (
    '    launch_kwargs = {"headless": use_headless, "channel": "chrome", '
    '"args": ["--no-sandbox", "--disable-blink-features=AutomationControlled"]}\n'
)
DOUYIN_PATCHED = (
    '    launch_kwargs = {"headless": use_headless, '
    '"args": ["--no-sandbox", "--disable-blink-features=AutomationControlled"]}\n'
    '    if LOCAL_CHROME_PATH:\n'
    '        launch_kwargs["executable_path"] = LOCAL_CHROME_PATH\n'
    '    else:\n'
    '        launch_kwargs["channel"] = "chrome"\n'
)


def _patch_conf(source_dir: Path, browser_executable: Path) -> None:
    conf_path = source_dir / "conf.py"
    example_path = source_dir / "conf.example.py"
    if not conf_path.exists():
        if not example_path.exists():
            raise RuntimeError(f"Missing conf.example.py in {source_dir}")
        conf_path.write_text(example_path.read_text(encoding="utf-8"), encoding="utf-8")

    text = conf_path.read_text(encoding="utf-8")
    replacement = f"LOCAL_CHROME_PATH = {str(browser_executable)!r}"
    updated, count = re.subn(
        r"^LOCAL_CHROME_PATH\s*=\s*.*$",
        replacement,
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise RuntimeError("Could not update LOCAL_CHROME_PATH in social-auto-upload/conf.py")
    conf_path.write_text(updated, encoding="utf-8")


def _patch_douyin_cookie_auth(source_dir: Path) -> None:
    path = source_dir / "uploader" / "douyin_uploader" / "main.py"
    text = path.read_text(encoding="utf-8")
    if DOUYIN_PATCHED in text:
        return
    if DOUYIN_ORIGINAL not in text:
        raise RuntimeError(
            "Pinned Douyin runtime no longer matches the expected Chrome launch block; "
            "review the upstream diff before updating SOCIAL_AUTO_UPLOAD_REF."
        )
    path.write_text(text.replace(DOUYIN_ORIGINAL, DOUYIN_PATCHED, 1), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--browser-executable", required=True)
    parser.add_argument("--browser-root", required=True)
    parser.add_argument("--upstream-ref", required=True)
    args = parser.parse_args()

    source_dir = Path(args.source).resolve()
    browser_executable = Path(args.browser_executable).resolve()
    browser_root = Path(args.browser_root).resolve()
    if not source_dir.is_dir():
        raise RuntimeError(f"Social uploader source directory does not exist: {source_dir}")
    if not browser_executable.is_file():
        raise RuntimeError(f"Patchright Chromium executable does not exist: {browser_executable}")

    _patch_conf(source_dir, browser_executable)
    _patch_douyin_cookie_auth(source_dir)
    (source_dir / "cookies").mkdir(parents=True, exist_ok=True)

    marker = {
        "schema": 1,
        "upstream_ref": args.upstream_ref,
        "browser_root": str(browser_root),
        "browser_executable": str(browser_executable),
    }
    (source_dir / ".mpt-runtime.json").write_text(
        json.dumps(marker, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(marker, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
