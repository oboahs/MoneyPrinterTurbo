"""Unified cross-platform publishing for generated videos.

Upload-Post remains the API provider for TikTok, Instagram and YouTube.  The
optional ``social-auto-upload`` adapter handles browser-based publishing to
Douyin, Kuaishou, Xiaohongshu, Bilibili and WeChat Channels/Tencent.
"""

from __future__ import annotations

import os
from typing import Optional

import requests
from loguru import logger

from app.config import config
from app.services.social_auto_upload import (
    SUPPORTED_PLATFORMS as SOCIAL_AUTO_UPLOAD_PLATFORMS,
    social_auto_upload_service,
)


UPLOAD_POST_PLATFORMS = {"tiktok", "instagram", "youtube"}


class UploadPostService:
    API_BASE = "https://api.upload-post.com"

    def __init__(self):
        self.api_key = config.app.get("upload_post_api_key", "")
        self.username = config.app.get("upload_post_username", "")
        self.enabled = bool(config.app.get("upload_post_enabled", False))
        self.upload_post_platforms = [
            str(platform).strip().lower()
            for platform in config.app.get(
                "upload_post_platforms", ["tiktok", "instagram"]
            )
            if str(platform).strip().lower() in UPLOAD_POST_PLATFORMS
        ]
        self.upload_post_auto_upload = bool(
            config.app.get("upload_post_auto_upload", False)
        )
        self.youtube_privacy_status = config.app.get(
            "upload_post_youtube_privacy_status", "public"
        )

        # task.py already owns a reliable asynchronous publishing queue.  Expose
        # the union of providers through the same interface so no second task
        # system is needed.  Only platforms whose provider explicitly enables
        # auto-upload are included; this prevents enabling one provider from
        # accidentally auto-publishing through the other.
        self.auto_upload = bool(
            self.upload_post_auto_upload or social_auto_upload_service.auto_upload
        )
        self.platforms = []
        if self._is_upload_post_configured() and self.upload_post_auto_upload:
            self.platforms.extend(self.upload_post_platforms)
        if (
            social_auto_upload_service.is_configured()
            and social_auto_upload_service.auto_upload
        ):
            self.platforms.extend(social_auto_upload_service.platforms)

    def _is_upload_post_configured(self) -> bool:
        return bool(self.api_key and self.username and self.enabled)

    def is_configured(self) -> bool:
        return bool(
            self._is_upload_post_configured()
            or social_auto_upload_service.is_configured()
        )

    def upload_video(
        self,
        video_path: str,
        title: str,
        platforms: Optional[list] = None,
        privacy_level: str = "PUBLIC_TO_EVERYONE",
        youtube_extra: Optional[dict] = None,
    ) -> dict:
        """Upload a video through Upload-Post only."""
        if not self._is_upload_post_configured():
            logger.warning("Upload-Post is not configured. Skipping API cross-post.")
            return {
                "success": False,
                "provider": "upload-post",
                "error": "Upload-Post not configured",
            }

        if platforms is None:
            platforms = self.upload_post_platforms
        platforms = [
            str(platform).strip().lower()
            for platform in platforms
            if str(platform).strip().lower() in UPLOAD_POST_PLATFORMS
        ]
        if not platforms:
            return {
                "success": False,
                "provider": "upload-post",
                "error": "no Upload-Post platforms requested",
            }

        if not os.path.exists(video_path):
            logger.error(f"Video file not found: {video_path}")
            return {
                "success": False,
                "provider": "upload-post",
                "error": f"Video file not found: {video_path}",
            }

        logger.info(
            f"Cross-posting video to {', '.join(platforms)} via Upload-Post..."
        )

        try:
            with open(video_path, "rb") as video_file:
                files = {"video": video_file}

                data = [
                    ("user", self.username),
                    ("title", title[:2200]),
                    ("privacy_level", privacy_level),
                ]

                for platform in platforms:
                    data.append(("platform[]", platform))

                if youtube_extra and any(
                    platform.startswith("youtube") for platform in platforms
                ):
                    if "youtube_title" in youtube_extra:
                        data.append(
                            ("youtube_title", youtube_extra["youtube_title"][:100])
                        )
                    if "youtube_description" in youtube_extra:
                        data.append(
                            (
                                "youtube_description",
                                youtube_extra["youtube_description"],
                            )
                        )
                    for tag in youtube_extra.get("tags", []):
                        data.append(("tags[]", tag))
                    data.append(
                        (
                            "privacyStatus",
                            youtube_extra.get("privacyStatus", "public"),
                        )
                    )
                    data.append(("containsSyntheticMedia", "true"))

                headers = {"Authorization": f"Apikey {self.api_key}"}

                response = requests.post(
                    f"{self.API_BASE}/api/upload",
                    headers=headers,
                    data=data,
                    files=files,
                    timeout=300,
                )

                response.raise_for_status()
                result = response.json()
                if not isinstance(result, dict):
                    result = {
                        "success": False,
                        "error": "Upload-Post returned an invalid response",
                    }
                result.setdefault("provider", "upload-post")
                result.setdefault("platforms", platforms)

                if result.get("success"):
                    logger.info(
                        "Video cross-posted successfully via Upload-Post. "
                        f"Request ID: {result.get('request_id')}"
                    )
                else:
                    logger.warning(
                        "Upload-Post failed: "
                        f"{result.get('message', result.get('error', 'Unknown error'))}"
                    )

                return result

        except requests.exceptions.RequestException as exc:
            logger.error(f"Failed to cross-post video via Upload-Post: {exc}")
            return {
                "success": False,
                "provider": "upload-post",
                "platforms": platforms,
                "error": str(exc),
            }

    def cross_post_video(
        self,
        video_path: str,
        title: str,
        platforms: Optional[list] = None,
        youtube_extra: Optional[dict] = None,
    ) -> dict:
        """Route requested platforms to the appropriate publishing provider."""
        if platforms is None:
            platforms = self.platforms
        requested_platforms = [
            str(platform).strip().lower()
            for platform in (platforms or [])
            if str(platform).strip()
        ]
        if not requested_platforms:
            return {
                "success": False,
                "error": "no publishing platforms requested",
                "results": [],
            }

        upload_post_platforms = [
            platform
            for platform in requested_platforms
            if platform in UPLOAD_POST_PLATFORMS
        ]
        local_platforms = [
            platform
            for platform in requested_platforms
            if platform in SOCIAL_AUTO_UPLOAD_PLATFORMS
        ]
        unknown_platforms = [
            platform
            for platform in requested_platforms
            if platform not in UPLOAD_POST_PLATFORMS
            and platform not in SOCIAL_AUTO_UPLOAD_PLATFORMS
        ]

        results = []
        if upload_post_platforms:
            results.append(
                self.upload_video(
                    video_path=video_path,
                    title=title,
                    platforms=upload_post_platforms,
                    youtube_extra=youtube_extra,
                )
            )

        for platform in local_platforms:
            results.append(
                social_auto_upload_service.upload_video(
                    video_path=video_path,
                    title=title,
                    platform=platform,
                )
            )

        for platform in unknown_platforms:
            results.append(
                {
                    "success": False,
                    "provider": "router",
                    "platform": platform,
                    "error": f"unsupported publishing platform: {platform}",
                }
            )

        failures = [result for result in results if not result.get("success")]
        return {
            "success": not failures and bool(results),
            "provider": "multi-provider" if len(results) > 1 else results[0].get(
                "provider", "publisher"
            ),
            "platforms": requested_platforms,
            "results": results,
            "error": (
                "; ".join(
                    str(
                        result.get("error")
                        or result.get("message")
                        or "unknown publishing error"
                    )
                    for result in failures
                )
                if failures
                else None
            ),
        }

    def check_status(self, request_id: str) -> dict:
        """Check the status of an Upload-Post API request."""
        try:
            headers = {"Authorization": f"Apikey {self.api_key}"}
            response = requests.get(
                f"{self.API_BASE}/api/uploadposts/status",
                params={"request_id": request_id},
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as exc:
            logger.error(f"Failed to check Upload-Post status: {exc}")
            return {"success": False, "error": str(exc)}


upload_post_service = UploadPostService()


def cross_post_video(
    video_path: str,
    title: str,
    platforms: Optional[list] = None,
    youtube_extra: Optional[dict] = None,
) -> dict:
    return upload_post_service.cross_post_video(
        video_path=video_path,
        title=title,
        platforms=platforms,
        youtube_extra=youtube_extra,
    )
