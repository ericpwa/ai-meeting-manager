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

from src.config import get_webhook_url, mask_secret
from src.repositories.meeting_repo import MeetingRepository
from src.services.notification_service import (
    dispatch_webhook_notification,
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
        st.caption("💡 提示：可於左側邊欄「🔔 跨部門通知 Webhook BYOK 設定」填入 Slack / Teams / Discord Webhook URL，即可一鍵真實推播至企業頻道。")

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
