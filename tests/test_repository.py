"""單元測試：驗證雙模資料庫儲存引擎 (SQLite Fallback / Supabase Schema 相容) CRUD、篩選與佐證閉環更新."""

from __future__ import annotations

from pathlib import Path

from src.repositories.meeting_repo import MeetingRepository
from src.schemas.models import (
    ActionItem,
    MeetingExtractionSchema,
    QCDTModel,
    RACIModel,
    SMARTGoalModel,
)


def test_repository_crud_and_sample_seeding(tmp_path: Path) -> None:
    """驗證本地 SQLite 備援模式之範例載入、新增、搜尋、篩選與刪除."""
    db_file = tmp_path / "test_meetings.db"
    repo = MeetingRepository(db_path=db_file, force_local=True)

    assert not repo.is_cloud_mode
    seeded_count = repo.ensure_sample_data_if_empty()
    assert seeded_count == 3

    all_meetings = repo.list_meetings()
    assert len(all_meetings) == 3

    # 測試關鍵字與部門篩選
    erp_meetings = repo.list_meetings(search_query="ERP", department_filter="採購部")
    assert len(erp_meetings) == 1
    assert "ERP" in erp_meetings[0].title

    # 測試新增自訂會議
    new_meeting = MeetingExtractionSchema(
        title="自動化測試新增會議",
        meeting_date="2026-11-10",
        departments=["QA 測試部"],
        attendees=["王測試"],
        executive_summary="執行 CRUD 測試",
        key_decisions=["通過 CRUD 驗收"],
        action_items=[
            ActionItem(
                id="ACT-999",
                task_title="驗證狀態更新與佐證卡控",
                department="QA 測試部",
                owner="王測試",
                due_date="2026-11-15",
                status="Pending",
                raci=RACIModel(accountable="王測試", responsible=["王測試"]),
                smart=SMARTGoalModel(
                    hierarchy_level="工作任務 (Work Task)",
                    specific="驗證資料庫讀寫",
                    measurable="pytest 100% 通過",
                    time_bound="2026-11-15",
                ),
                qcdt=QCDTModel(
                    quality_criteria="無錯誤拋出",
                    delivery_milestone="2026-11-15",
                    truthfulness_req="提供測試 Log",
                ),
            )
        ],
    )
    saved = repo.save_meeting(new_meeting, raw_transcript="王測試：執行 CRUD 測試。")
    assert saved.id is not None

    # 測試未提供佐證 T 時，將狀態改為 Done 會被拒絕
    ok_fail, msg_fail, _ = repo.update_action_item(
        meeting_id=saved.id,
        action_id="ACT-999",
        new_status="Done",
        evidence_submitted="",
        enforce_evidence_on_done=True,
    )
    assert ok_fail is False
    assert "Truthfulness/Evidence" in msg_fail

    # 測試提供具體佐證 T 後，將狀態改為 Done 成功持久化
    ok_pass, msg_pass, updated_rec = repo.update_action_item(
        meeting_id=saved.id,
        action_id="ACT-999",
        new_status="Done",
        evidence_submitted="pytest 執行完畢，100% PASSED (Log #881)",
        enforce_evidence_on_done=True,
    )
    assert ok_pass is True
    assert updated_rec is not None
    assert updated_rec.action_items[0].status == "Done"
    assert "Log #881" in updated_rec.action_items[0].qcdt.evidence_submitted

    # 測試刪除
    assert repo.delete_meeting(saved.id) is True
    assert repo.get_meeting_by_id(saved.id) is None
