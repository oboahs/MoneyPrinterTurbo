"""Local browser-based social publishing via dreammis/social-auto-upload.

This adapter intentionally talks to the upstream ``sau`` CLI instead of copying
platform automation code into MoneyPrinterTurbo. The upstream project changes
selectors and anti-bot workarounds frequently; keeping that implementation
separate lets us pin/update it in the Docker image without coupling the video
pipeline to individual social sites.
"""

from __future__ import annotations

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


class SocialAutoUploadService:
    """Invoke the pinned social-auto-upload CLI for one platform at a time."""

    def __init__(self):
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
        self.workdir = str(
            config.app.get(
                "social_auto_upload_workdir", "/opt/social-auto-upload"
            )
            or ""
        ).strip()
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
        return bool(self.enabled and self.platforms)

    def account_for(self, platform: str) -> str:
        return self.accounts.get(platform, self.default_account)

    def _resolve_command(self) -> str | None:
        if os.path.isabs(self.command) or os.sep in self.command:
            return self.command if Path(self.command).is_file() else None
        return shutil.which(self.command)

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
                    "Install the upstream project and patchright Chromium first."
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
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
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
