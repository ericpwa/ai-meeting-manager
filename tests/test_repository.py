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


def test_batch_update_and_safe_deletion_protect_existing_data(tmp_path: Path) -> None:
    """驗證看板二一鍵批次更新（含 QCD+T 攔截）、看板三精準刪除重複任務／會議與系統名冊防誤刪保護."""
    from src.repositories.meeting_repo import ORG_DIRECTORY_RECORD_ID

    db_file = tmp_path / "batch_del_test.db"
    repo = MeetingRepository(db_path=db_file, force_local=True)
    repo.save_org_directory(["綠能部"], ["王經理"])

    schema = MeetingExtractionSchema(
        title="批次更新與重複清理測試會議",
        meeting_date="2026-11-23",
        departments=["綠能部"],
        attendees=["王經理", "李工程師"],
        executive_summary="測試批次更新與精準刪除",
        key_decisions=["決議一"],
        action_items=[
            ActionItem(
                id="ACT-01",
                task_title="任務一（測試批次正常更新）",
                department="綠能部",
                owner="王經理",
                due_date="2026-11-20",
                status="Pending",
                raci=RACIModel(accountable="王經理", responsible=["王經理"]),
                smart=SMARTGoalModel(specific="完成一", measurable="100%", time_bound="2026-11-20"),
                qcdt=QCDTModel(quality_criteria="Q1", delivery_milestone="D1", truthfulness_req="T1"),
            ),
            ActionItem(
                id="ACT-02",
                task_title="任務二（測試 Done 無 T 佐證被攔截）",
                department="綠能部",
                owner="李工程師",
                due_date="2026-11-22",
                status="In Progress",
                raci=RACIModel(accountable="李工程師", responsible=["李工程師"]),
                smart=SMARTGoalModel(specific="完成二", measurable="100%", time_bound="2026-11-22"),
                qcdt=QCDTModel(quality_criteria="Q2", delivery_milestone="D2", truthfulness_req="T2"),
            ),
            ActionItem(
                id="ACT-01",
                task_title="任務一（同編號重複副本）",
                department="綠能部",
                owner="王經理",
                due_date="2026-11-20",
                status="Pending",
                raci=RACIModel(accountable="王經理", responsible=["王經理"]),
                smart=SMARTGoalModel(specific="完成一", measurable="100%", time_bound="2026-11-20"),
                qcdt=QCDTModel(quality_criteria="Q1", delivery_milestone="D1", truthfulness_req="T1"),
            ),
        ],
    )
    saved = repo.save_meeting(schema)

    # 1. 一鍵批次更新：ACT-01 (index=0) 改為 Done 並附上 T 佐證（成功）；ACT-02 (index=1) 改為 Done 但缺 T 佐證（攔截）
    updated_n, blocked_msgs, updated_m = repo.batch_update_meeting_action_items(
        meeting_id=saved.id,
        updates=[
            {
                "item_index": 0,
                "action_id": "ACT-01",
                "status": "Done",
                "evidence_submitted": "已提交驗收報告 https://internal/report/1",
                "due_date": "2026-11-21",
            },
            {
                "item_index": 1,
                "action_id": "ACT-02",
                "status": "Done",
                "evidence_submitted": "",
            },
        ],
        enforce_evidence_on_done=True,
    )
    assert updated_n == 1
    assert len(blocked_msgs) == 1
    assert "ACT-02" in blocked_msgs[0]
    assert updated_m is not None
    assert updated_m.action_items[0].status == "Done"
    assert updated_m.action_items[0].due_date == "2026-11-21"
    assert updated_m.action_items[1].status == "In Progress"  # 未被錯誤改為 Done
    assert updated_m.action_items[2].status == "Pending"  # 同 ID 副本未被誤蓋

    # 2. 精準刪除第 3 項重複副本 (index=2, id="ACT-01")，確認第 1 項 (index=0) 完整保留
    del_act_cnt, del_m_cnt, del_msg = repo.delete_action_items_by_keys(
        targets=[(saved.id, 2, "ACT-01")],
        remove_empty_meetings=False,
    )
    assert del_act_cnt == 1
    assert del_m_cnt == 0
    assert "已安全刪除 1 項" in del_msg
    reloaded = repo.get_meeting_by_id(saved.id)
    assert reloaded is not None
    assert len(reloaded.action_items) == 2
    assert reloaded.action_items[0].status == "Done"

    # 3. 驗證系統組織名冊紀錄絕不可被刪除
    assert repo.delete_meeting(ORG_DIRECTORY_RECORD_ID) is False
    del_m_cnt2, _ = repo.batch_delete_meetings([ORG_DIRECTORY_RECORD_ID, saved.id])
    assert del_m_cnt2 == 1
    assert repo.get_meeting_by_id(saved.id) is None
    saved_depts, saved_persons = repo.get_org_directory(include_from_meetings=False)
    assert "綠能部" in saved_depts
    assert "王經理" in saved_persons
