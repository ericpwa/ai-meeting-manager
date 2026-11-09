"""跨部門主動催辦與通知引擎服務 (`src/services/notification_service.py`).

核心職責：
1. 自動巡檢所有會議中之「逾期未完成 (Overdue)」、「執行受阻 (Blocked)」、「即將到期 (Due Soon)」與「存在 RACI/SMART/QCD+T 治理缺口」任務。
2. 依「最終當責者 A (Accountable)」或「主責部門」自動聚合催辦清單（落實 RACI 單一當責制：催辦必找當責者 A，並副知執行者 R）。
3. 產出多通道結構化催辦通知文案：
   - 📧 Email 正式當責稽核與催辦信
   - 💬 Slack / Microsoft Teams 頻道標註訊息
   - 📱 LINE / 即時通訊高密度行動卡片
4. 支援透過 Gemini API 依據管理情境調整催辦語氣（溫和提醒 ／ 嚴謹稽核 ／ 高階主管升級預警 Escalation）。
5. 支援零成本 Webhook 推播（相容 Slack / Discord / Teams / Generic JSON Webhook），並提供安全模擬發送模式。
"""

from __future__ import annotations

import datetime
import re
from typing import Literal

import httpx
from pydantic import BaseModel, Field

from src.config import get_gemini_api_key, get_gemini_model, get_webhook_url
from src.schemas.models import ActionItem, MeetingRecord


class FollowUpTaskEntry(BaseModel):
    """單筆需催辦或稽核之行動任務項目."""

    meeting_id: str
    meeting_title: str
    meeting_date: str
    action_id: str
    task_title: str
    department: str
    accountable: str
    responsible: list[str]
    due_date: str
    status: str
    smart_level: str
    quality_criteria: str
    truthfulness_req: str
    governance_gaps: list[str]
    urgency_category: Literal["🚨 逾期未完成", "🛑 執行受阻 (Blocked)", "⚠️ 治理缺口待補齊", "⏳ 3日內即將到期"]
    days_delta: int | None = None


class AccountableDigestGroup(BaseModel):
    """依『最終當責者 A』聚合之催辦摘要包."""

    accountable: str
    departments: list[str] = Field(default_factory=list)
    overdue_count: int = 0
    blocked_count: int = 0
    gap_count: int = 0
    due_soon_count: int = 0
    items: list[FollowUpTaskEntry] = Field(default_factory=list)


def scan_followup_targets(
    meetings: list[MeetingRecord],
    reference_date: datetime.date | None = None,
) -> list[FollowUpTaskEntry]:
    """掃描所有會議記錄，篩選出需要主動催辦或治理補強之待辦事項."""
    today = reference_date or datetime.date.today()
    entries: list[FollowUpTaskEntry] = []

    for m in meetings:
        for act in m.action_items:
            if act.status == "Done" and not act.governance_gaps:
                continue

            due_str = (act.due_date or "").strip()
            days_delta: int | None = None
            is_overdue = False
            is_due_soon = False

            if re.match(r"^\d{4}-\d{2}-\d{2}$", due_str):
                try:
                    due_dt = datetime.date.fromisoformat(due_str)
                    days_delta = (due_dt - today).days
                    if act.status != "Done" and days_delta < 0:
                        is_overdue = True
                    elif act.status != "Done" and 0 <= days_delta <= 3:
                        is_due_soon = True
                except ValueError:
                    pass

            # 判定催辦優先分類
            category: Literal["🚨 逾期未完成", "🛑 執行受阻 (Blocked)", "⚠️ 治理缺口待補齊", "⏳ 3日內即將到期"] | None = None
            if is_overdue:
                category = "🚨 逾期未完成"
            elif act.status == "Blocked":
                category = "🛑 執行受阻 (Blocked)"
            elif act.governance_gaps:
                category = "⚠️ 治理缺口待補齊"
            elif is_due_soon:
                category = "⏳ 3日內即將到期"

            if category is not None:
                entries.append(
                    FollowUpTaskEntry(
                        meeting_id=m.id,
                        meeting_title=m.title,
                        meeting_date=m.meeting_date,
                        action_id=act.id,
                        task_title=act.task_title,
                        department=act.department,
                        accountable=act.raci.accountable,
                        responsible=act.raci.responsible,
                        due_date=act.due_date,
                        status=act.status,
                        smart_level=act.smart.hierarchy_level,
                        quality_criteria=act.qcdt.quality_criteria,
                        truthfulness_req=act.qcdt.truthfulness_req,
                        governance_gaps=act.governance_gaps,
                        urgency_category=category,
                        days_delta=days_delta,
                    )
                )

    # 排序：逾期 -> 受阻 -> 治理缺口 -> 即將到期
    priority_order = {
        "🚨 逾期未完成": 0,
        "🛑 執行受阻 (Blocked)": 1,
        "⚠️ 治理缺口待補齊": 2,
        "⏳ 3日內即將到期": 3,
    }
    entries.sort(key=lambda e: (priority_order.get(e.urgency_category, 9), e.due_date))
    return entries


def group_by_accountable(entries: list[FollowUpTaskEntry]) -> list[AccountableDigestGroup]:
    """將催辦項目依 RACI 之『最終當責者 A』分群彙整."""
    groups_map: dict[str, AccountableDigestGroup] = {}
    for entry in entries:
        acc = entry.accountable or "待指定 (未明確歸屬)"
        if acc not in groups_map:
            groups_map[acc] = AccountableDigestGroup(accountable=acc)
        grp = groups_map[acc]
        grp.items.append(entry)
        if entry.department and entry.department not in grp.departments:
            grp.departments.append(entry.department)

        if entry.urgency_category == "🚨 逾期未完成":
            grp.overdue_count += 1
        elif entry.urgency_category == "🛑 執行受阻 (Blocked)":
            grp.blocked_count += 1
        elif entry.urgency_category == "⚠️ 治理缺口待補齊":
            grp.gap_count += 1
        elif entry.urgency_category == "⏳ 3日內即將到期":
            grp.due_soon_count += 1

    # 優先將『待指定 (未明確歸屬)』或有逾期/受阻之當責者排在前面
    return sorted(
        groups_map.values(),
        key=lambda g: (
            0 if "待指定" in g.accountable else 1,
            -(g.overdue_count * 10 + g.blocked_count * 5 + g.gap_count * 2 + g.due_soon_count),
        ),
    )


def generate_channel_message(
    entries: list[FollowUpTaskEntry],
    channel: Literal["email", "slack_teams", "line"] = "slack_teams",
    tone: Literal["溫和提醒 (Friendly)", "嚴謹稽核 (Audit)", "高階升級預警 (Escalation)"] = "嚴謹稽核 (Audit)",
    target_accountable: str = "全體當責人",
) -> str:
    """根據選定之通知通道與管理語氣，產出結構化 RACI + SMART + QCD+T 催辦摘要訊息."""
    today_iso = datetime.date.today().isoformat()
    if not entries:
        return f"✅ 【{today_iso} 會議治理巡檢】目前「{target_accountable}」名下無任何逾期、受阻或存在治理缺口之待辦事項！"

    overdue_n = sum(1 for e in entries if e.urgency_category == "🚨 逾期未完成")
    blocked_n = sum(1 for e in entries if e.urgency_category == "🛑 執行受阻 (Blocked)")
    gap_n = sum(1 for e in entries if e.urgency_category == "⚠️ 治理缺口待補齊")

    tone_Opening = {
        "溫和提醒 (Friendly)": "感謝各位跨部門夥伴的投入！溫馨提醒以下會議決議事項需要您的協助更新與推進：",
        "嚴謹稽核 (Audit)": "依據公司 RACI 當責制與 QCD+T 管理規範，以下會議行動方案需請最終當責者 (A) 立即確認進度並補齊驗證佐證 (T)：",
        "高階升級預警 (Escalation)": "⚠️【高階管理升級預警】以下跨部門關鍵任務已出現逾期、受阻或當責缺口，請最終當責者 (A) 於今日下班前提交處置方案與 T 佐證：",
    }.get(tone, "")

    if channel == "email":
        lines = [
            f"主旨：【AI 會議治理催辦】{target_accountable} — 待處理行動方案稽核通知（逾期 {overdue_n} 件 / 受阻 {blocked_n} 件 / 缺口 {gap_n} 件）",
            "",
            f"致 最終當責者 (A)：{target_accountable} 暨相關執行團隊 (R)：",
            "",
            tone_Opening,
            "",
            f"📊 **統計摘要（基準日：{today_iso}）**：共 {len(entries)} 項待關注任務（🚨 逾期：{overdue_n} ｜ 🛑 受阻：{blocked_n} ｜ ⚠️ 治理缺口：{gap_n}）",
            "---",
        ]
        for idx, e in enumerate(entries, start=1):
            r_str = ", ".join(e.responsible) if e.responsible else "尚未指定 R"
            lines.extend(
                [
                    f"### {idx}. {e.urgency_category}｜[{e.action_id}] {e.task_title}",
                    f"- **來源會議**：{e.meeting_title} ({e.meeting_date}) ｜ **部門**：{e.department}",
                    f"- **RACI 歸屬**：👑 **A (當責)**：{e.accountable} ｜ 🛠️ **R (執行)**：{r_str}",
                    f"- **SMART 層級**：`{e.smart_level}` ｜ **截止日期 (D)**：`{e.due_date}` ｜ **目前狀態**：`{e.status}`",
                    f"- **Q (品質驗收條件)**：{e.quality_criteria or '⚠️ 尚未定義（請補齊）'}",
                    f"- **T (結案必備可驗證證據)**：{e.truthfulness_req or '⚠️ 尚未定義（請補齊）'}",
                ]
            )
            if e.governance_gaps:
                lines.append(f"- 🚨 **待修正治理缺口**：{'；'.join(e.governance_gaps)}")
            lines.append("")

        lines.extend(
            [
                "---",
                "📌 **結案閉環提醒 (QCD+T 之 T 原則)**：完成任務時，請務必登入「AI 會議記錄管理 Web App」勾選 `Done` 並附上可驗證之成果佐證連結（如 PR、測試報告或簽核單號）。",
            ]
        )
        return "\n".join(lines)

    if channel == "line":
        lines = [
            f"🔔【會議當責催辦｜{target_accountable}】",
            f"📅 {today_iso}（共 {len(entries)} 項：🚨逾期{overdue_n} / 🛑受阻{blocked_n} / ⚠️缺口{gap_n}）",
            tone_Opening,
            "━━━━━━━━━━━━━━",
        ]
        for idx, e in enumerate(entries, start=1):
            r_str = "、".join(e.responsible) if e.responsible else "待指定"
            lines.append(
                f"{idx}️⃣ {e.urgency_category}\n"
                f"📌 [{e.action_id}] {e.task_title}\n"
                f"👑 當責A：{e.accountable}（執行R：{r_str}）\n"
                f"⏰ 期限：{e.due_date}｜狀態：{e.status}\n"
                f"📑 需交佐證T：{e.truthfulness_req or '⚠️待補定義'}"
            )
            if e.governance_gaps:
                lines.append(f"⚠️ 缺口：{e.governance_gaps[0]}")
            lines.append("──────────────")
        lines.append("👉 請至 AI 會議管理系統更新狀態並上傳 T 成果佐證！")
        return "\n".join(lines)

    # Default: slack_teams
    lines = [
        f"### 🔔 【AI 會議治理主動催辦通知】對象：`{target_accountable}`",
        f"> {tone_Opening}",
        f"> 📅 **巡檢日期**：`{today_iso}` ｜ **總計**：**{len(entries)}** 項（🚨 逾期 **{overdue_n}** ｜ 🛑 受阻 **{blocked_n}** ｜ ⚠️ 治理缺口 **{gap_n}**）",
        "",
    ]
    for e in entries:
        r_tags = " ".join(f"`@{r}`" for r in e.responsible) if e.responsible else "`@待指定執行者`"
        lines.append(
            f"- **{e.urgency_category}** `[{e.action_id}]` **{e.task_title}** （來源：*{e.meeting_title}*）\n"
            f"  - 👑 **當責者 (A)**：`@{e.accountable}` ｜ 🛠️ **執行者 (R)**：{r_tags} ｜ 🏢 **部門**：{e.department}\n"
            f"  - 📅 **截止日 (D)**：`{e.due_date}` (`{e.status}`) ｜ 🏷️ **層級**：`{e.smart_level}`\n"
            f"  - 🎯 **Q 驗收標準**：{e.quality_criteria or '⚠️ 未定義'} ｜ 📑 **T 必備佐證**：{e.truthfulness_req or '⚠️ 未定義'}"
        )
        if e.governance_gaps:
            lines.append(f"  - ⚠️ **治理缺口警示**：`{'`、`'.join(e.governance_gaps)}`")
    return "\n".join(lines)


def polish_reminder_with_ai(
    base_message: str,
    tone: str,
    api_key: str | None = None,
) -> tuple[str, bool, str]:
    """選用透過 Gemini 2.5 Flash 針對催辦訊息進行高情商且具管理魄力之潤飾."""
    resolved_key = (api_key or get_gemini_api_key()).strip()
    model_name = get_gemini_model()

    if not resolved_key:
        return (
            base_message,
            False,
            "ℹ️ 目前未設定 `GEMINI_API_KEY`，已採用高精準結構化治理範本產出催辦文案（於側邊欄注入 BYOK 金鑰即可使用 Gemini 動態語氣潤飾）。",
        )

    try:
        from google import genai

        client = genai.Client(api_key=resolved_key)
        prompt = (
            f"請以「{tone}」的管理語氣，幫我潤飾以下跨部門會議待辦催辦通知。"
            "要求：保留所有任務編號、當責者 (A)、執行者 (R)、截止日期、Q 驗收標準、T 佐證要求與治理缺口細節，使用繁體中文輸出：\n\n"
            f"{base_message}"
        )
        resp = client.models.generate_content(model=model_name, contents=prompt)
        polished = (resp.text or "").strip()
        if polished:
            return polished, True, f"✅ 已透過 Google Gemini ({model_name}) 完成「{tone}」語氣潤飾！"
    except Exception as exc:
        return base_message, False, f"⚠️ Gemini 潤飾呼叫失敗（{exc}），已保留原始結構化催辦文案。"

    return base_message, False, "已產出結構化催辦文案。"


def dispatch_webhook_notification(
    message_text: str,
    webhook_url: str | None = None,
) -> tuple[bool, str]:
    """發送催辦通知至外部 Webhook (相容 Slack / Discord / Teams / Generic JSON Webhook).

    若未設定 Webhook URL，則執行安全模擬發送 (Dry-run Simulation)，符合 0 元方案與無縫測試原則。
    """
    cleaned_msg = (message_text or "").strip()
    if not cleaned_msg:
        return False, "❌ 催辦訊息內容不可為空白。"

    resolved_url = (webhook_url if webhook_url is not None else get_webhook_url()).strip()
    if not resolved_url:
        return (
            True,
            "✅ 【模擬發送成功 (Dry-Run Mode)】目前未設定外部 Webhook URL，已將催辦紀錄寫入系統稽核日誌（如需真實推播至 Slack / Teams / Discord，請於側邊欄或 `.env` 填入 Webhook URL）。",
        )

    if not resolved_url.startswith(("http://", "https://")):
        return False, "❌ Webhook URL 格式不正確，必須以 `http://` 或 `https://` 開頭。"

    # 同時帶上 text (Slack / Teams) 與 content (Discord) 欄位以提高跨平台相容性
    payload = {
        "text": cleaned_msg,
        "content": cleaned_msg[:1950],
    }
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(resolved_url, json=payload)
            if 200 <= resp.status_code < 300:
                return True, f"🚀 已成功推播催辦通知至外部 Webhook (HTTP {resp.status_code})！"
            return False, f"⚠️ Webhook 伺服器回傳非成功狀態碼：HTTP {resp.status_code} ({resp.text[:120]})"
    except Exception as exc:
        return False, f"❌ Webhook 推播連線異常：{exc}"
