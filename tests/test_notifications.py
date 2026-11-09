"""單元測試：驗證跨部門主動催辦與通知引擎 (`src/services/notification_service.py`)."""

from __future__ import annotations

from src.repositories.meeting_repo import get_sample_meetings
from src.services.notification_service import (
    dispatch_webhook_notification,
    generate_channel_message,
    group_by_accountable,
    polish_reminder_with_ai,
    scan_followup_targets,
)


def test_scan_and_group_followup_targets() -> None:
    """驗證從範例會議中自動掃描逾期、受阻與治理缺口任務，並依當責者 A 分群."""
    meetings = get_sample_meetings()
    entries = scan_followup_targets(meetings)
    assert len(entries) >= 2

    # 應包含逾期/受阻之 ACT-201 以及存在治理缺口之 ACT-103
    action_ids = {e.action_id for e in entries}
    assert "ACT-201" in action_ids
    assert "ACT-103" in action_ids

    groups = group_by_accountable(entries)
    assert len(groups) >= 2
    # 『待指定 (未明確歸屬)』應被優先排序於第一位以提醒指派當責者 A
    assert "待指定" in groups[0].accountable


def test_multi_channel_digest_generation() -> None:
    """驗證 Email、Slack/Teams 與 LINE 三種通道催辦文案生成."""
    meetings = get_sample_meetings()
    entries = scan_followup_targets(meetings)

    slack_msg = generate_channel_message(entries, channel="slack_teams", tone="嚴謹稽核 (Audit)")
    assert "AI 會議治理主動催辦通知" in slack_msg
    assert "ACT-201" in slack_msg

    email_msg = generate_channel_message(entries, channel="email", tone="高階升級預警 (Escalation)")
    assert "主旨：【AI 會議治理催辦】" in email_msg
    assert "高階管理升級預警" in email_msg

    line_msg = generate_channel_message(entries, channel="line", tone="溫和提醒 (Friendly)")
    assert "🔔【會議當責催辦" in line_msg
    assert "需交佐證T" in line_msg


def test_webhook_dry_run_and_validation() -> None:
    """驗證 Webhook 推播之空訊息攔截、非法 URL 攔截與零成本 Dry-run 模擬發送."""
    ok_empty, _ = dispatch_webhook_notification("", webhook_url="")
    assert ok_empty is False

    ok_bad_url, msg_bad = dispatch_webhook_notification("測試通知", webhook_url="ftp://invalid-url")
    assert ok_bad_url is False
    assert "格式不正確" in msg_bad

    ok_dry, msg_dry = dispatch_webhook_notification("測試通知內容", webhook_url="")
    assert ok_dry is True
    assert "Dry-Run Mode" in msg_dry

    polished, used_gemini, _ = polish_reminder_with_ai("原始催辦內容", tone="嚴謹稽核 (Audit)", api_key="")
    assert used_gemini is False
    assert polished == "原始催辦內容"
