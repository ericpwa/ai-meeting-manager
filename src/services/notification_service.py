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
from typing import Any, Literal
from urllib.parse import quote

import httpx
from pydantic import BaseModel, Field

from src.config import (
    build_genai_clients,
    get_candidate_gemini_models,
    get_gemini_api_key,
    get_gemini_model,
    get_line_channel_access_token,
    get_line_target_id,
    get_webhook_url,
)
from src.schemas.models import ActionItem, MeetingRecord
from src.services.governance import get_taiwan_today, is_action_overdue


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
    entries: list[FollowUpTaskEntry] = []

    for m in meetings:
        for act in m.action_items:
            if act.status == "Done" and not act.governance_gaps:
                continue

            is_overdue, days_delta = is_action_overdue(act, reference_date=reference_date)
            is_due_soon = bool(
                act.status != "Done"
                and not is_overdue
                and days_delta is not None
                and 0 <= days_delta <= 3
            )

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
    today_iso = get_taiwan_today().isoformat()
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
    resolved_key = (api_key if api_key is not None else get_gemini_api_key()).strip()
    model_name = get_gemini_model()

    if not resolved_key:
        return (
            base_message,
            False,
            "ℹ️ 目前未設定 `GEMINI_API_KEY`，已採用高精準結構化治理範本產出催辦文案（於側邊欄注入 BYOK 金鑰即可使用 Gemini 動態語氣潤飾）。",
        )

    try:
        prompt = (
            f"請以「{tone}」的管理語氣，幫我潤飾以下跨部門會議待辦催辦通知。"
            "要求：保留所有任務編號、當責者 (A)、執行者 (R)、截止日期、Q 驗收標準、T 佐證要求與治理缺口細節，使用繁體中文輸出：\n\n"
            f"{base_message}"
        )
        last_exc: Exception | None = None
        for client, mode_label in build_genai_clients(resolved_key):
            for cand_model in get_candidate_gemini_models(model_name):
                try:
                    resp = client.models.generate_content(model=cand_model, contents=prompt)
                    polished = (resp.text or "").strip()
                    if polished:
                        return polished, True, f"✅ 已透過 Google Gemini ({cand_model} / {mode_label}) 完成「{tone}」語氣潤飾！"
                except Exception as inner_exc:
                    last_exc = inner_exc
                    continue
        if last_exc is not None:
            raise last_exc
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


LINE_BOT_INFO_API_URL = "https://api.line.me/v2/bot/info"
LINE_PUSH_API_URL = "https://api.line.me/v2/bot/message/push"
LINE_QUOTA_API_URL = "https://api.line.me/v2/bot/message/quota"
LINE_QUOTA_CONSUMPTION_URL = "https://api.line.me/v2/bot/message/quota/consumption"
_LINE_TARGET_ID_PATTERN = re.compile(r"^[UCR][0-9a-fA-F]{16,}$")
# LINE line.me / access.line.me (OpenResty 8KB URI 上限，含 OAuth 跳轉雙重編碼安全邊際)
LINE_SHARE_MAX_ENCODED_LEN = 1400


def _truncate_by_encoded_len(text: str, max_encoded_len: int, suffix: str = "\n…（完整清單請用一鍵複製或見系統）") -> tuple[str, bool]:
    """依據 URL-encoded 位元組長度安全截斷文字，徹底杜絕 OpenResty `414 Request-URI Too Large`."""
    cleaned = (text or "").strip()
    if len(quote(cleaned, safe="")) <= max_encoded_len:
        return cleaned, False

    suffix_encoded_len = len(quote(suffix, safe=""))
    budget = max(120, max_encoded_len - suffix_encoded_len)

    # 逐行優先保留完整段落；若首行就超長則逐字截斷
    out_chars: list[str] = []
    used = 0
    for ch in cleaned:
        ch_len = len(quote(ch, safe=""))
        if used + ch_len > budget:
            break
        out_chars.append(ch)
        used += ch_len

    shortened = "".join(out_chars).rstrip()
    # 盡量在換行處收尾，避免截斷在句子中間
    last_nl = shortened.rfind("\n")
    if last_nl >= max(40, int(len(shortened) * 0.65)):
        shortened = shortened[:last_nl].rstrip()
    return shortened + suffix, True


def build_line_share_payload(
    message_text: str,
    entries: list[FollowUpTaskEntry] | None = None,
    target_accountable: str = "全體當責人",
    max_encoded_len: int = LINE_SHARE_MAX_ENCODED_LEN,
) -> tuple[str, str, bool]:
    """產出保證不觸發 `414 Request-URI Too Large` 之 LINE 官方一鍵分享連結與預覽文本.

    回傳:
        (share_url, final_text_in_url, was_shortened)
    """
    cleaned = (message_text or "").strip()
    if len(quote(cleaned, safe="")) <= max_encoded_len:
        return f"https://line.me/R/share?text={quote(cleaned, safe='')}", cleaned, False

    # 若原文經 UTF-8 URL 編碼後超出 OpenResty 安全門檻，改組裝結構化精簡摘要（維持高可讀性）
    if entries:
        today_iso = get_taiwan_today().isoformat()
        overdue_n = sum(1 for e in entries if e.urgency_category == "🚨 逾期未完成")
        blocked_n = sum(1 for e in entries if e.urgency_category == "🛑 執行受阻 (Blocked)")
        gap_n = sum(1 for e in entries if e.urgency_category == "⚠️ 治理缺口待補齊")
        soon_n = sum(1 for e in entries if e.urgency_category == "⏳ 3日內即將到期")

        summary_lines = [
            f"🔔【會議催辦｜{target_accountable}】{today_iso}",
            f"共{len(entries)}項：🔴逾期{overdue_n} / 🛑受阻{blocked_n} / ⚠️缺口{gap_n} / ⏳到期{soon_n}",
        ]
        suffix = f"\n…（共{len(entries)}項，完整明細請見會議系統）"
        suffix_len = len(quote(suffix, safe=""))
        budget = max(200, max_encoded_len - suffix_len)

        current_text = "\n".join(summary_lines)
        shown = 0
        for idx, e in enumerate(entries, start=1):
            light = "🔴" if e.urgency_category in {"🚨 逾期未完成", "🛑 執行受阻 (Blocked)"} else "🟡"
            title_short = (e.task_title or "待辦事項").strip()[:18]
            line = f"{idx}.{light}[{e.action_id}]{title_short}({e.due_date})"
            candidate = current_text + "\n" + line
            if len(quote(candidate, safe="")) > budget:
                break
            current_text = candidate
            shown += 1

        if shown < len(entries):
            final_text = current_text + suffix
        else:
            final_text = current_text
        # 雙重防呆確保絕對不超過 max_encoded_len
        final_text, _ = _truncate_by_encoded_len(final_text, max_encoded_len=max_encoded_len, suffix="…")
        return f"https://line.me/R/share?text={quote(final_text, safe='')}", final_text, True

    final_text, was_short = _truncate_by_encoded_len(cleaned, max_encoded_len=max_encoded_len)
    return f"https://line.me/R/share?text={quote(final_text, safe='')}", final_text, was_short


def build_line_share_url(message_text: str, max_encoded_len: int = LINE_SHARE_MAX_ENCODED_LEN) -> str:
    """產出 LINE 官方 0 元無上限一鍵分享連結 (`https://line.me/R/share?text=...`).

    嚴格依 URL-encoded 位元組上限截斷，徹底避免 `414 Request-URI Too Large (openresty)`。
    """
    share_url, _, _ = build_line_share_payload(message_text, max_encoded_len=max_encoded_len)
    return share_url


def build_line_flex_message(
    entries: list[FollowUpTaskEntry],
    target_accountable: str = "全體當責人",
    tone: str = "嚴謹稽核 (Audit)",
) -> dict[str, Any]:
    """建置 LINE Messaging API 官方彩色 Flex Message 精簡行動卡（單則推播即可呈現完整治理摘要）."""
    today_iso = get_taiwan_today().isoformat()
    overdue_n = sum(1 for e in entries if e.urgency_category == "🚨 逾期未完成")
    blocked_n = sum(1 for e in entries if e.urgency_category == "🛑 執行受阻 (Blocked)")
    gap_n = sum(1 for e in entries if e.urgency_category == "⚠️ 治理缺口待補齊")
    soon_n = sum(1 for e in entries if e.urgency_category == "⏳ 3日內即將到期")

    body_contents: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": f"對象：{target_accountable} ｜ 基準日：{today_iso}",
            "size": "xs",
            "color": "#475569",
            "wrap": True,
        },
        {
            "type": "box",
            "layout": "horizontal",
            "margin": "md",
            "spacing": "sm",
            "contents": [
                {
                    "type": "text",
                    "text": f"🔴逾期 {overdue_n}",
                    "size": "xs",
                    "weight": "bold",
                    "color": "#DC2626",
                    "flex": 1,
                },
                {
                    "type": "text",
                    "text": f"🛑受阻 {blocked_n}",
                    "size": "xs",
                    "weight": "bold",
                    "color": "#B91C1C",
                    "flex": 1,
                },
                {
                    "type": "text",
                    "text": f"⚠️缺口 {gap_n}",
                    "size": "xs",
                    "weight": "bold",
                    "color": "#D97706",
                    "flex": 1,
                },
                {
                    "type": "text",
                    "text": f"⏳到期 {soon_n}",
                    "size": "xs",
                    "weight": "bold",
                    "color": "#B45309",
                    "flex": 1,
                },
            ],
        },
        {"type": "separator", "margin": "md"},
    ]

    if not entries:
        body_contents.append(
            {
                "type": "text",
                "text": "✅ 目前名下所有任務皆按期推進且無任何 RACI / SMART / QCD+T 治理缺口！",
                "size": "sm",
                "color": "#059669",
                "margin": "md",
                "wrap": True,
            }
        )
    else:
        for e in entries[:8]:
            is_red = e.urgency_category in {"🚨 逾期未完成", "🛑 執行受阻 (Blocked)"}
            badge_color = "#DC2626" if is_red else "#D97706"
            r_str = "、".join(e.responsible) if e.responsible else "待指定"
            safe_title = (e.task_title or "未命名待辦事項").strip()[:60] or "未命名待辦事項"
            safe_acc = (e.accountable or "待指定").strip() or "待指定"
            safe_due = (e.due_date or "待定").strip() or "待定"
            safe_t = (e.truthfulness_req or "待補定義").strip()[:80] or "待補定義"
            body_contents.append(
                {
                    "type": "box",
                    "layout": "vertical",
                    "margin": "md",
                    "spacing": "xs",
                    "contents": [
                        {
                            "type": "text",
                            "text": f"{e.urgency_category} [{e.action_id or 'ACT'}]",
                            "size": "xs",
                            "weight": "bold",
                            "color": badge_color,
                            "wrap": True,
                        },
                        {
                            "type": "text",
                            "text": safe_title,
                            "size": "sm",
                            "weight": "bold",
                            "color": "#0F172A",
                            "wrap": True,
                        },
                        {
                            "type": "text",
                            "text": f"👑 A:{safe_acc} ｜ 🛠️ R:{r_str}",
                            "size": "xs",
                            "color": "#334155",
                            "wrap": True,
                        },
                        {
                            "type": "text",
                            "text": f"⏰ 期限:{safe_due} ｜ 📑 佐證T:{safe_t}",
                            "size": "xs",
                            "color": "#64748B",
                            "wrap": True,
                        },
                    ],
                }
            )
            body_contents.append({"type": "separator", "margin": "sm"})

        if len(entries) > 8:
            body_contents.append(
                {
                    "type": "text",
                    "text": f"…其餘尚有 {len(entries) - 8} 項待處理任務，請登入 AI 會議管理系統檢視。",
                    "size": "xs",
                    "color": "#64748B",
                    "margin": "sm",
                    "wrap": True,
                }
            )

    alt_text = f"🔔 會議當責催辦｜{target_accountable}（共 {len(entries)} 項：逾期 {overdue_n} / 受阻 {blocked_n} / 缺口 {gap_n}）"
    return {
        "type": "flex",
        "altText": alt_text[:400],
        "contents": {
            "type": "bubble",
            "size": "mega",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#162238",
                "paddingAll": "14px",
                "contents": [
                    {
                        "type": "text",
                        "text": "🛡️ AI 會議治理當責催辦行動卡",
                        "color": "#FFFFFF",
                        "weight": "bold",
                        "size": "md",
                    },
                    {
                        "type": "text",
                        "text": f"INPOWER 充霸 · 語氣：{tone}",
                        "color": "#BAE6FD",
                        "size": "xs",
                        "margin": "xs",
                    },
                ],
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "paddingAll": "14px",
                "contents": body_contents,
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#F8FAFC",
                "paddingAll": "10px",
                "contents": [
                    {
                        "type": "text",
                        "text": "👉 完成時請回系統填寫 T 成果佐證始可結案 (Done)",
                        "size": "xs",
                        "color": "#1E4E79",
                        "weight": "bold",
                        "align": "center",
                        "wrap": True,
                    }
                ],
            },
        },
    }


def dispatch_line_messaging_push(
    message_text: str,
    entries: list[FollowUpTaskEntry] | None = None,
    target_accountable: str = "全體當責人",
    tone: str = "嚴謹稽核 (Audit)",
    use_flex_card: bool = True,
    channel_access_token: str | None = None,
    target_id: str | None = None,
) -> tuple[bool, str]:
    """透過 LINE 官方 Messaging API (`POST /v2/bot/message/push`) 推播精簡行動卡或 Flex 彩色卡片.

    支援：
    - 0 元輕用量方案（每月免費 200 則主動推播，推薦私訊當責者 A 最省額度）
    - 支援逗號分隔多個目標 ID（`U...` 個人 User ID、`C...` 群組 Group ID、`R...` 聊天室 Room ID）
    - 未填入憑證時採安全模擬推播 (Dry-Run Mode)，確保零設定亦可測試稽核紀錄
    """
    cleaned_msg = (message_text or "").strip()
    if not cleaned_msg:
        return False, "❌ LINE 催辦訊息內容不可為空白。"

    resolved_token = (
        channel_access_token if channel_access_token is not None else get_line_channel_access_token()
    ).strip().strip('"').strip("'")
    resolved_target_raw = (target_id if target_id is not None else get_line_target_id()).strip().strip('"').strip("'")

    if not resolved_token or not resolved_target_raw:
        return (
            True,
            "✅ 【LINE 模擬推播成功 (Dry-Run Mode)】目前尚未設定 `LINE_CHANNEL_ACCESS_TOKEN` 或 `LINE_TARGET_ID`。"
            "您可直接點擊上方 **「📲 一鍵開啟 LINE 傳送（0 元免費無上限）」** 立即發送，或於左側邊欄填入 LINE 官方帳號憑證啟用機器人自動推播（0 元方案每月 200 則）。",
        )

    targets = [t.strip().strip('"').strip("'") for t in re.split(r"[,，、;\s]+", resolved_target_raw) if t.strip()]
    invalid_targets = [t for t in targets if not _LINE_TARGET_ID_PATTERN.match(t)]
    if invalid_targets:
        return (
            False,
            f"❌ LINE 目標 ID 格式不正確：`{', '.join(invalid_targets)}`。"
            "請填入官方 `U` 開頭（個人 User ID）、`C` 開頭（群組 Group ID）或 `R` 開頭（聊天室 ID）之 33 碼英數識別碼（不是 `@xxx` LINE ID）。",
        )

    if use_flex_card and entries is not None:
        message_obj: dict[str, Any] = build_line_flex_message(
            entries=entries,
            target_accountable=target_accountable,
            tone=tone,
        )
        mode_tag = "彩色 Flex 互動行動卡"
    else:
        message_obj = {"type": "text", "text": cleaned_msg[:4900]}
        mode_tag = "精簡文字行動卡"

    headers = {
        "Authorization": f"Bearer {resolved_token}",
        "Content-Type": "application/json",
    }

    sent_ok = 0
    errors: list[str] = []
    try:
        with httpx.Client(timeout=12.0) as client:
            for tid in targets:
                resp = client.post(
                    LINE_PUSH_API_URL,
                    headers=headers,
                    json={"to": tid, "messages": [message_obj]},
                )
                if 200 <= resp.status_code < 300:
                    sent_ok += 1
                elif resp.status_code == 401:
                    errors.append(f"{tid[:6]}...: HTTP 401（Channel Access Token 無效或已過期，請到 Messaging API 頁面最下方重新 Issue）")
                elif resp.status_code == 400:
                    errors.append(
                        f"{tid[:6]}...: HTTP 400（請確認已先將機器人加為好友／拉進群組，且目標 ID 正確；LINE 回覆：{resp.text[:120]}）"
                    )
                elif resp.status_code == 429:
                    errors.append(f"{tid[:6]}...: HTTP 429（本月 200 則免費推播額度已達上限，請改用方案 ① 0 元一鍵分享或升級方案）")
                else:
                    errors.append(f"{tid[:6]}...: HTTP {resp.status_code} ({resp.text[:120]})")
    except Exception as exc:
        return False, f"❌ LINE Messaging API 連線異常：{exc}"

    if sent_ok == len(targets):
        return True, f"🚀 已透過 LINE Messaging API 成功推播「{mode_tag}」至 {sent_ok} 個目標！"
    if sent_ok > 0:
        return False, f"⚠️ 部分成功（{sent_ok}/{len(targets)}），失敗明細：{'；'.join(errors)}"
    return False, f"❌ LINE 推播失敗：{'；'.join(errors)}"


def fetch_line_bot_quota(channel_access_token: str | None = None) -> tuple[bool, dict[str, Any], str]:
    """免費驗證 LINE 官方帳號機器人連線（`/v2/bot/info`）並查詢本月免費／方案推播額度與已使用則數（0 額度消耗）."""
    resolved_token = (
        channel_access_token if channel_access_token is not None else get_line_channel_access_token()
    ).strip().strip('"').strip("'")
    if not resolved_token:
        return False, {}, "ℹ️ 請先於左側邊欄填入 `LINE_CHANNEL_ACCESS_TOKEN` 才可驗證機器人連線與查詢本月剩餘額度。"

    headers = {"Authorization": f"Bearer {resolved_token}"}
    try:
        with httpx.Client(timeout=10.0) as client:
            r_info = client.get(LINE_BOT_INFO_API_URL, headers=headers)
            r_quota = client.get(LINE_QUOTA_API_URL, headers=headers)
            r_used = client.get(LINE_QUOTA_CONSUMPTION_URL, headers=headers)
            if r_quota.status_code != 200 or r_used.status_code != 200:
                hint = "Token 無效或已過期，請回到 Messaging API 頁籤最底部重新 Issue 權杖" if 401 in {r_quota.status_code, r_used.status_code} else "請確認網路與 Token 設定"
                return (
                    False,
                    {},
                    f"⚠️ 驗證失敗（HTTP {r_quota.status_code} / {r_used.status_code}）：{hint}。",
                )
            bot_label = ""
            if r_info.status_code == 200:
                info_json = r_info.json()
                b_name = info_json.get("displayName", "")
                b_id = info_json.get("basicId", "")
                if b_name:
                    bot_label = f"✅ 機器人連線正常：【**{b_name}**】(`{b_id}`) ｜ "
            q_data = r_quota.json()
            u_data = r_used.json()
            limit_val = q_data.get("value")
            used_val = int(u_data.get("totalUsage", 0))
            remaining = (int(limit_val) - used_val) if isinstance(limit_val, int) else None
            info = {
                "type": q_data.get("type", "limited"),
                "limit": limit_val,
                "used": used_val,
                "remaining": remaining,
            }
            if remaining is not None:
                return True, info, f"{bot_label}📊 本月 LINE 主動推播額度：已使用 **{used_val} / {limit_val}** 則，剩餘 **{max(remaining, 0)}** 則。"
            return True, info, f"{bot_label}📊 本月 LINE 主動推播已使用 **{used_val}** 則（方案無硬性上限）。"
    except Exception as exc:
        return False, {}, f"❌ LINE 連線與額度查詢異常：{exc}"
