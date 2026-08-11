from __future__ import annotations

import streamlit as st

from app.services.social_auto_upload import social_auto_upload_service


st.set_page_config(
    page_title="MoneyPrinterTurbo",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="auto",
)

# MoneyPrinterTurbo 的历史页面样式会主动隐藏 Streamlit 自带 header/toolbar。
# 因此一级功能导航不再依赖 Streamlit 的 top-header navigation，而是在入口页
# 正文最顶部渲染一个稳定的横向 segmented control。路由仍由 st.navigation
# 管理，只把原生导航本身隐藏，避免未来 Streamlit header 结构变化再次让入口消失。
st.markdown(
    """
    <style>
    div[class*="st-key-mpt_primary_nav_"] {
        margin: 0 0 0.45rem 0 !important;
        padding: 0 !important;
    }

    div[class*="st-key-mpt_primary_nav_"] [role="radiogroup"] {
        display: flex !important;
        flex-wrap: nowrap !important;
        gap: 0 !important;
        width: fit-content !important;
        border-bottom: 1px solid color-mix(in srgb, currentColor 16%, transparent) !important;
    }

    div[class*="st-key-mpt_primary_nav_"] [role="radiogroup"] > button {
        min-width: 8.5rem !important;
        padding: 0.5rem 1rem !important;
        border: 0 !important;
        border-radius: 0 !important;
        background: transparent !important;
        box-shadow: none !important;
        opacity: 0.68;
    }

    div[class*="st-key-mpt_primary_nav_"] [role="radiogroup"] > button:hover {
        opacity: 1;
        background: color-mix(in srgb, currentColor 5%, transparent) !important;
    }

    div[class*="st-key-mpt_primary_nav_"] [role="radiogroup"] > button[data-selected="true"] {
        opacity: 1;
        font-weight: 600 !important;
        border-bottom: 2px solid currentColor !important;
    }

    @media (max-width: 600px) {
        div[class*="st-key-mpt_primary_nav_"] [role="radiogroup"] {
            width: 100% !important;
        }

        div[class*="st-key-mpt_primary_nav_"] [role="radiogroup"] > button {
            flex: 1 1 0 !important;
            min-width: 0 !important;
            padding-left: 0.5rem !important;
            padding-right: 0.5rem !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


video_page = st.Page(
    "Main.py",
    title="视频生成",
    icon=":material/movie:",
    default=True,
)
social_page = st.Page(
    "social_publishing_page.py",
    title="社交平台发布",
    icon=":material/publish:",
)
pages = [video_page, social_page]
page = st.navigation(pages, position="hidden")

labels = [item.title for item in pages]
selected = st.segmented_control(
    "功能区",
    options=labels,
    default=page.title,
    key=f"mpt_primary_nav_{page.url_path or 'video'}",
    label_visibility="collapsed",
    width="content",
)

if selected and selected != page.title:
    target_page = social_page if selected == social_page.title else video_page
    st.switch_page(target_page)

if page.title == social_page.title:
    runtime = social_auto_upload_service.runtime_status()
    if not runtime.get("ready") and runtime.get("runtime_kind") == "local":
        st.info(
            "当前是本机运行模式，浏览器自动发布环境尚未安装完整。"
            " Windows 请在项目根目录运行 `setup-social-publishing.bat`；"
            " macOS/Linux 运行 `./setup-social-publishing.sh`。"
            " 安装完成后刷新此页面即可，不需要重建 Docker。"
        )
    elif not runtime.get("ready") and runtime.get("runtime_kind") == "docker":
        st.info(
            "当前是 Docker/NAS 运行模式，浏览器自动发布环境尚未完整就绪。"
            " 请使用本仓库 Dockerfile 重新构建镜像，例如 `docker compose up -d --build`。"
        )

page.run()
