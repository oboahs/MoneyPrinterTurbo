from __future__ import annotations

import streamlit as st


st.set_page_config(
    page_title="MoneyPrinterTurbo",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="auto",
)

# Main.py 的历史样式会隐藏整个 Streamlit header，以去掉 Deploy/toolbar，并把
# 主内容顶部留白压到 0.5rem。顶部导航本身也位于 header 中，因此入口页用
# 更高 CSS specificity 恢复 header 和合理的内容起始位置，同时继续隐藏平台
# 工具栏。即使业务页调用 st.stop()，这些规则也不依赖 page.run() 后再次注入。
st.markdown(
    """
    <style>
    html body header[data-testid="stHeader"] {
        display: flex !important;
        visibility: visible !important;
    }

    html body div[data-testid="stMainBlockContainer"] {
        padding-top: 4.5rem !important;
    }

    html body div[data-testid="stToolbar"],
    html body div[data-testid="stDecoration"],
    html body div[data-testid="stStatusWidget"],
    html body div[data-testid="stSkillsNudgeAnchor"],
    html body div[data-testid="stSkillsNudge"] {
        display: none !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


page = st.navigation(
    [
        st.Page(
            "Main.py",
            title="视频生成",
            icon=":material/movie:",
            default=True,
        ),
        st.Page(
            "social_publishing_page.py",
            title="社交平台发布",
            icon=":material/publish:",
        ),
    ],
    position="top",
)
page.run()
