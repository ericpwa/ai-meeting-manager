"""AI 會議記錄管理 Web App 主程式入口 (`app.py`).

核心特色：
- 整合 RACI 責任歸屬模型、SMART 四階目標管理與自訂 QCD+T (Quality, Cost, Delivery, Truthfulness/Evidence) 框架
- 支援 `.env` / `st.secrets` 自動讀取與側邊欄 BYOK (Bring Your Own Key) 動態金鑰注入
- 雙模資料庫引擎：Supabase (PostgreSQL + JSONB + RLS) 雲端優先 ＋ 本地 SQLite 自動降級備援
- 支援貼上逐字稿、上傳 `.txt`/`.md` 與音訊檔兩階段多模態轉譯及 Gemini Structured Outputs (Pydantic) 萃取
"""

from __future__ import annotations

import streamlit as st

from src.repositories.meeting_repo import MeetingRepository
from src.ui.deployment_view import render_deployment_view
from src.ui.extraction_view import render_extraction_view
from src.ui.meetings_view import render_meetings_view
from src.ui.notification_view import render_notification_view
from src.ui.sidebar import render_sidebar
from src.ui.tracker_view import render_tracker_view


def main() -> None:
    st.set_page_config(
        page_title="AI 會議記錄管理 Web App | RACI · SMART · QCD+T",
        page_icon="🛡️",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # 初始化雙模儲存引擎並確保預載跨部門範例會議資料
    repo = MeetingRepository()
    repo.ensure_sample_data_if_empty()

    # 渲染側邊欄 (BYOK 金鑰管理 + 儲存狀態 + 工作區通行碼檢查)
    is_unlocked = render_sidebar(repo)

    # 頁面主標題區
    st.title("🛡️ AI 會議記錄管理 Web App")
    st.markdown(
        "**企業級會議治理中樞**：透過 **Google Gemini Structured Outputs** 自動萃取決策與行動方案，"
        "深度落實 **RACI 單一當責制**、**SMART 四階目標分層** 與 **QCD+T 真實性成果佐證閉環**。"
    )

    if not is_unlocked:
        st.info("🔒 請先於左側邊欄輸入正確的「企業內部工作區通行碼」以檢視與管理會議記錄。")
        return

    # 五大核心功能工作台 Tabs
    tab_extract, tab_history, tab_tracker, tab_notify, tab_deploy = st.tabs(
        [
            "🎙️ 1. 新增會議 & AI 結構化萃取",
            "📚 2. 歷史會議檢索 & 任務佐證更新",
            "📊 3. 全域行動方案追蹤看板 (Global Action Tracker)",
            "🔔 4. 跨部門主動催辦與通知中心",
            "☁️ 5. 雲端部署與系統自檢中心",
        ]
    )

    with tab_extract:
        render_extraction_view(repo)

    with tab_history:
        render_meetings_view(repo)

    with tab_tracker:
        render_tracker_view(repo)

    with tab_notify:
        render_notification_view(repo)

    with tab_deploy:
        render_deployment_view(repo)


if __name__ == "__main__":
    main()
