"""Tab 3：跨會議「全域行動方案追蹤看板 (Global Action Tracker)」視圖.

提供企業跨部門治理視角：
- 全域 KPI 指標卡與四色燈號預警統計（🔴 紅燈、🟡 黃燈、🔵 藍燈、🟢 綠燈）
- 支援批量匯入「部門名稱」與「與會人員」（.xlsx / .csv / .md），自動同步至「👑 當責者 (A) 篩選」、「🛠️ 執行者 (R) 篩選」與「🏢 部門篩選」選單
- 支援多元排序模式（預設「風險度優先：🔴紅➔🟡黃➔🔵藍➔🟢綠，同組依會議日期由新而舊」，並支援「完成度分群」、「純會議日期由新而舊」、「截止日急迫度優先」）
- 支援「✏️ 編輯與清理模式」：可安全勾選刪除單筆／多筆測試或重複待辦任務，或刪除整場測試／重複會議（內建重複偵測標記與兩段式安全防呆確認）
- 支援一鍵匯出全域 RACI + SMART + QCD+T 追蹤報表 (CSV)
"""

from __future__ import annotations

import datetime
from typing import Any

import pandas as pd
import streamlit as st

from src.repositories.meeting_repo import MeetingRepository
from src.schemas.models import MeetingRecord
from src.services.governance import (
    classify_action_traffic_light,
    compute_governance_metrics,
    get_taiwan_today,
    parse_flexible_date,
)
from src.services.org_directory_service import (
    generate_sample_roster_csv,
    generate_sample_roster_md,
    generate_sample_roster_xlsx,
    parse_organization_upload,
)
from src.ui.theme import render_traffic_light_neon_strip

SORT_MODE_RISK_FIRST = "🚦 風險度優先（🔴 紅 ➔ 🟡 黃 ➔ 🔵 藍 ➔ 🟢 綠，同組依會議日期由新而舊）"
SORT_MODE_COMPLETION = "✅ 完成度分群（未完成置頂 ➔ 已完成置底，同組依會議日期由新而舊）"
SORT_MODE_DATE_DESC = "📅 會議日期排序（由新而舊）"
SORT_MODE_DUE_ASC = "⏰ 截止日急迫度優先（已逾期／最早到期置頂，已完成置底）"

SORT_MODE_OPTIONS = [
    SORT_MODE_RISK_FIRST,
    SORT_MODE_COMPLETION,
    SORT_MODE_DATE_DESC,
    SORT_MODE_DUE_ASC,
]

DISPLAY_COLUMNS = [
    "燈號預警",
    "🩺 治理與逾期狀態",
    "會議日期",
    "來源會議",
    "任務編號",
    "待辦事項名稱",
    "執行狀態",
    "主責/跨部門",
    "A (最終當責者)",
    "R (實際執行者)",
    "SMART 層級",
    "截止日 (D)",
    "Q (品質驗收條件)",
    "C (成本預算)",
    "T (證據要求)",
    "T (已提交佐證)",
    "佐證已驗證",
    "治理缺口數",
    "治理缺口明細",
]

_LIGHT_PRIORITY = {
    "🔴 紅燈": 0,
    "🟡 黃燈": 1,
    "🔵 藍燈": 2,
    "🟢 綠燈": 3,
}

_STATUS_SUB_PRIORITY = {
    "🚨 逾期未完成": 0,
    "🛑 執行受阻 (Blocked)": 1,
    "⚠️ 治理缺口": 0,
    "⏳ 即將到期": 1,
    "⏳ 未完成/進行中": 0,
    "✅ 已完成 (Done)": 0,
}


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


def _date_ordinal_desc(raw: object) -> int:
    """回傳負數 ordinal 供由新而舊排序；無法解析者排於組內最後."""
    parsed = parse_flexible_date(str(raw or ""))
    return -parsed.toordinal() if parsed is not None else 0


def _date_ordinal_asc(raw: object) -> int:
    """回傳正數 ordinal 供由舊而新（最早截止／逾期最久優先）排序；無法解析者排於最後."""
    parsed = parse_flexible_date(str(raw or ""))
    return parsed.toordinal() if parsed is not None else 9_999_999


def sort_tracker_rows(
    rows: list[dict[str, Any]],
    sort_mode: str = SORT_MODE_RISK_FIRST,
) -> list[dict[str, Any]]:
    """依據選定之排序策略排序看板資料列（支援風險度分群、完成度分群、日期由新而舊與截止日急迫度）."""

    def _key(r: dict[str, Any]) -> tuple[Any, ...]:
        light_rank = _LIGHT_PRIORITY.get(str(r.get("燈號預警", "")), 9)
        sub_rank = _STATUS_SUB_PRIORITY.get(str(r.get("🩺 治理與逾期狀態", "")), 9)
        is_done = 1 if str(r.get("執行狀態", "")) == "Done" else 0
        m_date_desc = _date_ordinal_desc(r.get("會議日期", ""))
        due_asc = _date_ordinal_asc(r.get("截止日 (D)", ""))
        act_id = str(r.get("任務編號", ""))

        if sort_mode == SORT_MODE_COMPLETION:
            return (is_done, m_date_desc, light_rank, sub_rank, due_asc, act_id)
        if sort_mode == SORT_MODE_DATE_DESC:
            return (m_date_desc, light_rank, sub_rank, due_asc, act_id)
        if sort_mode == SORT_MODE_DUE_ASC:
            return (is_done, due_asc, light_rank, m_date_desc, act_id)

        # 預設：風險度優先（🔴 紅 ➔ 🟡 黃 ➔ 🔵 藍 ➔ 🟢 綠，已完成自動置底；同組依會議日期由新而舊）
        return (light_rank, sub_rank, m_date_desc, due_asc, act_id)

    return sorted(rows, key=_key)


def annotate_duplicate_tasks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """自動偵測跨會議或同會議中之疑似重複任務，並標註重複次數與是否為可清理之多餘副本（每組保留最新 1 筆）."""
    groups: dict[tuple[str, str], list[int]] = {}
    for idx, r in enumerate(rows):
        norm_title = " ".join(str(r.get("待辦事項名稱", "")).strip().lower().split())
        norm_acc = " ".join(str(r.get("A (最終當責者)", "")).strip().lower().split())
        sig = (norm_title, norm_acc)
        if norm_title:
            groups.setdefault(sig, []).append(idx)

    dup_count_by_idx: dict[int, int] = {}
    redundant_by_idx: dict[int, bool] = {}

    for _, indices in groups.items():
        if len(indices) <= 1:
            continue
        # 依會議日期與最後更新時間由新而舊排序，每組保留最新 1 筆，其餘標記為多餘副本
        ordered = sorted(
            indices,
            key=lambda i: (
                _date_ordinal_desc(rows[i].get("會議日期", "")),
                -int(bool(str(rows[i].get("T (已提交佐證)", "")) not in {"", "尚未提交"})),
                i,
            ),
        )
        for pos, row_i in enumerate(ordered):
            dup_count_by_idx[row_i] = len(indices)
            redundant_by_idx[row_i] = pos > 0

    annotated: list[dict[str, Any]] = []
    for idx, r in enumerate(rows):
        copy_r = dict(r)
        cnt = dup_count_by_idx.get(idx, 1)
        copy_r["_dup_count"] = cnt
        copy_r["_is_redundant_dup"] = redundant_by_idx.get(idx, False)
        copy_r["_dup_label"] = f"⚠️ 疑似重複 (共 {cnt} 筆)" if cnt > 1 else "正常"
        annotated.append(copy_r)
    return annotated


def render_tracker_view(repo: MeetingRepository) -> None:
    """渲染跨會議全域行動方案追蹤看板."""
    st.markdown("### 📊 跨會議「全域行動方案追蹤看板 (Global Action Tracker)」")
    st.caption(
        "彙整企業所有會議之待辦事項，以 **四色燈號預警（紅/黃/藍/綠燈）**、**風險／日期智慧排序**、**RACI 當責歸屬**、**SMART 目標層級** 與 **QCD+T 真實性佐證** 進行跨部門治理監控。"
    )

    if "trk_cleanup_feedback" in st.session_state:
        st.success(st.session_state.pop("trk_cleanup_feedback"))

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
    rows: list[dict[str, Any]] = []
    accountables_set: set[str] = set(org_persons)
    responsibles_set: set[str] = set(org_persons)
    depts_set: set[str] = set(org_depts)
    smart_levels_set: set[str] = set()

    today_iso = get_taiwan_today().isoformat()
    light_counts = {"🔴 紅燈": 0, "🟡 黃燈": 0, "🔵 藍燈": 0, "🟢 綠燈": 0}

    for m in meetings:
        for item_idx, act in enumerate(m.action_items):
            accountables_set.add(act.raci.accountable)
            for r in act.raci.responsible:
                responsibles_set.add(r)
            depts_set.add(act.department)
            smart_levels_set.add(act.smart.hierarchy_level)

            traffic_light, gov_status, _ = classify_action_traffic_light(act)
            light_counts[traffic_light] = light_counts.get(traffic_light, 0) + 1

            rows.append(
                {
                    "_meeting_id": m.id,
                    "_item_index": item_idx,
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
        if meetings:
            _render_edit_and_cleanup_panel(repo=repo, meetings=meetings, annotated_rows=[])
        return

    # 標記跨會議疑似重複任務
    annotated_all_rows = annotate_duplicate_tasks(rows)

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

    # 3.5 排序方式 ＋ 編輯／清理模式切換列
    s_col1, s_col2 = st.columns([2.8, 2.2])
    with s_col1:
        sel_sort_mode = st.selectbox(
            "🔀 排序方式（預設高風險紅燈置頂、已完成綠燈置底，同組依會議日期由新而舊）",
            options=SORT_MODE_OPTIONS,
            index=0,
            key="trk_sort_mode",
        )
    with s_col2:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        dup_total = sum(1 for r in annotated_all_rows if r["_dup_count"] > 1)
        edit_label = (
            f"✏️ 編輯與清理模式（刪除測試／重複項目｜偵測到 {dup_total} 筆疑似重複）"
            if dup_total > 0
            else "✏️ 編輯與清理模式（刪除測試／重複任務或整場會議）"
        )
        edit_mode_on = st.toggle(edit_label, value=False, key="trk_edit_mode_toggle")

    filtered_rows = filtered_candidates(annotated_all_rows, sel_a, sel_r, sel_dept, sel_lvl, sel_health)
    sorted_rows = sort_tracker_rows(filtered_rows, sort_mode=sel_sort_mode)

    display_rows = [{col: r[col] for col in DISPLAY_COLUMNS} for r in sorted_rows]
    df = pd.DataFrame(display_rows, columns=DISPLAY_COLUMNS) if display_rows else pd.DataFrame(columns=DISPLAY_COLUMNS)

    col_info, col_lights, col_dl = st.columns([1.8, 2.4, 1.2])
    with col_info:
        st.markdown(f"#### 📋 篩選結果：共 **{len(sorted_rows)}** 項行動方案")
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

    # 4. 編輯與安全清理工作區（刪除測試／重複任務或整場會議，兩段式防呆確認）
    if edit_mode_on:
        st.divider()
        _render_edit_and_cleanup_panel(repo=repo, meetings=meetings, annotated_rows=sorted_rows)


def _render_edit_and_cleanup_panel(
    repo: MeetingRepository,
    meetings: list[MeetingRecord],
    annotated_rows: list[dict[str, Any]],
) -> None:
    """渲染看板三之「✏️ 編輯與清理工作區」（支援勾選刪除任務、整場會議與重複標記，含兩段式安全防呆）."""
    with st.container(border=True):
        st.markdown("#### ✏️ 看板三編輯與清理工作區（測試資料與重複項目安全移除）")
        st.caption(
            "🛡️ **資料安全保護**：所有刪除操作均採 **「兩段式確認（勾選預覽 ➔ 確認核取方塊 ➔ 執行刪除）」**，"
            "僅會移除您明確勾選之項目，絕不影響其他正式會議與系統組織名冊。"
        )

        tab_del_tasks, tab_del_meetings = st.tabs(
            [
                "🎯 刪除單筆／多筆待辦任務（含重複任務自動標記）",
                "📁 刪除整場測試／重複會議",
            ]
        )

        # --- Sub-tab A: 刪除單筆／多筆待辦任務 ---
        with tab_del_tasks:
            if not annotated_rows:
                st.info("目前篩選條件下無待辦任務可編輯。")
            else:
                dup_rows_cnt = sum(1 for r in annotated_rows if r.get("_dup_count", 1) > 1)
                redundant_cnt = sum(1 for r in annotated_rows if r.get("_is_redundant_dup", False))

                ctl1, ctl2 = st.columns([1.8, 2.2])
                with ctl1:
                    only_dups = st.checkbox(
                        f"🔍 僅顯示疑似重複任務（目前共 {dup_rows_cnt} 筆）",
                        value=False,
                        key="trk_edit_only_dups",
                    )
                with ctl2:
                    preselect_redundant = st.checkbox(
                        f"⚡ 自動預勾「多餘重複副本」（共 {redundant_cnt} 筆，每組保留最新 1 筆）",
                        value=False,
                        key="trk_edit_preselect_dups",
                        disabled=(redundant_cnt == 0),
                    )

                candidate_rows = [r for r in annotated_rows if (not only_dups or r.get("_dup_count", 1) > 1)]
                if not candidate_rows:
                    st.success("🎉 目前篩選範圍內未偵測到疑似重複任務！")
                else:
                    editor_records = []
                    for r in candidate_rows:
                        editor_records.append(
                            {
                                "🗑️ 勾選刪除": bool(preselect_redundant and r.get("_is_redundant_dup", False)),
                                "重複偵測": r.get("_dup_label", "正常"),
                                "燈號預警": r["燈號預警"],
                                "會議日期": r["會議日期"],
                                "來源會議": r["來源會議"],
                                "任務編號": r["任務編號"],
                                "待辦事項名稱": r["待辦事項名稱"],
                                "執行狀態": r["執行狀態"],
                                "A (最終當責者)": r["A (最終當責者)"],
                                "截止日 (D)": r["截止日 (D)"],
                            }
                        )
                    editor_df = pd.DataFrame(editor_records)
                    edited_tasks_df = st.data_editor(
                        editor_df,
                        hide_index=True,
                        width="stretch",
                        height=300,
                        disabled=[
                            "重複偵測",
                            "燈號預警",
                            "會議日期",
                            "來源會議",
                            "任務編號",
                            "待辦事項名稱",
                            "執行狀態",
                            "A (最終當責者)",
                            "截止日 (D)",
                        ],
                        column_config={
                            "🗑️ 勾選刪除": st.column_config.CheckboxColumn("🗑️ 勾選刪除", default=False),
                        },
                        key=f"trk_del_tasks_editor_{only_dups}_{preselect_redundant}_{len(candidate_rows)}",
                    )

                    selected_indices = [
                        i for i, checked in enumerate(edited_tasks_df["🗑️ 勾選刪除"].tolist()) if bool(checked)
                    ]

                    if selected_indices:
                        preview_lines = [
                            f"- `[{candidate_rows[i]['任務編號']}]` **{candidate_rows[i]['待辦事項名稱']}**（來源：{candidate_rows[i]['來源會議']}｜{candidate_rows[i]['會議日期']}）"
                            for i in selected_indices[:10]
                        ]
                        if len(selected_indices) > 10:
                            preview_lines.append(f"- ……以及其餘 **{len(selected_indices) - 10}** 項任務")
                        st.warning(
                            f"⚠️ **第一步預覽**：您已勾選 **{len(selected_indices)} 項** 待辦任務準備永久刪除：\n"
                            + "\n".join(preview_lines)
                        )
                        remove_empty_m = st.checkbox(
                            "若該場會議所有待辦任務皆被清空，一併移除該場空會議",
                            value=False,
                            key="trk_del_tasks_remove_empty_m",
                        )
                        confirm_del_tasks = st.checkbox(
                            f"⚠️ 第二步確認：我已核對以上 {len(selected_indices)} 項任務皆為測試或重複項目，同意永久刪除（無法復原）",
                            value=False,
                            key="trk_confirm_del_actions",
                        )
                        if st.button(
                            f"🗑️ 執行永久刪除所選 {len(selected_indices)} 項待辦任務",
                            type="primary",
                            disabled=not confirm_del_tasks,
                            key="btn_trk_exec_del_tasks",
                        ):
                            targets = [
                                (
                                    str(candidate_rows[i]["_meeting_id"]),
                                    int(candidate_rows[i]["_item_index"]),
                                    str(candidate_rows[i]["任務編號"]),
                                )
                                for i in selected_indices
                            ]
                            _, _, msg = repo.delete_action_items_by_keys(
                                targets=targets,
                                remove_empty_meetings=remove_empty_m,
                            )
                            st.session_state["trk_cleanup_feedback"] = msg
                            st.rerun()
                    else:
                        st.caption("💡 請先於上方表格最左側勾選欲移除之測試或重複待辦任務。")

        # --- Sub-tab B: 刪除整場測試／重複會議 ---
        with tab_del_meetings:
            if not meetings:
                st.info("目前資料庫中沒有會議記錄。")
            else:
                # 偵測同名同日之疑似重複會議
                meeting_sig_counts: dict[tuple[str, str], int] = {}
                for m in meetings:
                    parsed_d = parse_flexible_date(m.meeting_date)
                    norm_d = parsed_d.isoformat() if parsed_d else m.meeting_date.strip()
                    sig = (" ".join(m.title.strip().lower().split()), norm_d)
                    meeting_sig_counts[sig] = meeting_sig_counts.get(sig, 0) + 1

                m_records = []
                for m in meetings:
                    parsed_d = parse_flexible_date(m.meeting_date)
                    norm_d = parsed_d.isoformat() if parsed_d else m.meeting_date.strip()
                    sig = (" ".join(m.title.strip().lower().split()), norm_d)
                    cnt = meeting_sig_counts.get(sig, 1)
                    m_records.append(
                        {
                            "🗑️ 勾選刪除": False,
                            "重複偵測": f"⚠️ 疑似重複會議 (共 {cnt} 場)" if cnt > 1 else "正常",
                            "會議日期": m.meeting_date,
                            "來源會議名稱": m.title,
                            "任務筆數": len(m.action_items),
                            "來源類型": m.source_type,
                            "最後更新": m.updated_at,
                        }
                    )

                m_df = pd.DataFrame(m_records)
                edited_m_df = st.data_editor(
                    m_df,
                    hide_index=True,
                    width="stretch",
                    height=260,
                    disabled=["重複偵測", "會議日期", "來源會議名稱", "任務筆數", "來源類型", "最後更新"],
                    column_config={
                        "🗑️ 勾選刪除": st.column_config.CheckboxColumn("🗑️ 勾選刪除", default=False),
                    },
                    key=f"trk_del_meetings_editor_{len(meetings)}",
                )

                sel_m_indices = [
                    i for i, checked in enumerate(edited_m_df["🗑️ 勾選刪除"].tolist()) if bool(checked)
                ]
                if sel_m_indices:
                    total_sub_tasks = sum(len(meetings[i].action_items) for i in sel_m_indices)
                    m_preview = [
                        f"- 📅 `{meetings[i].meeting_date}` **{meetings[i].title}**（含 {len(meetings[i].action_items)} 項任務）"
                        for i in sel_m_indices
                    ]
                    st.warning(
                        f"⚠️ **第一步預覽**：您已勾選 **{len(sel_m_indices)} 場** 會議（共包含 **{total_sub_tasks}** 項待辦任務）準備永久刪除：\n"
                        + "\n".join(m_preview)
                    )
                    confirm_del_m = st.checkbox(
                        f"⚠️ 第二步確認：我已核對以上 {len(sel_m_indices)} 場會議皆為測試或重複資料，同意永久刪除（無法復原）",
                        value=False,
                        key="trk_confirm_del_meetings",
                    )
                    if st.button(
                        f"🗑️ 執行永久刪除所選 {len(sel_m_indices)} 場會議",
                        type="primary",
                        disabled=not confirm_del_m,
                        key="btn_trk_exec_del_meetings",
                    ):
                        mids = [meetings[i].id for i in sel_m_indices]
                        _, msg = repo.batch_delete_meetings(mids)
                        st.session_state["trk_cleanup_feedback"] = msg
                        st.rerun()
                else:
                    st.caption("💡 請先於上方表格最左側勾選欲移除之測試或重複會議。")


def filtered_candidates(
    rows: list[dict[str, Any]],
    sel_a: str,
    sel_r: str,
    sel_dept: str,
    sel_lvl: str,
    sel_health: str,
) -> list[dict[str, Any]]:
    """根據 5 大篩選器條件（含四色燈號與 6 種治理逾期狀態）過濾行動方案列."""
    out: list[dict[str, Any]] = []
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
