"""單元測試：驗證跨部門主動催辦與通知引擎 (`src/services/notification_service.py`)."""

from __future__ import annotations

from src.repositories.meeting_repo import get_sample_meetings
from src.services.notification_service import (
    build_line_flex_message,
    build_line_share_url,
    dispatch_line_messaging_push,
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


def test_line_zero_cost_share_flex_and_messaging_api(monkeypatch) -> None:
    """驗證 LINE 0 元一鍵分享連結、Flex 彩色行動卡組裝與 Messaging API 推播（含防呆與模擬發送）."""
    meetings = get_sample_meetings()
    entries = scan_followup_targets(meetings)
    line_msg = generate_channel_message(entries, channel="line", tone="溫和提醒 (Friendly)")

    # 1. 驗證 0 元無上限 LINE 一鍵分享 URL
    share_url = build_line_share_url(line_msg)
    assert share_url.startswith("https://line.me/R/share?text=")
    assert len(share_url) > 40

    # 2. 驗證 LINE Flex Message 彩色行動卡結構完整
    flex_obj = build_line_flex_message(entries, target_accountable="管理部", tone="溫和提醒 (Friendly)")
    assert flex_obj["type"] == "flex"
    assert flex_obj["contents"]["type"] == "bubble"
    assert "管理部" in flex_obj["altText"]

    # 3. 空訊息攔截
    ok_empty, _ = dispatch_line_messaging_push("", channel_access_token="", target_id="")
    assert ok_empty is False

    # 4. 未填憑證自動進入 0 元 Dry-Run 模擬模式
    ok_dry, msg_dry = dispatch_line_messaging_push(
        line_msg,
        entries=entries,
        channel_access_token="",
        target_id="",
    )
    assert ok_dry is True
    assert "Dry-Run Mode" in msg_dry

    # 5. 目標 ID 格式防呆（不可填 @lineid，須為 U/C/R 開頭之官方 33 碼識別碼）
    ok_bad_id, msg_bad_id = dispatch_line_messaging_push(
        line_msg,
        entries=entries,
        channel_access_token="dummy_channel_token_for_test",
        target_id="@wrong_handle",
    )
    assert ok_bad_id is False
    assert "格式不正確" in msg_bad_id

    # 6. 模擬成功呼叫 LINE Push API (HTTP 200)
    captured_payloads: list[dict] = []

    class _FakeResp:
        status_code = 200
        text = "{}"

    class _FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            pass

        def post(self, url: str, headers: dict, json: dict):
            captured_payloads.append({"url": url, "headers": headers, "json": json})
            return _FakeResp()

    import src.services.notification_service as notif_mod

    monkeypatch.setattr(notif_mod.httpx, "Client", _FakeClient)
    ok_push, msg_push = dispatch_line_messaging_push(
        line_msg,
        entries=entries,
        target_accountable="管理部",
        tone="溫和提醒 (Friendly)",
        use_flex_card=True,
        channel_access_token="dummy_channel_token_for_test",
        target_id="U1234567890abcdef1234567890abcdef",
    )
    assert ok_push is True
    assert "彩色 Flex 互動行動卡" in msg_push
    assert len(captured_payloads) == 1
    assert captured_payloads[0]["url"] == "https://api.line.me/v2/bot/message/push"
    assert captured_payloads[0]["json"]["to"] == "U1234567890abcdef1234567890abcdef"
    assert captured_payloads[0]["json"]["messages"][0]["type"] == "flex"
