"""Tab 3：跨會議「全域行動方案追蹤看板 (Global Action Tracker)」視圖.

提供企業跨部門治理視角：
- 全域 KPI 指標卡（總會議數、總任務數、完成率、逾期任務數、管理缺口數、已驗證 T 佐證數）
- 依當責者 (A)、執行者 (R)、部門、SMART 目標層級、執行狀態、管理缺口狀態進行交叉篩選
- 支援一鍵匯出全域 RACI + SMART + QCD+T 追蹤報表 (CSV)
"""

from __future__ import annotations

import datetime
import re
import pandas as pd
import streamlit as st

from src.repositories.meeting_repo import MeetingRepository
from src.services.governance import compute_governance_metrics


def render_tracker_view(repo: MeetingRepository) -> None:
    """渲染跨會議全域行動方案追蹤看板."""
    st.markdown("### 📊 跨會議「全域行動方案追蹤看板 (Global Action Tracker)」")
    st.caption(
        "彙整企業所有會議之待辦事項，以 **RACI 當責歸屬**、**SMART 目標層級** 與 **QCD+T 真實性佐證** 進行跨部門治理監控。"
    )

    meetings = repo.list_meetings()
    metrics = compute_governance_metrics(meetings)

    # 1. 頂部管理 KPI 指標卡
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("📁 納管會議數", f"{metrics['total_meetings']} 場")
    k2.metric("🎯 總行動任務", f"{metrics['total_actions']} 項")
    k3.metric("✅ 任務完成率", f"{metrics['completion_rate']}%", f"{metrics['done_actions']} 項已完成")
    k4.metric("⏰ 逾期未完任務", f"{metrics['overdue_actions']} 項")
    k5.metric("⚠️ 存在治理缺口", f"{metrics['actions_with_gaps']} 項")
    k6.metric("🛡️ 治理健康度", f"{metrics['governance_health_rate']}%")

    st.divider()

    # 展開所有任務為平面清單
    rows: list[dict[str, str | int | bool]] = []
    accountables_set: set[str] = set()
    responsibles_set: set[str] = set()
    depts_set: set[str] = set()
    smart_levels_set: set[str] = set()

    today_iso = datetime.date.today().isoformat()

    for m in meetings:
        for act in m.action_items:
            accountables_set.add(act.raci.accountable)
            for r in act.raci.responsible:
                responsibles_set.add(r)
            depts_set.add(act.department)
            smart_levels_set.add(act.smart.hierarchy_level)

            is_overdue = (
                act.status != "Done"
                and bool(re.match(r"^\d{4}-\d{2}-\d{2}$", act.due_date.strip()))
                and act.due_date.strip() < today_iso
            )

            rows.append(
                {
                    "會議日期": m.meeting_date,
                    "來源會議": m.title,
                    "任務編號": act.id,
                    "待辦事項名稱": act.task_title,
                    "狀態": act.status,
                    "是否逾期": "🚨 逾期" if is_overdue else "正常",
                    "主責/跨部門": act.department,
                    "A (最終當責者)": act.raci.accountable,
                    "R (實際執行者)": ", ".join(act.raci.responsible),
                    "SMART 層級": act.smart.hierarchy_level,
                    "截止日 (D)": act.due_date,
                    "Q (品質驗收條件)": act.qcdt.quality_criteria,
                    "C (成本預算)": act.qcdt.cost_budget,
                    "T (證據要求)": act.qcdt.truthfulness_req,
                    "T (已提交佐證)": act.qcdt.evidence_submitted or "尚未提交",
                    "佐證已驗證": "✅ 是" if act.qcdt.evidence_verified else "⏳ 否",
                    "治理缺口數": len(act.governance_gaps),
                    "治理缺口明細": "；".join(act.governance_gaps) if act.governance_gaps else "✅ 完整合規",
                }
            )

    if not rows:
        st.info("目前尚無行動方案資料。")
        return

    # 2. 多維度交叉篩選器
    f1, f2, f3, f4, f5 = st.columns(5)
    with f1:
        sel_a = st.selectbox("👑 當責者 (A) 篩選", options=["全部"] + sorted(accountables_set), key="trk_filter_a")
    with f2:
        sel_r = st.selectbox("🛠️ 執行者 (R) 篩選", options=["全部"] + sorted(responsibles_set), key="trk_filter_r")
    with f3:
        sel_dept = st.selectbox("🏢 部門篩選", options=["全部"] + sorted(depts_set), key="trk_filter_dept")
    with f4:
        sel_lvl = st.selectbox("🏷️ SMART 層級", options=["全部"] + sorted(smart_levels_set), key="trk_filter_lvl")
    with f5:
        sel_health = st.selectbox(
            "🩺 治理與逾期狀態",
            options=["全部", "⚠️ 僅顯示有治理缺口", "🚨 僅顯示逾期任務", "✅ 僅顯示已完成 (Done)", "⏳ 僅顯示未完成"],
            key="trk_filter_health",
        )

    filtered_rows = []
    for r in rows:
        if sel_a != "全部" and r["A (最終當責者)"] != sel_a:
            continue
        if sel_r != "全部" and sel_r not in str(r["R (實際執行者)"]):
            continue
        if sel_dept != "全部" and sel_dept not in str(r["主責/跨部門"]):
            continue
        if sel_lvl != "全部" and r["SMART 層級"] != sel_lvl:
            continue
        if sel_health == "⚠️ 僅顯示有治理缺口" and int(r["治理缺口數"]) == 0:
            continue
        if sel_health == "🚨 僅顯示逾期任務" and r["是否逾期"] != "🚨 逾期":
            continue
        if sel_health == "✅ 僅顯示已完成 (Done)" and r["狀態"] != "Done":
            continue
        if sel_health == "⏳ 僅顯示未完成" and r["狀態"] == "Done":
            continue
        filtered_rows.append(r)

    df = pd.DataFrame(filtered_rows)

    col_info, col_dl = st.columns([3, 1])
    with col_info:
        st.markdown(f"#### 📋 篩選結果：共 **{len(filtered_rows)}** 項行動方案")
    with col_dl:
        csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "📥 匯出全域追蹤報表 (CSV)",
            data=csv_bytes,
            file_name=f"global_action_tracker_{today_iso}.csv",
            mime="text/csv",
            key="btn_dl_global_csv",
        )

    st.dataframe(df, height=420)
