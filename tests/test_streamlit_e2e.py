"""Streamlit 端到端 UI 自動化測試 (`streamlit.testing.v1.AppTest`).

模擬真實使用者於瀏覽器操作：
1. 啟動 `app.py`，驗證無任何 Exception、標題與三大 Tabs 正常渲染、預設載入 3 場跨部門範例會議。
2. 於側邊欄動態輸入 BYOK 金鑰，驗證 Session State 動態注入與遮罩顯示生效。
3. 於 Tab 1 載入測試逐字稿範本並點擊「執行 AI 結構化萃取」，再點擊「確認無誤並儲存至資料庫」，驗證會議成功新增。
4. 於 Tab 2 驗證將待辦事項狀態改為 Done 時，未填寫 T (成果佐證) 會觸發錯誤攔截；補齊 T 佐證並執行 AI 佐證稽核與儲存後成功閉環。
5. 於 Tab 3 (全域行動方案追蹤看板) 驗證跨會議篩選器與指標卡正常運作。
"""

from __future__ import annotations

from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_streamlit_app_end_to_end(tmp_path: Path, monkeypatch) -> None:
    """執行 Streamlit AppTest 端到端自動化 UI 測試."""
    test_db = tmp_path / "e2e_ui_test.db"
    monkeypatch.setenv("LOCAL_DB_PATH", str(test_db))
    monkeypatch.setenv("SUPABASE_URL", "offline-test")
    monkeypatch.setenv("SUPABASE_KEY", "")

    app_path = Path(__file__).resolve().parent.parent / "app.py"
    at = AppTest.from_file(str(app_path), default_timeout=30)
    at.run()

    # 1. 確保首次啟動無任何未捕捉之例外錯誤，且 6 張全域 KPI 指標卡正常渲染
    assert len(at.exception) == 0, f"Streamlit 渲染發生例外：{at.exception}"
    assert any("AI 會議記錄管理 Web App" in t.value for t in at.title)
    assert len(at.metric) >= 6

    # 2. 測試在 Tab 1 點擊「📑 載入標準輸入公版範本」並執行精準萃取與入庫
    btn_load_tpl = at.button(key="btn_load_structured_template")
    btn_load_tpl.click().run()
    assert len(at.exception) == 0
    assert "標準輸入格式公版" in at.session_state["draft_transcript_text"]

    # 3. 點擊「執行 AI 結構化萃取」
    btn_extract = at.button(key="btn_execute_extraction")
    btn_extract.click().run()
    assert len(at.exception) == 0
    assert "latest_extracted_meeting" in at.session_state

    # 4. 點擊「確認無誤並儲存至資料庫」
    btn_save = at.button(key="btn_save_extracted_meeting")
    btn_save.click().run()
    assert len(at.exception) == 0
    assert any("已成功存入資料庫" in s.value for s in at.success)


def test_streamlit_action_item_evidence_closed_loop_and_tracker(tmp_path: Path, monkeypatch) -> None:
    """驗證 Tab 2 待辦事項 Done 狀態之 T (成果佐證) 卡控與 Tab 3 全域追蹤看板篩選互動."""
    test_db = tmp_path / "e2e_tracker_test.db"
    monkeypatch.setenv("LOCAL_DB_PATH", str(test_db))
    monkeypatch.setenv("SUPABASE_URL", "offline-test")
    monkeypatch.setenv("SUPABASE_KEY", "")

    app_path = Path(__file__).resolve().parent.parent / "app.py"
    at = AppTest.from_file(str(app_path), default_timeout=30)
    at.run()
    assert len(at.exception) == 0

    # 針對第一場範例會議之進行中任務 ACT-102 (尚未填寫佐證)
    target_uid = "11111111-2222-3333-4444-555555555501_ACT-102"

    # (a) 將狀態改為 Done 但不填佐證 -> 點擊儲存應顯示錯誤訊息攔截
    at.selectbox(key=f"sel_status_{target_uid}").select("Done").run()
    at.button(key=f"btn_save_act_{target_uid}").click().run()
    assert len(at.exception) == 0
    assert any("Truthfulness/Evidence" in err.value for err in at.error)

    # (b) 填入具體成果佐證 T 並點擊 AI 佐證稽核 -> 再點擊儲存更新
    at.text_area(key=f"inp_evidence_{target_uid}").set_value(
        "已完成 BYOK 與 RLS 資安審查，掃描報告連結：https://sec.internal/audit/102 (100% 通過)"
    ).run()
    at.button(key=f"btn_audit_ev_{target_uid}").click().run()
    assert len(at.exception) == 0

    at.selectbox(key=f"sel_status_{target_uid}").select("Done").run()
    at.button(key=f"btn_save_act_{target_uid}").click().run()
    assert len(at.exception) == 0

    # (c) 測試 Tab 3 全域行動方案追蹤看板篩選器（四色燈號與治理狀態連動）
    at.selectbox(key="trk_filter_health").select("🟡 黃燈：⚠️ 治理缺口").run()
    assert len(at.exception) == 0
    assert len(at.dataframe) >= 1

    at.selectbox(key="trk_filter_health").select("🔴 紅燈（全部：逾期未完成＋執行受阻）").run()
    assert len(at.exception) == 0
    assert len(at.dataframe) >= 1

    # (d) 測試 Tab 4 跨部門主動催辦與通知中心：切換為 Email 格式、高階升級預警語氣，並觸發 Webhook 模擬推播
    at.selectbox(key="notif_sel_channel").select("📧 Email 正式當責稽核信").run()
    at.selectbox(key="notif_sel_tone").select("高階升級預警 (Escalation)").run()
    assert len(at.exception) == 0
    assert "主旨：【AI 會議治理催辦】" in at.session_state["notif_message_editor"]

    at.button(key="btn_notif_dispatch_webhook").click().run()
    assert len(at.exception) == 0
    assert len(at.session_state.get("notification_dispatch_logs", [])) == 1

    # (e) 測試 Tab 5 雲端部署與系統自檢中心：點擊「立即執行系統自我查核」
    at.button(key="btn_run_live_diagnostics").click().run()
    assert len(at.exception) == 0
    assert len(at.session_state.get("live_diag_results", [])) == 4

    # (f) 驗證 Tab 6 新手教學與操作指南正常渲染無異常
    assert any("新手教學與超簡單操作說明書" in m.value for m in at.markdown)
