"""Local browser-based social publishing via dreammis/social-auto-upload.

This adapter intentionally talks to the upstream ``sau`` CLI instead of copying
platform automation code into MoneyPrinterTurbo. The upstream project changes
selectors and anti-bot workarounds frequently; keeping that implementation
separate lets us pin/update it without coupling the video pipeline to individual
social sites.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

from loguru import logger

from app.config import config


SUPPORTED_PLATFORMS = {
    "douyin",
    "kuaishou",
    "xiaohongshu",
    "bilibili",
    "tencent",
}
SOCIAL_AUTO_UPLOAD_REF = "008e4ff66abdf48eb1f4b999272ef979711af436"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOCAL_RUNTIME_ROOT = PROJECT_ROOT / "storage" / "social-auto-upload"
LOCAL_SOURCE_DIR = LOCAL_RUNTIME_ROOT / "runtime"
LOCAL_VENV_DIR = LOCAL_RUNTIME_ROOT / "venv"
LOCAL_BROWSER_ROOT = LOCAL_RUNTIME_ROOT / "browsers"
DOCKER_SOURCE_DIR = Path("/opt/social-auto-upload")
DOCKER_BROWSER_ROOT = Path("/opt/patchright-browsers")


def _normalize_platforms(value) -> list[str]:
    if isinstance(value, str):
        value = value.split(",")
    return [
        str(item).strip().lower()
        for item in (value or [])
        if str(item).strip()
    ]


def _normalize_tags(value) -> list[str]:
    if isinstance(value, str):
        value = value.split(",")

    tags = []
    for tag in value or []:
        cleaned = str(tag).strip().lstrip("#").strip()
        if cleaned:
            tags.append(cleaned)
    return tags


def _tail(value: str | None, limit: int = 3000) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[-limit:]


def _looks_like_docker_default(path: str) -> bool:
    normalized = str(path or "").strip().replace("\\", "/").rstrip("/")
    return normalized == "/opt/social-auto-upload"


def _local_sau_command() -> Path:
    if os.name == "nt":
        return LOCAL_VENV_DIR / "Scripts" / "sau.exe"
    return LOCAL_VENV_DIR / "bin" / "sau"


def _read_runtime_marker(workdir: Path | None) -> dict:
    if not workdir:
        return {}
    marker_path = workdir / ".mpt-runtime.json"
    try:
        value = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


class SocialAutoUploadService:
    """Invoke the pinned social-auto-upload CLI for one platform at a time."""

    def __init__(self):
        self.refresh_config()

    @staticmethod
    def _using_docker_runtime() -> bool:
        # Do not infer Docker from the existence of /opt/social-auto-upload. A
        # developer can have similarly named folders on Linux/macOS, while the
        # project already has a tested container detector used elsewhere.
        return bool(config.is_running_in_container())

    def _default_workdir(self) -> str:
        if self._using_docker_runtime():
            return str(DOCKER_SOURCE_DIR)
        return str(LOCAL_SOURCE_DIR)

    def _browser_root(self) -> Path:
        configured = str(os.getenv("PLAYWRIGHT_BROWSERS_PATH", "") or "").strip()
        if configured:
            return Path(configured)
        if self._using_docker_runtime():
            return DOCKER_BROWSER_ROOT
        return LOCAL_BROWSER_ROOT

    def _subprocess_env(self) -> dict[str, str]:
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        env.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(self._browser_root()))
        return env

    def refresh_config(self) -> None:
        """Reload mutable publishing settings without requiring a process restart."""
        self.enabled = bool(config.app.get("social_auto_upload_enabled", False))
        self.auto_upload = bool(
            config.app.get("social_auto_upload_auto_upload", False)
        )
        configured_platforms = _normalize_platforms(
            config.app.get("social_auto_upload_platforms", [])
        )
        self.platforms = [
            platform
            for platform in configured_platforms
            if platform in SUPPORTED_PLATFORMS
        ]
        unsupported = sorted(set(configured_platforms) - SUPPORTED_PLATFORMS)
        if unsupported:
            logger.warning(
                "ignore unsupported social-auto-upload platforms: "
                + ", ".join(unsupported)
            )

        raw_accounts = config.app.get("social_auto_upload_accounts", {}) or {}
        self.accounts = (
            {
                str(platform).strip().lower(): str(account).strip()
                for platform, account in raw_accounts.items()
                if str(platform).strip() and str(account).strip()
            }
            if isinstance(raw_accounts, dict)
            else {}
        )
        self.default_account = str(
            config.app.get("social_auto_upload_default_account", "") or ""
        ).strip()
        self.command = str(
            config.app.get("social_auto_upload_command", "sau") or "sau"
        ).strip()

        configured_workdir = str(
            config.app.get("social_auto_upload_workdir", "") or ""
        ).strip()
        if not configured_workdir or (
            not self._using_docker_runtime()
            and _looks_like_docker_default(configured_workdir)
        ):
            configured_workdir = self._default_workdir()
        self.workdir = configured_workdir

        self.timeout = max(
            60,
            int(config.app.get("social_auto_upload_timeout", 900) or 900),
        )
        self.tags = _normalize_tags(config.app.get("social_auto_upload_tags", []))
        self.bilibili_tid = int(
            config.app.get("social_auto_upload_bilibili_tid", 249) or 249
        )
        self.headless = bool(config.app.get("social_auto_upload_headless", True))
        self.description = str(
            config.app.get("social_auto_upload_description", "") or ""
        ).strip()

    def is_configured(self) -> bool:
        """Configuration presence only; runtime availability is checked on upload."""
        self.refresh_config()
        return bool(self.enabled and self.platforms)

    def account_for(self, platform: str) -> str:
        return self.accounts.get(platform, self.default_account)

    def _resolve_command(self) -> str | None:
        if os.path.isabs(self.command) or os.sep in self.command or (
            os.altsep and os.altsep in self.command
        ):
            return self.command if Path(self.command).is_file() else None

        resolved = shutil.which(self.command)
        if resolved:
            return resolved

        if self.command == "sau" and not self._using_docker_runtime():
            local_command = _local_sau_command()
            if local_command.is_file():
                return str(local_command)
        return None

    def runtime_status(self) -> dict:
        """Return inexpensive local runtime diagnostics for the WebUI."""
        self.refresh_config()
        command = self._resolve_command()
        workdir = Path(self.workdir) if self.workdir else None
        cookies_dir = workdir / "cookies" if workdir else None
        browser_root = self._browser_root()
        marker = _read_runtime_marker(workdir)
        browser_executable_value = str(marker.get("browser_executable") or "").strip()
        browser_executable = Path(browser_executable_value) if browser_executable_value else None
        marker_ref = str(marker.get("upstream_ref") or "").strip()
        browser_ready = bool(browser_executable and browser_executable.is_file())
        workdir_ready = bool(workdir and workdir.is_dir())
        cookies_ready = bool(cookies_dir and cookies_dir.is_dir())
        runtime_version_ready = marker_ref == SOCIAL_AUTO_UPLOAD_REF

        using_docker = self._using_docker_runtime()
        ready = bool(
            command
            and workdir_ready
            and cookies_ready
            and browser_ready
            and runtime_version_ready
        )
        return {
            "ready": ready,
            "runtime_kind": "docker" if using_docker else "local",
            "command": command or "",
            "configured_command": self.command,
            "workdir": str(workdir) if workdir else "",
            "workdir_ready": workdir_ready,
            "cookies_dir": str(cookies_dir) if cookies_dir else "",
            "cookies_dir_ready": cookies_ready,
            "browser_root": str(browser_root),
            "browser_ready": browser_ready,
            "browser_executable": str(browser_executable) if browser_executable else "",
            "runtime_ref": marker_ref,
            "expected_runtime_ref": SOCIAL_AUTO_UPLOAD_REF,
            "runtime_version_ready": runtime_version_ready,
            "setup_command": (
                "setup-social-publishing.bat"
                if os.name == "nt" and not using_docker
                else "sh setup-social-publishing.sh"
                if not using_docker
                else "docker compose up -d --build"
            ),
        }

    def check_account(self, platform: str, account: str | None = None) -> dict:
        """Validate one saved social-auto-upload login without publishing anything."""
        self.refresh_config()
        platform = str(platform or "").strip().lower()
        if platform not in SUPPORTED_PLATFORMS:
            return {
                "success": False,
                "platform": platform,
                "account": account or "",
                "error": f"unsupported social-auto-upload platform: {platform}",
            }

        resolved_account = str(account or self.account_for(platform) or "").strip()
        if not resolved_account:
            return {
                "success": False,
                "platform": platform,
                "account": "",
                "error": "no account configured",
            }

        command = self._resolve_command()
        if not command:
            return {
                "success": False,
                "platform": platform,
                "account": resolved_account,
                "error": f"social-auto-upload CLI not found: {self.command}",
            }

        cwd = self.workdir if self.workdir and os.path.isdir(self.workdir) else None
        try:
            result = subprocess.run(
                [
                    command,
                    platform,
                    "check",
                    "--account",
                    resolved_account,
                ],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=min(self.timeout, 45),
                check=False,
                env=self._subprocess_env(),
            )
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "platform": platform,
                "account": resolved_account,
                "error": "account check timed out",
            }
        except OSError as exc:
            return {
                "success": False,
                "platform": platform,
                "account": resolved_account,
                "error": str(exc),
            }

        stdout = _tail(result.stdout, limit=1000)
        stderr = _tail(result.stderr, limit=1000)
        return {
            "success": result.returncode == 0,
            "platform": platform,
            "account": resolved_account,
            "returncode": result.returncode,
            "message": stdout,
            "error": "" if result.returncode == 0 else (stderr or stdout or "invalid login"),
        }

    def _build_command(
        self,
        *,
        command: str,
        platform: str,
        account: str,
        video_path: str,
        title: str,
        description: str,
        tags: Iterable[str],
    ) -> list[str]:
        args = [
            command,
            platform,
            "upload-video",
            "--account",
            account,
            "--file",
            video_path,
            "--title",
            title,
            "--desc",
            description,
        ]
        normalized_tags = _normalize_tags(list(tags))
        if normalized_tags:
            args.extend(["--tags", ",".join(normalized_tags)])

        if platform == "bilibili":
            args.extend(["--tid", str(self.bilibili_tid)])
        else:
            args.append("--headless" if self.headless else "--headed")
        return args

    def upload_video(
        self,
        *,
        video_path: str,
        title: str,
        platform: str,
        description: str = "",
        tags: Iterable[str] | None = None,
    ) -> dict:
        self.refresh_config()
        platform = str(platform or "").strip().lower()
        if platform not in SUPPORTED_PLATFORMS:
            return {
                "success": False,
                "provider": "social-auto-upload",
                "platform": platform,
                "error": f"unsupported social-auto-upload platform: {platform}",
            }
        if not self.enabled:
            return {
                "success": False,
                "provider": "social-auto-upload",
                "platform": platform,
                "error": "social-auto-upload integration is disabled",
            }
        if not os.path.isfile(video_path):
            return {
                "success": False,
                "provider": "social-auto-upload",
                "platform": platform,
                "error": f"video file not found: {video_path}",
            }

        account = self.account_for(platform)
        if not account:
            return {
                "success": False,
                "provider": "social-auto-upload",
                "platform": platform,
                "error": (
                    f"no account configured for {platform}; set "
                    "social_auto_upload_accounts or social_auto_upload_default_account"
                ),
            }

        command = self._resolve_command()
        if not command:
            return {
                "success": False,
                "provider": "social-auto-upload",
                "platform": platform,
                "account": account,
                "error": (
                    f"social-auto-upload CLI not found: {self.command}. "
                    "Install the upstream project and Patchright Chromium first."
                ),
            }

        description = str(description or self.description or title or "").strip()
        effective_tags = list(tags or self.tags)
        args = self._build_command(
            command=command,
            platform=platform,
            account=account,
            video_path=os.path.realpath(video_path),
            title=str(title or "").strip() or "Untitled video",
            description=description,
            tags=effective_tags,
        )
        cwd = self.workdir if self.workdir and os.path.isdir(self.workdir) else None
        logger.info(
            f"publishing via social-auto-upload, platform: {platform}, "
            f"account: {account}, video: {video_path}"
        )

        try:
            result = subprocess.run(
                args,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
                env=self._subprocess_env(),
            )
        except subprocess.TimeoutExpired as exc:
            logger.error(
                f"social-auto-upload timed out, platform: {platform}, "
                f"timeout: {self.timeout}s"
            )
            return {
                "success": False,
                "provider": "social-auto-upload",
                "platform": platform,
                "account": account,
                "error": f"upload timed out after {self.timeout} seconds",
                "stdout": _tail(exc.stdout),
                "stderr": _tail(exc.stderr),
            }
        except OSError as exc:
            logger.exception(
                f"failed to start social-auto-upload, platform: {platform}, error: {exc}"
            )
            return {
                "success": False,
                "provider": "social-auto-upload",
                "platform": platform,
                "account": account,
                "error": str(exc),
            }

        stdout = _tail(result.stdout)
        stderr = _tail(result.stderr)
        if result.returncode != 0:
            error = stderr or stdout or f"sau exited with code {result.returncode}"
            logger.warning(
                f"social-auto-upload failed, platform: {platform}, "
                f"account: {account}, error: {error}"
            )
            return {
                "success": False,
                "provider": "social-auto-upload",
                "platform": platform,
                "account": account,
                "returncode": result.returncode,
                "error": error,
                "stdout": stdout,
                "stderr": stderr,
            }

        logger.success(
            f"social-auto-upload completed, platform: {platform}, account: {account}"
        )
        return {
            "success": True,
            "provider": "social-auto-upload",
            "platform": platform,
            "account": account,
            "returncode": result.returncode,
            "message": stdout or f"uploaded to {platform}",
        }


social_auto_upload_service = SocialAutoUploadService()
