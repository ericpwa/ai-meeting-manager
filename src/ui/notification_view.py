"""Tab 4：跨部門主動催辦與通知中心 (`src/ui/notification_view.py`).

核心功能：
1. 自動巡檢全公司會議中「🚨 逾期未完成」、「🛑 執行受阻 (Blocked)」、「⚠️ 治理缺口待補齊」與「⏳ 3日內即將到期」任務。
2. 依 RACI 原則按「👑 最終當責者 A (Accountable)」分群檢視，確保催辦必找當責者 A、副知執行者 R。
3. 支援一鍵切換產出 **📧 Email 正式催辦稽核信**、**💬 Slack / Teams 頻道標註訊息**、**📱 LINE 精簡行動卡片**。
4. 支援選擇催辦語氣（溫和提醒 ／ 嚴謹稽核 ／ 高階升級預警 Escalation）並由 Gemini AI 潤飾。
5. 支援一鍵 Webhook 推播（或安全 Dry-run 模擬發送）並留存催辦稽核紀錄。
"""

from __future__ import annotations

import datetime
import streamlit as st

from src.config import (
    get_line_channel_access_token,
    get_line_target_id,
    get_webhook_url,
    is_line_messaging_configured,
    mask_secret,
)
from src.repositories.meeting_repo import MeetingRepository
from src.services.notification_service import (
    build_line_share_payload,
    dispatch_line_messaging_push,
    dispatch_webhook_notification,
    fetch_line_bot_quota,
    generate_channel_message,
    group_by_accountable,
    polish_reminder_with_ai,
    scan_followup_targets,
)


def render_notification_view(repo: MeetingRepository) -> None:
    """渲染跨部門主動催辦與通知中心視圖."""
    st.markdown("### 🔔 跨部門主動催辦與當責通知中心 (Proactive Accountability & Reminder Engine)")
    st.caption(
        "自動巡檢所有會議中之**逾期任務**、**受阻任務**與**治理缺口**，依 **RACI 唯一最終當責者 (A)** 自動分群，"
        "一鍵產出 **Email / Slack / Teams / LINE** 催辦通知或透過 Webhook 即時推播。"
    )

    meetings = repo.list_meetings()
    all_entries = scan_followup_targets(meetings)
    groups = group_by_accountable(all_entries)

    overdue_total = sum(1 for e in all_entries if e.urgency_category == "🚨 逾期未完成")
    blocked_total = sum(1 for e in all_entries if e.urgency_category == "🛑 執行受阻 (Blocked)")
    gap_total = sum(1 for e in all_entries if e.urgency_category == "⚠️ 治理缺口待補齊")
    due_soon_total = sum(1 for e in all_entries if e.urgency_category == "⏳ 3日內即將到期")

    # 1. 巡檢摘要指標卡
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("🔔 需催辦總任務", f"{len(all_entries)} 項")
    m2.metric("👑 涉及當責者 (A)", f"{len(groups)} 位")
    m3.metric("🚨 逾期未完成", f"{overdue_total} 項")
    m4.metric("🛑 執行受阻 (Blocked)", f"{blocked_total} 項")
    m5.metric("⚠️ 治理缺口 / ⏳ 即將到期", f"{gap_total} / {due_soon_total} 項")

    st.divider()

    if not all_entries:
        st.success("🎉 太棒了！目前所有會議任務皆按期推進且無任何 RACI / SMART / QCD+T 治理缺口，無須發送催辦通知。")
        return

    # 2. 依當責者 A 分群總覽折疊面板
    with st.expander("👑 檢視依「最終當責者 A (Accountable)」分群之待催辦責任清單", expanded=True):
        cols = st.columns(min(len(groups), 3) or 1)
        for idx, grp in enumerate(groups):
            with cols[idx % len(cols)]:
                with st.container(border=True):
                    st.markdown(f"#### 👤 `{grp.accountable}`")
                    st.caption(f"🏢 涉及部門：{', '.join(grp.departments) or '跨部門'}")
                    st.markdown(
                        f"- 🚨 逾期：**{grp.overdue_count}** 件 ｜ 🛑 受阻：**{grp.blocked_count}** 件\n"
                        f"- ⚠️ 治理缺口：**{grp.gap_count}** 件 ｜ ⏳ 即將到期：**{grp.due_soon_count}** 件"
                    )
                    for item in grp.items:
                        light_tag = "🔴 紅燈" if item.urgency_category in {"🚨 逾期未完成", "🛑 執行受阻 (Blocked)"} else "🟡 黃燈"
                        st.markdown(
                            f"  - `{item.action_id}` {item.task_title[:22]}... ({light_tag}｜{item.urgency_category})"
                        )

    st.markdown("#### ✉️ 催辦訊息產生器 & Webhook 自動推播工作台")

    _, org_persons = repo.get_org_directory(include_from_meetings=True)
    merged_accountables = list(dict.fromkeys([g.accountable for g in groups] + org_persons))
    accountable_options = ["全體當責人 (跨部門總表)"] + merged_accountables
    urgency_options = [
        "全部待催辦項目 (紅燈＋黃燈)",
        "🚨 僅逾期與受阻項目 (🔴 紅燈高優先級)",
        "⚠️ 僅存在治理缺口項目 (🟡 黃燈要求補齊 A / Q / T)",
        "⏳ 僅 3日內即將到期項目 (🟡 黃燈到期預警)",
    ]

    c_sel1, c_sel2, c_sel3, c_sel4 = st.columns([2, 2, 1.8, 1.8])
    with c_sel1:
        selected_acc = st.selectbox(
            "1️⃣ 選擇催辦對象 (最終當責者 A)",
            options=accountable_options,
            key="notif_sel_accountable",
        )
    with c_sel2:
        selected_urgency = st.selectbox(
            "2️⃣ 篩選催辦範圍",
            options=urgency_options,
            key="notif_sel_urgency",
        )
    with c_sel3:
        selected_channel_label = st.selectbox(
            "3️⃣ 通知通道格式",
            options=[
                "💬 Slack / Microsoft Teams 群組標註",
                "📧 Email 正式當責稽核信",
                "📱 LINE / 即時通訊精簡行動卡",
            ],
            key="notif_sel_channel",
        )
    with c_sel4:
        selected_tone = st.selectbox(
            "4️⃣ 管理催辦語氣",
            options=[
                "嚴謹稽核 (Audit)",
                "溫和提醒 (Friendly)",
                "高階升級預警 (Escalation)",
            ],
            key="notif_sel_tone",
        )

    # 根據選擇過濾 entries
    target_entries = all_entries
    target_label = "全體當責人"
    if not selected_acc.startswith("全體當責人"):
        target_entries = [e for e in target_entries if e.accountable == selected_acc]
        target_label = selected_acc

    if selected_urgency.startswith("🚨"):
        target_entries = [
            e for e in target_entries if e.urgency_category in {"🚨 逾期未完成", "🛑 執行受阻 (Blocked)"}
        ]
    elif selected_urgency.startswith("⚠️"):
        target_entries = [e for e in target_entries if e.governance_gaps]
    elif selected_urgency.startswith("⏳"):
        target_entries = [e for e in target_entries if e.urgency_category == "⏳ 3日內即將到期"]

    channel_code = "slack_teams"
    if selected_channel_label.startswith("📧"):
        channel_code = "email"
    elif selected_channel_label.startswith("📱"):
        channel_code = "line"

    generated_msg = generate_channel_message(
        entries=target_entries,
        channel=channel_code,  # type: ignore[arg-type]
        tone=selected_tone,  # type: ignore[arg-type]
        target_accountable=target_label,
    )

    # 如果使用者點擊了 AI 潤飾，使用潤飾後內容，否則隨選單即時更新
    state_signature = f"{selected_acc}|{selected_urgency}|{channel_code}|{selected_tone}"
    if st.session_state.get("notif_last_signature") != state_signature:
        st.session_state["notif_last_signature"] = state_signature
        st.session_state["notif_message_editor"] = generated_msg

    btn_col1, btn_col2, btn_col3 = st.columns([1.6, 2.0, 2.4])
    with btn_col1:
        if st.button("🤖 AI 智慧語氣潤飾 (Gemini)", key="btn_notif_ai_polish"):
            with st.spinner("正在透過 Gemini 潤飾催辦文案..."):
                polished, _, msg = polish_reminder_with_ai(
                    base_message=generated_msg,
                    tone=selected_tone,
                )
                st.session_state["notif_message_editor"] = polished
                st.session_state["notif_status_banner"] = msg

    with btn_col2:
        if st.button("🚀 發送 Webhook 催辦推播 (Slack/Teams/LINE)", type="primary", key="btn_notif_dispatch_webhook"):
            current_msg_to_send = st.session_state.get("notif_message_editor", generated_msg)
            ok, dispatch_msg = dispatch_webhook_notification(current_msg_to_send)
            st.session_state["notif_dispatch_ok"] = ok
            st.session_state["notif_dispatch_msg"] = dispatch_msg

            # 記錄至催辦發送稽核日誌
            if "notification_dispatch_logs" not in st.session_state:
                st.session_state["notification_dispatch_logs"] = []
            st.session_state["notification_dispatch_logs"].insert(
                0,
                {
                    "發送時間": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "催辦對象 (A)": target_label,
                    "通知通道": selected_channel_label,
                    "催辦語氣": selected_tone,
                    "涵蓋任務數": len(target_entries),
                    "發送狀態": "✅ 成功" if ok else "❌ 失敗",
                    "結果說明": dispatch_msg,
                },
            )

    with btn_col3:
        current_txt = st.session_state.get("notif_message_editor", generated_msg)
        st.download_button(
            "📥 下載催辦通知文案 (.md / .txt)",
            data=current_txt.encode("utf-8"),
            file_name=f"followup_{channel_code}_{datetime.date.today().isoformat()}.md",
            mime="text/markdown",
            key="btn_dl_notif_text",
        )

    if "notif_status_banner" in st.session_state:
        st.info(st.session_state["notif_status_banner"])

    if "notif_dispatch_msg" in st.session_state:
        if st.session_state.get("notif_dispatch_ok", True):
            st.success(st.session_state["notif_dispatch_msg"])
        else:
            st.error(st.session_state["notif_dispatch_msg"])

    wh_url = get_webhook_url()
    if wh_url:
        st.caption(f"🔗 目前已綁定外部 Webhook URL：`{mask_secret(wh_url)}`")
    else:
        st.caption("💡 提示：可於左側邊欄「🔔 進階：跨部門催辦 Webhook & LINE BYOK 設定」填入 Slack / Teams / Discord Webhook 或 LINE Messaging API 憑證。")

    # 📱 當通道選為 LINE 時，顯示專屬「0 元開通雙軌 LINE 傳送與機器人推播工作區」
    if channel_code == "line":
        current_line_msg = st.session_state.get("notif_message_editor", generated_msg)
        line_share_url, _, share_was_shortened = build_line_share_payload(
            current_line_msg,
            entries=target_entries,
            target_accountable=target_label,
        )
        line_token = get_line_channel_access_token()
        default_line_target = get_line_target_id()

        with st.container(border=True):
            st.markdown("##### 📱 LINE 精簡行動卡 0 元開通發送中心（雙軌免付費方案）")
            st.caption(
                "⚠️ 註：舊版 LINE Notify 已於 2025/03/31 退場。本系統全面採用 2026 官方現役雙軌方案："
                "**① 0 元永久免費無上限「LINE 一鍵分享傳送」** 與 **② 0 元輕用量每月 200 則「LINE Messaging API 官方機器人推播」**。"
            )

            ln_c1, ln_c2 = st.columns([1.6, 2.4])
            with ln_c1:
                st.markdown("**🌟 方案 ①：0 元無限則數・零設定（推薦立即可用）**")
                st.link_button(
                    "📲 一鍵開啟 LINE 傳送至群組／個人（0 元無上限）",
                    url=line_share_url,
                    type="primary",
                    width="stretch",
                )
                if share_was_shortened:
                    st.caption(
                        "🛡️ 系統已自動將網址內容濃縮為 **LINE 伺服器安全長度摘要版**（徹底杜絕 `414` 錯誤）；"
                        "若需傳送完整長版明細，請直接點擊下方 **「📋 一鍵複製完整行動卡」** 貼到 LINE，或使用右側 **方案 ② 機器人推播**！"
                    )
                else:
                    st.caption("點擊後直接開啟手機／電腦版 LINE 並自動填入行動卡，挑選同事或群組按送出即可（不管群組幾人皆 0 元）。")

            with ln_c2:
                st.markdown("**🤖 方案 ②：LINE 官方機器人自動推播（0 元每月 200 則）**")
                line_opt1, line_opt2 = st.columns([1.4, 1.6])
                with line_opt1:
                    use_flex = st.checkbox(
                        "🎨 傳送彩色 Flex 互動行動卡（推薦）",
                        value=True,
                        key="notif_line_use_flex",
                        help="勾選後 LINE 會收到帶有深藍標題、紅/黃燈號與 RACI/QCD+T 結構排版的美觀彩色行動卡；取消勾選則傳送下方純文字。",
                    )
                with line_opt2:
                    override_target = st.text_input(
                        "本次推播目標 ID (留空沿用側邊欄設定)",
                        value=default_line_target,
                        placeholder="U... (個人) 或 C... (群組)，多筆用逗號隔開",
                        key="notif_line_target_override",
                        label_visibility="collapsed",
                    )

                effective_target = override_target.strip() or default_line_target

                lbtn1, lbtn2 = st.columns([1.7, 1.3])
                with lbtn1:
                    if st.button(
                        "📱 發送 LINE 官方機器人推播 (Messaging API)",
                        type="primary",
                        key="btn_notif_dispatch_line",
                    ):
                        ok_ln, msg_ln = dispatch_line_messaging_push(
                            message_text=current_line_msg,
                            entries=target_entries,
                            target_accountable=target_label,
                            tone=selected_tone,
                            use_flex_card=use_flex,
                            target_id=effective_target,
                        )
                        st.session_state["notif_dispatch_ok"] = ok_ln
                        st.session_state["notif_dispatch_msg"] = msg_ln
                        if "notification_dispatch_logs" not in st.session_state:
                            st.session_state["notification_dispatch_logs"] = []
                        st.session_state["notification_dispatch_logs"].insert(
                            0,
                            {
                                "發送時間": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "催辦對象 (A)": target_label,
                                "通知通道": "📱 LINE Messaging API (" + ("Flex 彩色卡" if use_flex else "純文字") + ")",
                                "催辦語氣": selected_tone,
                                "涵蓋任務數": len(target_entries),
                                "發送狀態": "✅ 成功" if ok_ln else "❌ 失敗",
                                "結果說明": msg_ln,
                            },
                        )
                        st.rerun()

                with lbtn2:
                    if st.button("🔍 驗證連線與剩餘額度", key="btn_check_line_quota"):
                        _, _, q_msg = fetch_line_bot_quota()
                        st.session_state["notif_line_quota_msg"] = q_msg

                if line_token and effective_target:
                    st.caption(
                        f"🟢 LINE 機器人憑證已就緒（Token：`{mask_secret(line_token)}` ｜ 目標：`{mask_secret(effective_target)}`）"
                    )
                elif line_token:
                    st.caption(
                        f"🟡 已填入 Token (`{mask_secret(line_token)}`)，請於上方格子或側邊欄再填入目標 ID (`U...` 或 `C...`) 即可發送！"
                    )
                else:
                    st.caption("ℹ️ 尚未設定 LINE 憑證：按推播將執行安全模擬 (Dry-Run)；可於左側邊欄填入免費官方帳號 Token 開通真實推播。")

                if "notif_line_quota_msg" in st.session_state:
                    st.info(st.session_state["notif_line_quota_msg"])

            with st.expander(
                "📋 一鍵複製完整純文字行動卡（不受網址長度限制，點擊右上角複製圖示直接貼到 LINE）",
                expanded=share_was_shortened,
            ):
                st.code(current_line_msg, language=None)

            with st.expander("📖 新手小白開通教學 ＆ 2026 LINE 免費／付費成本速查", expanded=False):
                st.markdown(
                    r"""
                    - **最快 0 元免設定用法**：直接點擊上方 **「📲 一鍵開啟 LINE 傳送至群組／個人」**，或展開「📋 一鍵複製純文字行動卡」貼到 LINE 群組，**永久 0 元、無則數上限**！
                    - **想開通「機器人自動直推」(0 元輕用量每月 200 則)**：
                      1. 免費建立 LINE 官方帳號（[LINE Official Account Manager](https://manager.line.biz/)）並開啟 **Messaging API**。
                      2. 到 [LINE Developers Console](https://developers.line.biz/console/) 複製 **Channel access token (long-lived)** 與目標 **User ID (`U...`) / Group ID (`C...`)**。
                      3. 貼入左側邊欄「🔔 進階：跨部門催辦 Webhook & LINE BYOK 設定」即可一鍵發送彩色 Flex 行動卡！
                    - **💡 2026/11 最新台灣 LINE 費率與省額度秘技**：
                      - **輕用量（免費）**：**NT\$0 / 月**（每月 200 則，不可加購）。
                      - **中用量**：**NT\$1,000 / 月**（未稅，3,000 則）；**高用量**：**NT\$1,400 / 月**（未稅，6,000 則，超量每則 NT\$0.20 起）。
                      - **省錢鐵律**：LINE 推播至群組是以「`群組人數 × 發送次數`」扣額度；建議改用 **私訊單獨推播給「👑 最終當責者 A」**（1 人只扣 1 則，每週催 10 位主管 1 個月僅耗 40 則，**0 元免費額度綽綽有餘**！），大群組公告則用「📲 一鍵開啟 LINE 分享」完全免費！
                    """
                )

    edited_msg = st.text_area(
        "📝 催辦通知文案預覽與微調（可直接複製貼上至 Email / Slack / Teams / LINE，或點擊上方按鈕自動推播）",
        height=320,
        key="notif_message_editor",
    )

    with st.expander("👁️ Markdown 渲染視覺預覽", expanded=False):
        st.markdown(edited_msg)

    if st.session_state.get("notification_dispatch_logs"):
        st.divider()
        st.markdown("#### 📜 本次工作階段催辦發送稽核紀錄 (Audit Trail)")
        st.dataframe(st.session_state["notification_dispatch_logs"], height=180)
