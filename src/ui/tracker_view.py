"""Tab 3：跨會議「全域行動方案追蹤看板 (Global Action Tracker)」視圖.

提供企業跨部門治理視角：
- 全域 KPI 指標卡與四色燈號預警統計（🔴 紅燈、🟡 黃燈、🔵 藍燈、🟢 綠燈）
- 支援批量匯入「部門名稱」與「與會人員」（.xlsx / .csv / .md），自動同步至「👑 當責者 (A) 篩選」、「🛠️ 執行者 (R) 篩選」與「🏢 部門篩選」選單
- 「📋 篩選結果」列表內建四色「燈號預警」與「🩺 治理與逾期狀態」欄位：
  - 🔴 紅燈：🚨 逾期未完成 ／ 🛑 執行受阻 (Blocked)
  - 🟡 黃燈：⚠️ 治理缺口 ／ ⏳ 即將到期
  - 🔵 藍燈：⏳ 未完成/進行中
  - 🟢 綠燈：✅ 已完成 (Done)
- 支援一鍵匯出全域 RACI + SMART + QCD+T 追蹤報表 (CSV)
"""

from __future__ import annotations

import datetime
import pandas as pd
import streamlit as st

from src.repositories.meeting_repo import MeetingRepository
from src.services.governance import classify_action_traffic_light, compute_governance_metrics
from src.services.org_directory_service import (
    generate_sample_roster_csv,
    generate_sample_roster_md,
    generate_sample_roster_xlsx,
    parse_organization_upload,
)
from src.ui.theme import render_traffic_light_neon_strip


def _style_traffic_light_cell(val: object) -> str:
    """為 DataFrame 之燈號預警與治理狀態儲存格套用高辨識度背景色彩."""
    s = str(val)
    if "🔴" in s or "逾期未完成" in s or "執行受阻" in s:
        return "background-color: #FEE2E2; color: #991B1B; font-weight: 600;"
    if "🟡" in s or "治理缺口" in s or "即將到期" in s:
        return "background-color: #FEF3C7; color: #92400E; font-weight: 600;"
    if "🔵" in s or "未完成/進行中" in s:
        return "background-color: #DBEAFE; color: #1E40AF; font-weight: 600;"
    if "🟢" in s or "已完成 (Done)" in s:
        return "background-color: #DCFCE7; color: #166534; font-weight: 600;"
    return ""


def render_tracker_view(repo: MeetingRepository) -> None:
    """渲染跨會議全域行動方案追蹤看板."""
    st.markdown("### 📊 跨會議「全域行動方案追蹤看板 (Global Action Tracker)」")
    st.caption(
        "彙整企業所有會議之待辦事項，以 **四色燈號預警（紅/黃/藍/綠燈）**、**RACI 當責歸屬**、**SMART 目標層級** 與 **QCD+T 真實性佐證** 進行跨部門治理監控。"
    )

    meetings = repo.list_meetings()
    metrics = compute_governance_metrics(meetings)
    org_depts, org_persons = repo.get_org_directory(include_from_meetings=True)

    # 1. 頂部管理 KPI 指標卡
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("📁 納管會議數", f"{metrics['total_meetings']} 場")
    k2.metric("🎯 總行動任務", f"{metrics['total_actions']} 項")
    k3.metric("✅ 任務完成率", f"{metrics['completion_rate']}%", f"{metrics['done_actions']} 項已完成")
    k4.metric("⏰ 逾期未完任務", f"{metrics['overdue_actions']} 項")
    k5.metric("⚠️ 存在治理缺口", f"{metrics['actions_with_gaps']} 項")
    k6.metric("🛡️ 治理健康度", f"{metrics['governance_health_rate']}%")

    # 2. 批量匯入「部門名稱」與「與會人員」快捷面板
    with st.expander("👥 批量匯入「部門名稱」與「與會人員」名冊（支援上傳 .xlsx / .csv / .md，自動擴充下方 A / R / 部門篩選選單）", expanded=False):
        imp_c1, imp_c2 = st.columns([2.2, 1.8])
        with imp_c1:
            tracker_roster_file = st.file_uploader(
                "選擇包含『部門名稱』與『與會人員』之檔案 (.xlsx, .csv, .md)",
                type=["xlsx", "csv", "md"],
                key="tracker_roster_uploader",
            )
            if tracker_roster_file is not None:
                if st.button("🚀 立即匯入並同步至篩選選單", type="primary", key="btn_tracker_import_roster"):
                    depts_in, persons_in, msg = parse_organization_upload(
                        tracker_roster_file.getvalue(),
                        tracker_roster_file.name,
                    )
                    if depts_in or persons_in:
                        repo.save_org_directory(depts_in, persons_in, merge=True)
                        st.success(msg)
                        st.rerun()
                    else:
                        st.warning(msg)
        with imp_c2:
            st.markdown("**📥 下載標準匯入範本檔**")
            st.caption(f"目前名冊共納管：**{len(org_depts)} 個部門**、**{len(org_persons)} 位與會人員**")
            dl1, dl2, dl3 = st.columns(3)
            with dl1:
                st.download_button(
                    "📊 .xlsx 範本",
                    data=generate_sample_roster_xlsx(),
                    file_name="org_roster_template.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dl_tpl_xlsx_trk",
                )
            with dl2:
                st.download_button(
                    "📄 .csv 範本",
                    data=generate_sample_roster_csv(),
                    file_name="org_roster_template.csv",
                    mime="text/csv",
                    key="dl_tpl_csv_trk",
                )
            with dl3:
                st.download_button(
                    "📝 .md 範本",
                    data=generate_sample_roster_md(),
                    file_name="org_roster_template.md",
                    mime="text/markdown",
                    key="dl_tpl_md_trk",
                )

    st.divider()

    # 展開所有任務為平面清單並計算燈號預警
    rows: list[dict[str, str | int | bool]] = []
    accountables_set: set[str] = set(org_persons)
    responsibles_set: set[str] = set(org_persons)
    depts_set: set[str] = set(org_depts)
    smart_levels_set: set[str] = set()

    today_iso = datetime.date.today().isoformat()
    light_counts = {"🔴 紅燈": 0, "🟡 黃燈": 0, "🔵 藍燈": 0, "🟢 綠燈": 0}

    for m in meetings:
        for act in m.action_items:
            accountables_set.add(act.raci.accountable)
            for r in act.raci.responsible:
                responsibles_set.add(r)
            depts_set.add(act.department)
            smart_levels_set.add(act.smart.hierarchy_level)

            traffic_light, gov_status, _ = classify_action_traffic_light(act)
            light_counts[traffic_light] = light_counts.get(traffic_light, 0) + 1

            rows.append(
                {
                    "燈號預警": traffic_light,
                    "🩺 治理與逾期狀態": gov_status,
                    "會議日期": m.meeting_date,
                    "來源會議": m.title,
                    "任務編號": act.id,
                    "待辦事項名稱": act.task_title,
                    "執行狀態": act.status,
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

    # 2.5 四色霓虹微光燈號預警看板
    render_traffic_light_neon_strip(light_counts)

    # 3. 多維度交叉篩選器（包含批量匯入之部門與人員名冊，以及呼應四色燈號之治理狀態選單）
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
            "🩺 治理與逾期狀態 (燈號連動)",
            options=[
                "全部",
                "🔴 紅燈：🚨 逾期未完成",
                "🔴 紅燈：🛑 執行受阻 (Blocked)",
                "🟡 黃燈：⚠️ 治理缺口",
                "🟡 黃燈：⏳ 即將到期",
                "🔵 藍燈：⏳ 未完成/進行中",
                "🟢 綠燈：✅ 已完成 (Done)",
                "🔴 紅燈（全部：逾期未完成＋執行受阻）",
                "🟡 黃燈（全部：治理缺口＋即將到期）",
                "⚠️ 僅顯示有治理缺口",
                "🚨 僅顯示逾期任務",
                "✅ 僅顯示已完成 (Done)",
                "⏳ 僅顯示未完成",
            ],
            key="trk_filter_health",
        )

    filtered_rows = []
    for r in filtered_candidates(rows, sel_a, sel_r, sel_dept, sel_lvl, sel_health):
        filtered_rows.append(r)

    df = pd.DataFrame(filtered_rows)

    col_info, col_lights, col_dl = st.columns([1.8, 2.4, 1.2])
    with col_info:
        st.markdown(f"#### 📋 篩選結果：共 **{len(filtered_rows)}** 項行動方案")
    with col_lights:
        st.markdown(
            f"**燈號分布**：🔴 紅燈 **{light_counts['🔴 紅燈']}** ｜ "
            f"🟡 黃燈 **{light_counts['🟡 黃燈']}** ｜ "
            f"🔵 藍燈 **{light_counts['🔵 藍燈']}** ｜ "
            f"🟢 綠燈 **{light_counts['🟢 綠燈']}**"
        )
    with col_dl:
        csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "📥 匯出全域追蹤報表 (CSV)",
            data=csv_bytes,
            file_name=f"global_action_tracker_{today_iso}.csv",
            mime="text/csv",
            key="btn_dl_global_csv",
        )

    if not df.empty:
        styled_df = df.style.map(_style_traffic_light_cell, subset=["燈號預警", "🩺 治理與逾期狀態"])
        st.dataframe(styled_df, height=440)
    else:
        st.dataframe(df, height=200)


def filtered_candidates(
    rows: list[dict[str, str | int | bool]],
    sel_a: str,
    sel_r: str,
    sel_dept: str,
    sel_lvl: str,
    sel_health: str,
) -> list[dict[str, str | int | bool]]:
    """根據 5 大篩選器條件（含四色燈號與 6 種治理逾期狀態）過濾行動方案列."""
    out: list[dict[str, str | int | bool]] = []
    for r in rows:
        if sel_a != "全部" and r["A (最終當責者)"] != sel_a:
            continue
        if sel_r != "全部" and sel_r not in str(r["R (實際執行者)"]):
            continue
        if sel_dept != "全部" and sel_dept not in str(r["主責/跨部門"]):
            continue
        if sel_lvl != "全部" and r["SMART 層級"] != sel_lvl:
            continue

        light = str(r["燈號預警"])
        gov_state = str(r["🩺 治理與逾期狀態"])

        if sel_health == "🔴 紅燈：🚨 逾期未完成" and gov_state != "🚨 逾期未完成":
            continue
        if sel_health == "🔴 紅燈：🛑 執行受阻 (Blocked)" and gov_state != "🛑 執行受阻 (Blocked)":
            continue
        if sel_health == "🟡 黃燈：⚠️ 治理缺口" and gov_state != "⚠️ 治理缺口":
            continue
        if sel_health == "🟡 黃燈：⏳ 即將到期" and gov_state != "⏳ 即將到期":
            continue
        if sel_health == "🔵 藍燈：⏳ 未完成/進行中" and gov_state != "⏳ 未完成/進行中":
            continue
        if sel_health == "🟢 綠燈：✅ 已完成 (Done)" and gov_state != "✅ 已完成 (Done)":
            continue
        if sel_health == "🔴 紅燈（全部：逾期未完成＋執行受阻）" and light != "🔴 紅燈":
            continue
        if sel_health == "🟡 黃燈（全部：治理缺口＋即將到期）" and light != "🟡 黃燈":
            continue
        if sel_health == "⚠️ 僅顯示有治理缺口" and int(r["治理缺口數"]) == 0:
            continue
        if sel_health == "🚨 僅顯示逾期任務" and gov_state != "🚨 逾期未完成":
            continue
        if sel_health == "✅ 僅顯示已完成 (Done)" and r["執行狀態"] != "Done":
            continue
        if sel_health == "⏳ 僅顯示未完成" and r["執行狀態"] == "Done":
            continue

        out.append(r)
    return out
