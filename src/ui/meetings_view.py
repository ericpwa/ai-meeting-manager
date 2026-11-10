"""Tab 2：歷史會議檢索、決策明細、待辦事項狀態勾選更新與 QCD+T 成果佐證 (T) 閉環稽核視圖."""

from __future__ import annotations

import json
import streamlit as st

from src.repositories.meeting_repo import MeetingRepository
from src.schemas.models import ActionItem, MeetingRecord
from src.services.ai_service import audit_action_evidence
from src.services.governance import classify_action_traffic_light


def _export_meeting_markdown(meeting: MeetingRecord) -> str:
    """將單場會議匯出為結構化管理報告 Markdown."""
    lines = [
        f"# 📌 {meeting.title}",
        f"- **會議日期**：{meeting.meeting_date}",
        f"- **參與部門**：{', '.join(meeting.departments)}",
        f"- **出席人員**：{', '.join(meeting.attendees)}",
        "",
        "## 📝 高階執行摘要 (Executive Summary)",
        meeting.executive_summary,
        "",
        "## ⚖️ 關鍵決策清單 (Key Decisions)",
    ]
    for idx, dec in enumerate(meeting.key_decisions, start=1):
        lines.append(f"{idx}. {dec}")

    lines.append("")
    lines.append("## 🎯 待辦事項與 RACI + SMART + QCD+T 治理矩陣")
    for act in meeting.action_items:
        _, _, combined_light = classify_action_traffic_light(act)
        lines.extend(
            [
                f"### [{act.id}] {act.task_title} ({act.status} ｜ {combined_light})",
                f"- **主責部門**：{act.department} ｜ **截止日期**：{act.due_date}",
                f"- **RACI 矩陣**：**A (當責)**：{act.raci.accountable} ｜ **R (執行)**：{', '.join(act.raci.responsible)} ｜ **C (徵詢)**：{', '.join(act.raci.consulted)} ｜ **I (告知)**：{', '.join(act.raci.informed)}",
                f"- **SMART 目標 ({act.smart.hierarchy_level})**：具體性(S)：{act.smart.specific} ／ 衡量指標(M)：{act.smart.measurable}",
                f"- **QCD+T 管控**：",
                f"  - **Q (品質驗收)**：{act.qcdt.quality_criteria}",
                f"  - **C (成本預算)**：{act.qcdt.cost_budget}",
                f"  - **D (交付里程碑)**：{act.qcdt.delivery_milestone}",
                f"  - **T (證據要求)**：{act.qcdt.truthfulness_req}",
                f"  - **T (實際提交佐證)**：{act.qcdt.evidence_submitted or '尚未提交'}",
            ]
        )
        if act.governance_gaps:
            lines.append(f"- ⚠️ **治理缺口警示**：{'；'.join(act.governance_gaps)}")
        lines.append("")

    return "\n".join(lines)


def render_meetings_view(repo: MeetingRepository) -> None:
    """渲染歷史會議搜尋、篩選與待辦事項狀態勾選更新介面."""
    st.markdown("### 📚 歷史會議檢索與待辦事項閉環管理")
    st.caption(
        "支援全文搜尋、部門與待辦狀態篩選。勾選更新待辦事項為 **Done (已完成)** 時，"
        "系統將依循 **QCD+T** 規範檢核 **「T (Truthfulness/Evidence 成果佐證)」**，並支援一鍵 AI 佐證對照品質條件 (Q) 稽核。"
    )

    all_meetings = repo.list_meetings()
    org_depts, _ = repo.get_org_directory(include_from_meetings=True)
    all_depts: set[str] = set(org_depts)
    for m in all_meetings:
        for d in m.departments:
            all_depts.add(d)

    # 搜尋與篩選列
    f_col1, f_col2, f_col3 = st.columns([2.5, 1.5, 1.5])
    with f_col1:
        search_q = st.text_input(
            "🔍 搜尋會議標題、摘要、決策、當責者 (A) 或執行者 (R)",
            placeholder="輸入關鍵字，例如：資安、ERP、林雅婷、SaaS...",
            key="meetings_search_q",
        )
    with f_col2:
        dept_filter = st.selectbox(
            "🏢 部門篩選",
            options=["全部"] + sorted(all_depts),
            key="meetings_dept_filter",
        )
    with f_col3:
        status_filter = st.selectbox(
            "📌 包含待辦狀態",
            options=["全部", "Pending", "In Progress", "Blocked", "Done"],
            key="meetings_status_filter",
        )

    filtered_meetings = repo.list_meetings(
        search_query=search_q,
        department_filter=dept_filter,
        status_filter=status_filter,
    )

    if not filtered_meetings:
        st.info("查無符合篩選條件的會議記錄。您可調整篩選條件或由左側邊欄重新載入範例會議。")
        return

    st.markdown(f"共找到 **{len(filtered_meetings)}** 場會議記錄：")

    for m_idx, meeting in enumerate(filtered_meetings):
        done_cnt = sum(1 for a in meeting.action_items if a.status == "Done")
        total_cnt = len(meeting.action_items)
        gap_cnt = sum(len(a.governance_gaps) for a in meeting.action_items)

        badge_str = f"📅 {meeting.meeting_date} ｜ 🎯 完成度 {done_cnt}/{total_cnt}"
        if gap_cnt > 0:
            badge_str += f" ｜ ⚠️ {gap_cnt} 項治理缺口待補齊"
        else:
            badge_str += " ｜ ✅ 治理完整"

        with st.expander(f"📌 {meeting.title} （{badge_str}）", expanded=(m_idx == 0)):
            meta_c1, meta_c2, meta_c3 = st.columns([2, 2, 1.5])
            with meta_c1:
                st.markdown(f"**🏢 參與部門**：{', '.join(meeting.departments) or '未標註'}")
                st.markdown(f"**👥 出席人員**：{', '.join(meeting.attendees) or '未標註'}")
            with meta_c2:
                st.markdown(f"**📥 來源類型**：`{meeting.source_type}`")
                st.markdown(f"**🕒 最後更新**：`{meeting.updated_at}`")
            with meta_c3:
                md_export = _export_meeting_markdown(meeting)
                st.download_button(
                    "📥 匯出 Markdown 報告",
                    data=md_export.encode("utf-8"),
                    file_name=f"meeting_{meeting.meeting_date}_{meeting.id[:6]}.md",
                    mime="text/markdown",
                    key=f"dl_md_{meeting.id}",
                )
                json_export = json.dumps(meeting.model_dump(), ensure_ascii=False, indent=2)
                st.download_button(
                    "📥 匯出 JSON 結構檔",
                    data=json_export.encode("utf-8"),
                    file_name=f"meeting_{meeting.meeting_date}_{meeting.id[:6]}.json",
                    mime="application/json",
                    key=f"dl_json_{meeting.id}",
                )

            st.markdown("#### 📝 (b) 高階執行摘要")
            st.info(meeting.executive_summary)

            st.markdown("#### ⚖️ (c) 關鍵決策清單")
            for d_i, dec in enumerate(meeting.key_decisions, start=1):
                st.markdown(f"{d_i}. {dec}")

            st.markdown("#### ✅ (d) 待辦事項管理 (RACI + SMART + QCD+T 狀態勾選與佐證閉環)")
            for act in meeting.action_items:
                _render_action_item_card(repo, meeting, act)

            with st.expander("📄 檢視原始會議逐字稿", expanded=False):
                st.text(meeting.raw_transcript or "（無原始逐字稿紀錄）")


def _render_action_item_card(repo: MeetingRepository, meeting: MeetingRecord, act: ActionItem) -> None:
    """渲染單一待辦事項之互動管理卡片（含四色燈號預警、快速勾選 Done、T 佐證閉環與 AI 稽核）."""
    uid = f"{meeting.id}_{act.id}"
    _, _, combined_light = classify_action_traffic_light(act)
    status_icon = {
        "Done": "✅",
        "In Progress": "⏳",
        "Blocked": "🛑",
        "Pending": "📝",
    }.get(act.status, "📝")

    with st.container(border=True):
        top_c1, top_c2, top_c3 = st.columns([3.2, 1.5, 1.3])
        with top_c1:
            st.markdown(f"**{status_icon} [{act.id}] {act.task_title}**")
            st.caption(
                f"🚦 **燈號預警**：`{combined_light}` ｜ 🏷️ **SMART**：`{act.smart.hierarchy_level}` ｜ 🏢 **部門**：{act.department} ｜ 📅 **截止日**：`{act.due_date}`"
            )
        with top_c2:
            st.markdown(f"👑 **當責者 (A)**：`{act.raci.accountable}`")
            st.caption(f"🛠️ **執行者 (R)**：{', '.join(act.raci.responsible) or '待指定'}")
        with top_c3:
            is_done_checked = st.checkbox(
                "勾選完成 (Done)",
                value=(act.status == "Done"),
                key=f"chk_done_{uid}",
                help="勾選後請確認下方已填寫 T (成果佐證)，再點擊『儲存更新』完成閉環。",
            )

        # 顯示管理缺口警示
        if act.governance_gaps:
            for gap in act.governance_gaps:
                st.warning(gap)

        # RACI / SMART / QCD+T 詳細資訊折疊與編輯區
        with st.expander("🔍 展開 / 更新 RACI、SMART、QCD+T 成果佐證與狀態", expanded=(act.status != "Done" and bool(act.governance_gaps))):
            st.markdown(
                f"- **RACI 完整歸屬**：**A (當責)**：`{act.raci.accountable}` ｜ "
                f"**R (執行)**：`{', '.join(act.raci.responsible)}` ｜ "
                f"**C (徵詢)**：`{', '.join(act.raci.consulted) or '無'}` ｜ "
                f"**I (告知)**：`{', '.join(act.raci.informed) or '無'}`\n"
                f"- **SMART 檢核**：\n"
                f"  - **S (具體)**：{act.smart.specific or '未填'}\n"
                f"  - **M (可衡量)**：{act.smart.measurable or '未填'}\n"
                f"  - **A (可達成)**：{act.smart.achievable or '未填'} ／ **R (相關性)**：{act.smart.relevant or '未填'}\n"
                f"- **QCD+T 管控規格**：\n"
                f"  - **Q (品質驗收條件)**：{act.qcdt.quality_criteria or '未定義'}\n"
                f"  - **C (成本與預算)**：{act.qcdt.cost_budget}\n"
                f"  - **D (交付里程碑)**：{act.qcdt.delivery_milestone or '未定義'}\n"
                f"  - **T (證據規格要求)**：{act.qcdt.truthfulness_req or '未定義'}"
            )

            status_options = ["Pending", "In Progress", "Blocked", "Done"]
            default_status = "Done" if is_done_checked else (act.status if act.status != "Done" else "In Progress")
            s_idx = status_options.index(default_status) if default_status in status_options else 0

            ed_c1, ed_c2, ed_c3, ed_c4 = st.columns([1.3, 1.7, 1.8, 1.3])
            with ed_c1:
                new_status = st.selectbox(
                    "更新執行狀態",
                    options=status_options,
                    index=s_idx,
                    key=f"sel_status_{uid}",
                )
            with ed_c2:
                new_acc = st.text_input(
                    "更新最終當責者 (A - 唯一單人)",
                    value=act.raci.accountable,
                    key=f"inp_acc_{uid}",
                )
            with ed_c3:
                new_resp = st.text_input(
                    "更新實際執行者 (R - 逗號分隔)",
                    value=", ".join(act.raci.responsible),
                    key=f"inp_resp_{uid}",
                )
            with ed_c4:
                new_due = st.text_input(
                    "更新截止日 (YYYY-MM-DD)",
                    value=act.due_date,
                    key=f"inp_due_{uid}",
                )

            q_c1, q_c2 = st.columns(2)
            with q_c1:
                new_q = st.text_input(
                    "補齊/更新 Q (品質驗收條件)",
                    value=act.qcdt.quality_criteria,
                    key=f"inp_q_{uid}",
                )
            with q_c2:
                new_t_req = st.text_input(
                    "補齊/更新 T (可驗證證據規格要求)",
                    value=act.qcdt.truthfulness_req,
                    key=f"inp_t_req_{uid}",
                )

            new_evidence = st.text_area(
                "📑 T (Truthfulness/Evidence 實際提交之成果佐證：請填寫 PR 連結、文件 URL、測試報告數據或簽核紀錄)",
                value=act.qcdt.evidence_submitted,
                height=75,
                placeholder="當狀態設為 Done 時必填！例如：https://github.com/org/repo/pull/42 ，壓測通過率 100%...",
                key=f"inp_evidence_{uid}",
            )

            if act.qcdt.evidence_audit_feedback:
                if act.qcdt.evidence_verified:
                    st.success(act.qcdt.evidence_audit_feedback)
                else:
                    st.warning(act.qcdt.evidence_audit_feedback)

            btn_c1, btn_c2 = st.columns([1.5, 2])
            with btn_c1:
                if st.button("💾 儲存任務狀態與佐證更新", type="primary", key=f"btn_save_act_{uid}"):
                    parsed_resp = [r.strip() for r in new_resp.split(",") if r.strip()]
                    ok, msg, _ = repo.update_action_item(
                        meeting_id=meeting.id,
                        action_id=act.id,
                        new_status=new_status,
                        evidence_submitted=new_evidence,
                        accountable=new_acc,
                        responsible=parsed_resp,
                        due_date=new_due,
                        quality_criteria=new_q,
                        truthfulness_req=new_t_req,
                        enforce_evidence_on_done=True,
                    )
                    if ok:
                        st.toast(msg, icon="✅")
                        st.rerun()
                    else:
                        st.error(msg)

            with btn_c2:
                if st.button("🤖 AI 稽核成果佐證 (比對 T 佐證 vs Q 品質條件)", key=f"btn_audit_ev_{uid}"):
                    parsed_resp = [r.strip() for r in new_resp.split(",") if r.strip()]
                    temp_item = act.model_copy(deep=True)
                    temp_item.qcdt.quality_criteria = new_q
                    temp_item.qcdt.truthfulness_req = new_t_req
                    audit_res, _ = audit_action_evidence(temp_item, new_evidence)
                    feedback_str = f"{'✅ 通過' if audit_res.is_verified else '⚠️ 待補強'} (評分 {audit_res.audit_score}/100)：{audit_res.feedback}"
                    repo.update_action_item(
                        meeting_id=meeting.id,
                        action_id=act.id,
                        new_status=new_status if (new_status != "Done" or audit_res.is_verified) else act.status,
                        evidence_submitted=new_evidence,
                        accountable=new_acc,
                        responsible=parsed_resp,
                        due_date=new_due,
                        quality_criteria=new_q,
                        truthfulness_req=new_t_req,
                        evidence_verified=audit_res.is_verified,
                        evidence_audit_feedback=feedback_str,
                        enforce_evidence_on_done=False,
                    )
                    st.rerun()
