from __future__ import annotations

import os
import shlex
import subprocess
from collections.abc import Mapping

import streamlit as st
from loguru import logger

from app.config import config
from app.services.social_auto_upload import social_auto_upload_service


PLATFORM_LABELS = {
    "douyin": "抖音 / Douyin",
    "xiaohongshu": "小红书 / Xiaohongshu",
    "kuaishou": "快手 / Kuaishou",
    "bilibili": "哔哩哔哩 / Bilibili",
    "tencent": "视频号 / WeChat Channels",
}


def _snapshot() -> dict:
    try:
        return config.snapshot_config_with_pending(config.app)
    except Exception:
        return dict(config.app)


def _save_accounts(accounts: dict[str, str]) -> None:
    updated = config.update_config_nonblocking(
        config.app,
        "social_auto_upload_accounts",
        accounts,
    )
    if not updated:
        logger.debug("deferred social account alias update")
    config.try_save_config()


def _login_args(runtime: dict, platform: str, account: str) -> list[str]:
    command = str(runtime.get("command") or "sau")
    args = [command, platform, "login", "--account", account]
    if platform != "bilibili":
        # First-time login must be visible locally so the user can scan the QR code.
        args.append("--headed")
    return args


def _display_command(runtime: dict, platform: str, account: str) -> str:
    if runtime.get("runtime_kind") == "docker":
        args = [
            "docker",
            "exec",
            "-it",
            "moneyprinterturbo-webui",
            "sau",
            platform,
            "login",
            "--account",
            account,
        ]
        return " ".join(shlex.quote(item) for item in args)

    args = _login_args(runtime, platform, account)
    if os.name == "nt":
        return subprocess.list2cmdline(args)
    return shlex.join(args)


def _launch_windows_login(runtime: dict, platform: str, account: str) -> dict:
    if os.name != "nt" or runtime.get("runtime_kind") != "local":
        return {
            "success": False,
            "error": "当前运行环境不支持从 WebUI 直接弹出本机登录窗口，请使用下方终端命令。",
        }

    if not runtime.get("command"):
        return {
            "success": False,
            "error": "未找到 sau CLI，请先运行 setup-social-publishing.bat。",
        }
    if not runtime.get("workdir_ready"):
        return {
            "success": False,
            "error": "social-auto-upload 运行目录不存在，请先运行 setup-social-publishing.bat。",
        }
    if platform != "bilibili" and not runtime.get("browser_ready"):
        return {
            "success": False,
            "error": "Patchright Chromium 尚未安装，请先运行 setup-social-publishing.bat。",
        }

    args = _login_args(runtime, platform, account)
    command_line = subprocess.list2cmdline(args)
    env = {
        **os.environ,
        "PYTHONUNBUFFERED": "1",
        "PLAYWRIGHT_BROWSERS_PATH": str(runtime.get("browser_root") or ""),
    }

    try:
        creation_flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        subprocess.Popen(
            ["cmd.exe", "/k", command_line],
            cwd=str(runtime.get("workdir") or None),
            env=env,
            creationflags=creation_flags,
        )
    except OSError as exc:
        return {"success": False, "error": str(exc)}

    return {
        "success": True,
        "message": (
            "已打开独立终端。B站登录会在终端显示二维码；如果二维码显示不完整，"
            "请打开运行目录中的 qrcode.png 扫码。"
            if platform == "bilibili"
            else "已打开独立终端并启动可见 Chromium，请在弹出的平台登录页扫描二维码。"
        ),
    }


def render_social_login_panel() -> None:
    snapshot = _snapshot()
    selected_platforms = [
        str(item).strip().lower()
        for item in snapshot.get("social_auto_upload_platforms", []) or []
        if str(item).strip().lower() in PLATFORM_LABELS
    ]
    if not selected_platforms:
        return

    runtime = social_auto_upload_service.runtime_status()
    raw_accounts = snapshot.get("social_auto_upload_accounts", {}) or {}
    accounts = dict(raw_accounts) if isinstance(raw_accounts, Mapping) else {}
    default_account = str(
        snapshot.get("social_auto_upload_default_account", "") or ""
    ).strip()

    with st.expander("账号登录与扫码", expanded=True):
        st.caption(
            "首次使用顺序：填写账号别名 → 点击“登录 / 重新登录” → 在弹出的浏览器或终端扫码 → 返回这里点击“检查登录”。"
            "“检查登录”本身不会上传任何内容。"
        )

        if not runtime.get("ready"):
            setup_command = runtime.get("setup_command") or "setup-social-publishing.bat"
            st.warning(
                "浏览器发布环境尚未就绪，因此登录和检查按钮会保持不可用。"
                f"请先运行 `{setup_command}`，安装完成后刷新页面。"
            )
            st.code(str(setup_command), language="text")

        for platform in selected_platforms:
            with st.container(border=True):
                st.markdown(f"**{PLATFORM_LABELS[platform]}**")
                account = st.text_input(
                    "账号别名",
                    value=str(accounts.get(platform) or default_account or ""),
                    key=f"social_login_panel_account_{platform}",
                    placeholder="例如：main / creator / wechat_main",
                    help="这里只是本地账号标识，用于对应 Cookie 文件，不需要填写平台用户名或手机号。",
                ).strip()

                if account:
                    if accounts.get(platform) != account:
                        accounts[platform] = account
                        _save_accounts(accounts)
                elif platform in accounts:
                    accounts.pop(platform, None)
                    _save_accounts(accounts)

                action_cols = st.columns([1.2, 1.2, 2.6], vertical_alignment="center")
                can_login = bool(
                    account
                    and runtime.get("command")
                    and runtime.get("workdir_ready")
                    and (platform == "bilibili" or runtime.get("browser_ready"))
                )
                can_check = bool(account and runtime.get("ready"))

                if runtime.get("runtime_kind") == "local" and os.name == "nt":
                    if action_cols[0].button(
                        "登录 / 重新登录",
                        key=f"social_login_panel_login_{platform}",
                        use_container_width=True,
                        disabled=not can_login,
                    ):
                        result = _launch_windows_login(runtime, platform, account)
                        st.session_state[f"social_login_launch_{platform}"] = result
                        st.rerun()
                else:
                    action_cols[0].button(
                        "登录 / 重新登录",
                        key=f"social_login_panel_login_{platform}",
                        use_container_width=True,
                        disabled=True,
                        help="当前环境请使用下方终端登录命令。",
                    )

                if action_cols[1].button(
                    "检查登录",
                    key=f"social_login_panel_check_{platform}",
                    use_container_width=True,
                    disabled=not can_check,
                ):
                    with st.spinner("正在检查登录状态…"):
                        result = social_auto_upload_service.check_account(platform, account)
                    st.session_state[f"social_publish_account_status_{platform}"] = result
                    st.rerun()

                status = st.session_state.get(f"social_publish_account_status_{platform}")
                if status:
                    if status.get("success"):
                        action_cols[2].success("登录有效")
                    else:
                        action_cols[2].warning(
                            "需要登录："
                            + str(status.get("error") or status.get("message") or "Cookie 无效")[:180]
                        )
                elif account:
                    action_cols[2].info("尚未检查")
                else:
                    action_cols[2].info("请先填写账号别名")

                launch_result = st.session_state.get(f"social_login_launch_{platform}")
                if launch_result:
                    if launch_result.get("success"):
                        st.success(str(launch_result.get("message") or "登录流程已启动。"))
                    else:
                        st.error(str(launch_result.get("error") or "登录流程启动失败。"))

                if account:
                    st.caption("手动登录命令（需要时可复制到终端执行）：")
                    st.code(_display_command(runtime, platform, account), language="text")
                    if platform == "bilibili" and runtime.get("runtime_kind") == "local":
                        st.caption(
                            "B站由上游 biliup 使用交互式终端登录；二维码无法完整显示时，可打开 "
                            f"`{runtime.get('workdir')}\\qrcode.png` 扫码。"
                        )
                else:
                    st.caption("填写账号别名后，登录按钮和对应终端命令会立即出现。")
