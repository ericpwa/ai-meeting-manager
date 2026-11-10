"""側邊欄元件：BYOK 動態金鑰注入、雙模資料庫狀態指示燈、工作區通行碼與範例資料管理."""

from __future__ import annotations

import streamlit as st

from src.config import (
    get_gemini_api_key,
    get_gemini_model,
    get_supabase_credentials,
    get_webhook_url,
    get_workspace_passcode,
    is_supabase_configured,
    mask_secret,
)
from src.repositories.meeting_repo import MeetingRepository
from src.services.org_directory_service import (
    generate_sample_roster_csv,
    generate_sample_roster_md,
    generate_sample_roster_xlsx,
    parse_organization_upload,
)


def render_sidebar(repo: MeetingRepository) -> bool:
    """渲染左側資安與管理控制欄，並回傳當前使用者是否已通過選用之工作區通行碼驗證."""
    with st.sidebar:
        st.markdown("## 🛡️ Antigravity 會議治理中心")
        st.caption("Phase 1 企業內部 0 元方案 · 邁向 Phase 2 SaaS")

        st.divider()

        # 1. 選用之企業工作區通行碼保護
        required_passcode = get_workspace_passcode()
        is_unlocked = True
        if required_passcode:
            st.markdown("### 🔒 企業內部工作區驗證")
            entered_pass = st.text_input(
                "輸入內部工作區通行碼",
                type="password",
                key="ui_workspace_passcode_input",
                help="系統管理員已於環境變數設定 WORKSPACE_PASSCODE，請輸入通行碼解鎖。",
            )
            if entered_pass != required_passcode:
                st.warning("請輸入正確的內部工作區通行碼以存取會議記錄。")
                is_unlocked = False
            else:
                st.success("✅ 工作區已解鎖")
            st.divider()

        # 2. 資安鐵律：BYOK (Bring Your Own Key) 動態金鑰管理
        st.markdown("### 🔑 資安與 BYOK 金鑰中心")
        current_gemini_key = get_gemini_api_key()
        if current_gemini_key:
            st.success(f"Gemini API Key 已就緒 (`{mask_secret(current_gemini_key)}`)")
        else:
            st.info("尚未於 `.env` / `st.secrets` 偵測到 Gemini Key，可於下方動態注入 (BYOK) 或使用本地規則引擎體驗。")

        byok_gemini = st.text_input(
            "🔑 Google Gemini API Key (BYOK)",
            value=st.session_state.get("byok_gemini_api_key", ""),
            type="password",
            placeholder="貼上 AIza... 金鑰 (僅存於當前記憶體)",
            help="資安鐵律：動態注入之金鑰僅保存在您當前的瀏覽器 Session 記憶體中，絕不寫入程式碼或磁碟。",
        )
        if byok_gemini.strip():
            st.session_state["byok_gemini_api_key"] = byok_gemini.strip()

        model_choice = st.selectbox(
            "🤖 Gemini 模型選擇",
            options=["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
            index=0,
            help="預設採用免費額度與速度最佳之 gemini-2.5-flash，支援多模態音訊與 Structured Outputs。",
        )
        st.session_state["byok_gemini_model"] = model_choice

        with st.expander("☁️ 進階：Supabase 雲端資料庫 BYOK 設定", expanded=False):
            st.caption("未設定時自動採用本地 SQLite 雙模備援，設定後即刻切換至 Supabase PostgreSQL + JSONB。")
            byok_supa_url = st.text_input(
                "Supabase Project URL",
                value=st.session_state.get("byok_supabase_url", ""),
                placeholder="https://xxxx.supabase.co",
            )
            byok_supa_key = st.text_input(
                "Supabase Anon / Service Key",
                value=st.session_state.get("byok_supabase_key", ""),
                type="password",
                placeholder="eyJ...",
            )
            if st.button("🔄 套用資料庫連線設定", key="btn_apply_supabase"):
                st.session_state["byok_supabase_url"] = byok_supa_url.strip()
                st.session_state["byok_supabase_key"] = byok_supa_key.strip()
                st.rerun()

        with st.expander("🔔 進階：跨部門催辦 Webhook BYOK 設定", expanded=False):
            st.caption("支援 Slack / Teams / Discord Incoming Webhook URL，未設定時採安全模擬推播 (Dry-run)。")
            byok_wh = st.text_input(
                "Notification Webhook URL",
                value=st.session_state.get("byok_webhook_url", ""),
                type="password",
                placeholder="https://hooks.slack.com/services/...",
                key="input_byok_webhook_url",
            )
            if byok_wh.strip():
                st.session_state["byok_webhook_url"] = byok_wh.strip()
            current_wh = get_webhook_url()
            if current_wh:
                st.success(f"Webhook 已就緒 (`{mask_secret(current_wh)}`)")

        st.divider()

        # 3. 系統儲存模式與健康度診斷
        st.markdown("### 🩺 系統儲存與治理狀態")
        st.markdown(f"**儲存模式**：{repo.storage_mode_label}")
        if repo.last_error:
            st.caption(f"⚠️ 備援提示：{repo.last_error}")

        supa_url, _ = get_supabase_credentials()
        if is_supabase_configured():
            st.caption(f"🌐 雲端端點：`{supa_url}`")
        else:
            st.caption(f"📁 本地資料庫：`{repo.db_path.name}`")

        # 4. 企業部門與與會人員批量匯入中心
        st.divider()
        st.markdown("### 👥 部門與人員名冊批量匯入")
        org_depts, org_persons = repo.get_org_directory(include_from_meetings=True)
        st.caption(
            f"目前已納管：**{len(org_depts)} 個部門** ｜ **{len(org_persons)} 位人員**\n"
            "（自動對應「👑 當責者 A」、「🛠️ 執行者 R」與「🏢 部門」篩選選單）"
        )
        uploaded_roster = st.file_uploader(
            "上傳名冊 (.xlsx / .csv / .md)",
            type=["xlsx", "csv", "md"],
            key="sidebar_roster_uploader",
            help="支援含『部門名稱』與『與會人員』欄位的 Excel、CSV 或 Markdown 檔案。",
        )
        if uploaded_roster is not None:
            if st.button("📥 執行批量匯入名冊", type="primary", key="btn_sidebar_import_roster"):
                depts_in, persons_in, msg = parse_organization_upload(
                    uploaded_roster.getvalue(),
                    uploaded_roster.name,
                )
                if depts_in or persons_in:
                    repo.save_org_directory(depts_in, persons_in, merge=True)
                    st.success(msg)
                    st.rerun()
                else:
                    st.warning(msg)

        with st.expander("📥 下載名冊匯入範本 (.xlsx/.csv/.md)", expanded=False):
            st.download_button(
                "📊 下載 Excel 範本 (.xlsx)",
                data=generate_sample_roster_xlsx(),
                file_name="org_roster_template.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_tpl_xlsx_sb",
            )
            st.download_button(
                "📄 下載 CSV 範本 (.csv)",
                data=generate_sample_roster_csv(),
                file_name="org_roster_template.csv",
                mime="text/csv",
                key="dl_tpl_csv_sb",
            )
            st.download_button(
                "📝 下載 Markdown 範本 (.md)",
                data=generate_sample_roster_md(),
                file_name="org_roster_template.md",
                mime="text/markdown",
                key="dl_tpl_md_sb",
            )

        # 5. 範例資料一鍵管理
        st.divider()
        st.markdown("### 📦 範例資料與快速體驗")
        if st.button("🌱 重新載入跨部門範例會議", key="btn_seed_samples"):
            loaded = repo.seed_sample_meetings(force=True)
            st.toast(f"已成功載入/更新 {loaded} 場跨部門 RACI+SMART+QCD+T 範例會議！", icon="✅")
            st.rerun()

        with st.expander("📖 管理框架速查指南 (RACI / SMART / QCD+T)", expanded=False):
            st.markdown(
                """
                - **RACI 鐵律**：
                  - **A (Accountable)**：最終當責者（**唯一 1 人**，跨部門任務亦須明確歸屬）。
                  - **R (Responsible)**：實際執行者（可多人）。
                  - **C / I**：應徵詢者 / 應被告知者。
                - **SMART 四階層級**：
                  - 嚴格區分：**企業目標**、**專案成果**、**工作任務**、**個別活動**。
                - **QCD+T 自訂擴充框架**：
                  - **Q**：品質與驗收條件
                  - **C**：成本與預算 (含 0 元方案)
                  - **D**：交付期限與里程碑
                  - **T (Truthfulness/Evidence)**：結案時必須提供可驗證證據！
                """
            )

    return is_unlocked
