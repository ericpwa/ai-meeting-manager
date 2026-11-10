"""RACI + SMART + QCD+T 管理治理稽核與缺口主動偵測服務 (Governance Validator).

核心管理規則：
1. RACI 鐵律：每項任務原則上須有且只有一名最終當責者 A (Accountable)；可以有多名 R (Responsible)。
   跨部門任務不得因涉及多個部門而失去最終當責歸屬。
2. SMART 鐵律：明確區分「企業目標」、「專案成果」、「工作任務」與「個別活動」，不可混為一談；
   並檢核 Specific, Measurable, Achievable, Relevant, Time-bound。
3. QCD+T 鐵律：檢核 Quality (品質驗收)、Cost (成本預算)、Delivery (交付里程碑)、
   Truthfulness/Evidence (真實性與可驗證證據)。
4. 結案閉環鐵律：當待辦事項狀態轉為 Done 時，檢核是否已填具可驗證之成果佐證 (T)。
"""

from __future__ import annotations

import re
from typing import Iterable

from src.schemas.models import ActionItem, MeetingExtractionSchema, MeetingRecord

# 視為未指定或模糊的佔位詞集合
VAGUE_PLACEHOLDERS = {
    "",
    "無",
    "未指定",
    "待定",
    "待確認",
    "未知",
    "未明確",
    "待指定",
    "待指定 (未明確歸屬)",
    "tbd",
    "n/a",
    "none",
    "unknown",
    "null",
}

# 檢查當責者 A 是否被填入多人之分隔符號正規表達式
MULTI_PERSON_PATTERN = re.compile(r"[,，、/&＆;；]|(?:\s+及\s+)|(?:\s+與\s+)|(?:\s+和\s+)|(?:\s+and\s+)", re.IGNORECASE)

VALID_SMART_LEVELS = {
    "企業目標 (Enterprise Goal)",
    "專案成果 (Project Outcome)",
    "工作任務 (Work Task)",
    "個別活動 (Individual Activity)",
}


def is_vague_or_empty(text: str | None) -> bool:
    """判斷字串是否為空或屬於未明確定義之模糊詞彙."""
    if text is None:
        return True
    cleaned = text.strip().lower()
    return cleaned in VAGUE_PLACEHOLDERS


def has_multiple_accountables(accountable_str: str) -> bool:
    """檢查最終當責者 (A) 欄位是否違反『僅限單一當責者』原則（例如填寫了多人或多個部門共同當責）."""
    cleaned = (accountable_str or "").strip()
    if is_vague_or_empty(cleaned):
        return False
    # 允許格式如 "王大明 (研發部)" 或 "陳經理 - 產品部"，但不允許 "王大明、李小華" 或 "產品部 / 研發部"
    # 先移除括號內的部門補充說明再檢查分隔符
    without_parens = re.sub(r"[\(（][^\)）]*[\)）]", "", cleaned).strip()
    parts = [p.strip() for p in MULTI_PERSON_PATTERN.split(without_parens) if p.strip()]
    if len(parts) > 1:
        return True
    if any(keyword in cleaned for keyword in ["共同當責", "全體", "所有人", "各部門", "大家"]):
        return True
    return False


def audit_action_item_governance(item: ActionItem, index: int = 1) -> ActionItem:
    """對單一 ActionItem 執行 RACI + SMART + QCD+T 深度治理查核，自動補齊預設值並更新 governance_gaps."""
    gaps: list[str] = []

    # 確保 ID 有值
    if not item.id or not item.id.strip():
        item.id = f"ACT-{index:02d}"

    # 1. RACI 檢核：唯一最終當責者 A 與執行者 R
    acc = (item.raci.accountable or "").strip()
    if is_vague_or_empty(acc):
        item.raci.accountable = "待指定 (未明確歸屬)"
        gaps.append("【RACI 缺口】缺少最終當責者 (A)：每項任務須有唯一最終當責者，跨部門任務亦不得失去當責歸屬")
    elif has_multiple_accountables(acc):
        gaps.append(
            f"【RACI 違規】最終當責者 (A) 填寫了多人或多單位（{acc}）：原則上每項任務僅能有一名最終當責者 A，協作者請改列為執行者 R"
        )

    # 過濾空字串的 R, C, I
    item.raci.responsible = [r.strip() for r in item.raci.responsible if r and not is_vague_or_empty(r)]
    item.raci.consulted = [c.strip() for c in item.raci.consulted if c and not is_vague_or_empty(c)]
    item.raci.informed = [i.strip() for i in item.raci.informed if i and not is_vague_or_empty(i)]

    if not item.raci.responsible:
        if not is_vague_or_empty(item.owner):
            item.raci.responsible = [item.owner.strip()]
        else:
            gaps.append("【RACI 缺口】未指定實際執行者 (R：Responsible)")

    # 同步 Owner 與 RACI：優先以 Accountable 為 Owner，若 A 未指定則取第一位 R
    if is_vague_or_empty(item.owner):
        if not is_vague_or_empty(item.raci.accountable):
            item.owner = item.raci.accountable
        elif item.raci.responsible:
            item.owner = item.raci.responsible[0]
        else:
            item.owner = "待指定"

    # 2. SMART 目標層級與五維度檢核
    if item.smart.hierarchy_level not in VALID_SMART_LEVELS:
        item.smart.hierarchy_level = "工作任務 (Work Task)"

    smart_missing: list[str] = []
    if is_vague_or_empty(item.smart.specific):
        smart_missing.append("S-具體性")
    if is_vague_or_empty(item.smart.measurable):
        smart_missing.append("M-可衡量指標")
    if is_vague_or_empty(item.smart.time_bound) and is_vague_or_empty(item.due_date):
        smart_missing.append("T-明確期限")

    if smart_missing:
        item.smart.is_smart_compliant = False
        gaps.append(f"【SMART 缺口】目標描述尚缺：{', '.join(smart_missing)}")
    else:
        item.smart.is_smart_compliant = True

    if is_vague_or_empty(item.due_date):
        item.due_date = "待定"
        if "T-明確期限" not in smart_missing:
            gaps.append("【SMART / D 缺口】截止日期 (Due Date) 尚未明確設定")

    # 3. QCD+T 四維度檢核
    if is_vague_or_empty(item.qcdt.quality_criteria):
        gaps.append("【QCD+T 缺口】未定義 Q (Quality 品質與驗收條件)")
    if is_vague_or_empty(item.qcdt.cost_budget):
        item.qcdt.cost_budget = "0 元 (內部資源/工時)"
    if is_vague_or_empty(item.qcdt.delivery_milestone):
        if not is_vague_or_empty(item.due_date):
            item.qcdt.delivery_milestone = f"預計於 {item.due_date} 前完成交付"
        else:
            gaps.append("【QCD+T 缺口】未定義 D (Delivery 交付期限與里程碑)")
    if is_vague_or_empty(item.qcdt.truthfulness_req):
        gaps.append("【QCD+T 缺口】未定義 T (Truthfulness/Evidence 可驗證成果證據要求)")

    # 4. 若狀態已標記為 Done，檢核是否具備實際提交之佐證 T
    if item.status == "Done" and is_vague_or_empty(item.qcdt.evidence_submitted):
        gaps.append("【T 佐證閉環缺口】任務狀態為已完成 (Done)，但尚未提交可驗證成果佐證 (Evidence)")

    # 去重並保留順序
    deduped_gaps: list[str] = []
    for g in gaps:
        if g not in deduped_gaps:
            deduped_gaps.append(g)

    item.governance_gaps = deduped_gaps
    return item


def audit_meeting_extraction(extraction: MeetingExtractionSchema | MeetingRecord) -> MeetingExtractionSchema | MeetingRecord:
    """對整份會議萃取結果執行治理檢核與正規化."""
    audited_items: list[ActionItem] = []
    for idx, item in enumerate(extraction.action_items, start=1):
        audited_items.append(audit_action_item_governance(item, index=idx))
    extraction.action_items = audited_items
    return extraction


def validate_done_transition(item: ActionItem, new_status: str, new_evidence: str) -> tuple[bool, str]:
    """當使用者欲將待辦事項狀態更新為 Done 時，檢核 QCD+T 之 T (Truthfulness/Evidence) 閉環條件.

    回傳:
        (is_valid, message)
    """
    if new_status != "Done":
        return True, "狀態更新合法。"

    cleaned_evidence = (new_evidence or "").strip()
    if is_vague_or_empty(cleaned_evidence):
        return (
            False,
            "⚠️ 依據 QCD+T 管理框架之「T (Truthfulness/Evidence)」原則，將任務標記為「已完成 (Done)」前，必須填寫具體的成果佐證（例如：交付文件連結、PR 編號、測試數據或驗收紀錄）。",
        )
    return True, "✅ 已提供成果佐證 (T)，符合結案閉環要求。"


def classify_action_traffic_light(
    act: ActionItem,
    reference_date: __import__("datetime").date | None = None,
) -> tuple[str, str, str]:
    """判定單一待辦事項之『燈號預警 (紅/黃/藍/綠燈)』與『🩺 治理與逾期狀態』分類.

    規則對應：
    1. 🔴 紅燈 — 🚨 逾期未完成 (status != Done 且 due_date < today)
    2. 🔴 紅燈 — 🛑 執行受阻 (Blocked) (status == Blocked)
    3. 🟡 黃燈 — ⚠️ 治理缺口 (存在 RACI/SMART/QCD+T 缺口)
    4. 🟡 黃燈 — ⏳ 即將到期 (status != Done 且 0 <= 剩餘天數 <= 3)
    5. 🔵 藍燈 — ⏳ 未完成/進行中 (status 為 Pending 或 In Progress，且無逾期/無缺口/非即將到期)
    6. 🟢 綠燈 — ✅ 已完成 (Done) (status == Done 且無治理缺口)

    回傳:
        (traffic_light, governance_status, combined_badge)
    """
    import datetime as _dt

    today = reference_date or _dt.date.today()
    due_str = (act.due_date or "").strip()
    days_delta: int | None = None

    if re.match(r"^\d{4}-\d{2}-\d{2}$", due_str):
        try:
            due_dt = _dt.date.fromisoformat(due_str)
            days_delta = (due_dt - today).days
        except ValueError:
            days_delta = None

    # 1. 逾期未完成 -> 紅燈
    if act.status != "Done" and days_delta is not None and days_delta < 0:
        return "🔴 紅燈", "🚨 逾期未完成", "🔴 紅燈｜🚨 逾期未完成"

    # 2. 執行受阻 (Blocked) -> 紅燈
    if act.status == "Blocked":
        return "🔴 紅燈", "🛑 執行受阻 (Blocked)", "🔴 紅燈｜🛑 執行受阻 (Blocked)"

    # 3. 治理缺口 -> 黃燈
    if act.governance_gaps:
        return "🟡 黃燈", "⚠️ 治理缺口", "🟡 黃燈｜⚠️ 治理缺口"

    # 4. 即將到期 (3日內) -> 黃燈
    if act.status != "Done" and days_delta is not None and 0 <= days_delta <= 3:
        return "🟡 黃燈", "⏳ 即將到期", "🟡 黃燈｜⏳ 即將到期"

    # 5. 未完成/進行中 -> 藍燈
    if act.status != "Done":
        return "🔵 藍燈", "⏳ 未完成/進行中", "🔵 藍燈｜⏳ 未完成/進行中"

    # 6. 已完成 (Done) -> 綠燈
    return "🟢 綠燈", "✅ 已完成 (Done)", "🟢 綠燈｜✅ 已完成 (Done)"


def compute_governance_metrics(meetings: Iterable[MeetingRecord]) -> dict[str, int | float]:
    """計算跨會議之全域管理指標 (供 Global Action Tracker 儀表板使用)."""
    total_meetings = 0
    total_actions = 0
    done_actions = 0
    in_progress_actions = 0
    blocked_actions = 0
    pending_actions = 0
    overdue_actions = 0
    gaps_count = 0
    verified_evidence_count = 0

    today_str = re.sub(r"[^0-9-]", "", str( __import__("datetime").date.today().isoformat()))

    for m in meetings:
        total_meetings += 1
        for act in m.action_items:
            total_actions += 1
            if act.status == "Done":
                done_actions += 1
            elif act.status == "In Progress":
                in_progress_actions += 1
            elif act.status == "Blocked":
                blocked_actions += 1
            else:
                pending_actions += 1

            if act.governance_gaps:
                gaps_count += 1

            if act.qcdt.evidence_verified or (act.status == "Done" and not is_vague_or_empty(act.qcdt.evidence_submitted)):
                verified_evidence_count += 1

            # 檢查是否逾期 (YYYY-MM-DD < today 且狀態非 Done)
            due = (act.due_date or "").strip()
            if act.status != "Done" and re.match(r"^\d{4}-\d{2}-\d{2}$", due):
                if due < today_str:
                    overdue_actions += 1

    completion_rate = round((done_actions / total_actions) * 100, 1) if total_actions > 0 else 0.0
    governance_health_rate = (
        round(((total_actions - gaps_count) / total_actions) * 100, 1) if total_actions > 0 else 100.0
    )

    return {
        "total_meetings": total_meetings,
        "total_actions": total_actions,
        "done_actions": done_actions,
        "in_progress_actions": in_progress_actions,
        "blocked_actions": blocked_actions,
        "pending_actions": pending_actions,
        "overdue_actions": overdue_actions,
        "actions_with_gaps": gaps_count,
        "verified_evidence_count": verified_evidence_count,
        "completion_rate": completion_rate,
        "governance_health_rate": governance_health_rate,
    }
