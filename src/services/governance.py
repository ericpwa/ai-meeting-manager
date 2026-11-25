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

import datetime
import re
from typing import Iterable

from src.schemas.models import ActionItem, MeetingExtractionSchema, MeetingRecord

TAIWAN_TZ = datetime.timezone(datetime.timedelta(hours=8))

# 視為未指定或模糊的佔位詞集合
VAGUE_PLACEHOLDERS = {
    "",
    "-",
    "--",
    "—",
    "–",
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


def get_taiwan_now() -> datetime.datetime:
    """取得台灣標準時間 (UTC+8) 當前日期時間，避免雲端伺服器 UTC 時差導致逾期誤判."""
    return datetime.datetime.now(TAIWAN_TZ)


def get_taiwan_today() -> datetime.date:
    """取得台灣標準時間 (UTC+8) 今日日期."""
    return get_taiwan_now().date()


def _to_halfwidth(text: str) -> str:
    """將常見全形數字與日期符號正規化為半形."""
    trans = str.maketrans("０１２３４５６７８９／－．：　", "0123456789/-.: ")
    return text.translate(trans)


def _convert_year_to_ad(raw_year: int) -> int | None:
    """支援西元年 (1900-2199) 與台灣民國年 (1-300，自動加 1911 轉西元)."""
    if 1900 <= raw_year <= 2199:
        return raw_year
    if 1 <= raw_year <= 300:
        return raw_year + 1911
    return None


def _build_time_from_groups(
    meridiem_zh: str | None,
    hh: str | None,
    mm: str | None,
    ss: str | None,
    meridiem_en: str | None,
) -> datetime.time | None:
    if hh is None or mm is None:
        return None
    try:
        hour = int(hh)
        minute = int(mm)
        second = int(ss) if ss is not None else 0
        if meridiem_zh == "下午" or (meridiem_en and meridiem_en.lower() == "pm"):
            if 1 <= hour <= 11:
                hour += 12
        elif meridiem_zh == "上午" or (meridiem_en and meridiem_en.lower() == "am"):
            if hour == 12:
                hour = 0
        return datetime.time(hour, minute, second)
    except ValueError:
        return None


def parse_flexible_datetime(date_str: str | None) -> tuple[datetime.date | None, datetime.time | None]:
    """彈性解析多種企業常見日期/時間格式，回傳 `(date, time_or_none)`.

    支援格式：
    - 標準 ISO 與斜線/點分隔（含時間）：`2026-11-15`, `2026/11/15 00:00`, `2026-11-23 12:00:00`, `2026.11.5`, `2026-11-23T17:30:00`
    - 台灣民國年格式：`0115-11-23`, `115/11/23`, `115.11.23`, `115年11月23日`, `民國115年11月23日`, `1151123`
    - 中文西元年格式：`2026年11月15日`, `2026年11月5號`
    - 美式斜線/連字號：`11/15/2026`, `11-15-2026 00:00`
    - 8 碼緊湊西元日期：`20261115`
    """
    if not date_str:
        return None, None
    cleaned = _to_halfwidth(str(date_str).strip())
    if is_vague_or_empty(cleaned):
        return None, None

    time_tail = r"(?:[T\s]+(?:(上午|下午)\s*)?(\d{1,2}):(\d{2})(?::(\d{2}))?(?:\s*(AM|PM|am|pm))?)?"

    # 1. Y-M-D / Y/M/D / Y.M.D (含西元與民國 0115 / 115)
    m1 = re.search(rf"(?<!\d)(\d{{2,4}})[-/.](\d{{1,2}})[-/.](\d{{1,2}}){time_tail}(?!\d)", cleaned)
    if m1:
        ad_year = _convert_year_to_ad(int(m1.group(1)))
        month, day = int(m1.group(2)), int(m1.group(3))
        if ad_year is not None and 1 <= month <= 12 and 1 <= day <= 31:
            try:
                parsed_d = datetime.date(ad_year, month, day)
                parsed_t = _build_time_from_groups(m1.group(4), m1.group(5), m1.group(6), m1.group(7), m1.group(8))
                return parsed_d, parsed_t
            except ValueError:
                pass

    # 2. 中文年月日 (2026年11月15日 / 民國115年11月23日 / 115年11月23號)
    m2 = re.search(rf"(?:民國\s*)?(\d{{2,4}})\s*年\s*(\d{{1,2}})\s*月\s*(\d{{1,2}})\s*[日號]{time_tail}", cleaned)
    if m2:
        ad_year = _convert_year_to_ad(int(m2.group(1)))
        month, day = int(m2.group(2)), int(m2.group(3))
        if ad_year is not None:
            try:
                parsed_d = datetime.date(ad_year, month, day)
                parsed_t = _build_time_from_groups(m2.group(4), m2.group(5), m2.group(6), m2.group(7), m2.group(8))
                return parsed_d, parsed_t
            except ValueError:
                pass

    # 3. 美式 MM/DD/YYYY 或 MM-DD-YYYY
    m3 = re.search(rf"(?<!\d)(\d{{1,2}})[-/](\d{{1,2}})[-/](\d{{4}}){time_tail}(?!\d)", cleaned)
    if m3:
        month, day, year = int(m3.group(1)), int(m3.group(2)), int(m3.group(3))
        if 1900 <= year <= 2199:
            try:
                parsed_d = datetime.date(year, month, day)
                parsed_t = _build_time_from_groups(m3.group(4), m3.group(5), m3.group(6), m3.group(7), m3.group(8))
                return parsed_d, parsed_t
            except ValueError:
                pass

    # 4. 8 碼緊湊西元日期 YYYYMMDD (如 20261115)
    m4 = re.search(r"(?<!\d)((?:19|20|21)\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?!\d)", cleaned)
    if m4:
        try:
            return datetime.date(int(m4.group(1)), int(m4.group(2)), int(m4.group(3))), None
        except ValueError:
            pass

    # 5. 7 碼緊湊民國日期 YYYMMDD (如 1151123)
    m5 = re.search(r"(?<!\d)(\d{3})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?!\d)", cleaned)
    if m5:
        ad_year = _convert_year_to_ad(int(m5.group(1)))
        if ad_year is not None and 1990 <= ad_year <= 2150:
            try:
                return datetime.date(ad_year, int(m5.group(2)), int(m5.group(3))), None
            except ValueError:
                pass

    return None, None


def parse_flexible_date(date_str: str | None) -> datetime.date | None:
    """彈性解析日期字串並回傳 `datetime.date`（解析失敗則回傳 None）."""
    parsed_d, _ = parse_flexible_datetime(date_str)
    return parsed_d


def normalize_date_str(date_str: str | None, keep_nonzero_time: bool = False) -> str:
    """將各種日期格式（含 Excel 時間戳與民國年）正規化為標準 `YYYY-MM-DD`（或選用保留非午夜時間）."""
    raw = (date_str or "").strip()
    if is_vague_or_empty(raw):
        return ""
    parsed_d, parsed_t = parse_flexible_datetime(raw)
    if parsed_d is None:
        return raw
    if keep_nonzero_time and parsed_t is not None and (parsed_t.hour, parsed_t.minute, parsed_t.second) != (0, 0, 0):
        return f"{parsed_d.isoformat()} {parsed_t.strftime('%H:%M')}"
    return parsed_d.isoformat()


def is_action_overdue(
    act: ActionItem,
    reference_date: datetime.date | None = None,
) -> tuple[bool, int | None]:
    """統一判定單一待辦事項是否逾期及其距離截止日之天數差 `(is_overdue, days_delta)`."""
    today = reference_date or get_taiwan_today()
    due_dt, due_tm = parse_flexible_datetime(act.due_date)
    if due_dt is None:
        return False, None

    days_delta = (due_dt - today).days
    if act.status == "Done":
        return False, days_delta

    if days_delta < 0:
        return True, days_delta

    # 若未指定外部基準日且為當日明確非午夜時間（例如 2026-11-25 12:00:00），已過該時點亦視為逾期
    if (
        reference_date is None
        and days_delta == 0
        and due_tm is not None
        and (due_tm.hour, due_tm.minute, due_tm.second) != (0, 0, 0)
        and due_tm < get_taiwan_now().time()
    ):
        return True, days_delta

    return False, days_delta


def classify_action_traffic_light(
    act: ActionItem,
    reference_date: datetime.date | None = None,
) -> tuple[str, str, str]:
    """判定單一待辦事項之『燈號預警 (紅/黃/藍/綠燈)』與『🩺 治理與逾期狀態』分類.

    規則對應：
    1. 🔴 紅燈 — 🚨 逾期未完成 (status != Done 且 due_date 已逾期，支援多種西元/民國/含時間戳格式)
    2. 🔴 紅燈 — 🛑 執行受阻 (Blocked) (status == Blocked)
    3. 🟡 黃燈 — ⚠️ 治理缺口 (存在 RACI/SMART/QCD+T 缺口)
    4. 🟡 黃燈 — ⏳ 即將到期 (status != Done 且 0 <= 剩餘天數 <= 3)
    5. 🔵 藍燈 — ⏳ 未完成/進行中 (status 為 Pending 或 In Progress，且無逾期/無缺口/非即將到期)
    6. 🟢 綠燈 — ✅ 已完成 (Done) (status == Done 且無治理缺口)

    回傳:
        (traffic_light, governance_status, combined_badge)
    """
    overdue, days_delta = is_action_overdue(act, reference_date=reference_date)

    # 1. 逾期未完成 -> 紅燈
    if act.status != "Done" and overdue:
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


def compute_governance_metrics(
    meetings: Iterable[MeetingRecord],
    reference_date: datetime.date | None = None,
) -> dict[str, int | float]:
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

            # 統一透過彈性日期解析引擎檢查是否逾期（相容 Excel 斜線/時間戳/民國年等所有日期格式）
            overdue, _ = is_action_overdue(act, reference_date=reference_date)
            if overdue:
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
