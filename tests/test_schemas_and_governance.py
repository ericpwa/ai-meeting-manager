"""單元測試：驗證 RACI、SMART Goals、QCD+T 資料模型與治理稽核邏輯."""

from __future__ import annotations

from src.schemas.models import (
    ActionItem,
    MeetingExtractionSchema,
    QCDTModel,
    RACIModel,
    SMARTGoalModel,
)
from src.services.governance import (
    audit_action_item_governance,
    audit_meeting_extraction,
    compute_governance_metrics,
    has_multiple_accountables,
    validate_done_transition,
)


def test_raci_single_accountable_enforcement() -> None:
    """驗證 RACI 原則：每項任務須有且只有一名最終當責者 A；若填寫多人或未指定應產生治理缺口警示."""
    assert has_multiple_accountables("王小明、李大華") is True
    assert has_multiple_accountables("產品部 / 研發部") is True
    assert has_multiple_accountables("全體共同當責") is True
    assert has_multiple_accountables("林雅婷 (AI 架構師)") is False

    # 測試多人當責違規偵測
    item_multi = ActionItem(
        id="ACT-T1",
        task_title="跨部門資料庫遷移",
        department="資訊部 / 研發部",
        owner="王小明, 李大華",
        due_date="2026-12-01",
        status="Pending",
        raci=RACIModel(
            accountable="王小明, 李大華",
            responsible=["王小明", "李大華"],
        ),
        smart=SMARTGoalModel(
            hierarchy_level="工作任務 (Work Task)",
            specific="遷移 PostgreSQL",
            measurable="零停機完成",
            time_bound="2026-12-01",
        ),
        qcdt=QCDTModel(
            quality_criteria="數據一致性 100%",
            cost_budget="0 元",
            delivery_milestone="2026-12-01",
            truthfulness_req="提供遷移校驗報告連結",
        ),
    )
    audited = audit_action_item_governance(item_multi)
    assert any("RACI 違規" in g for g in audited.governance_gaps)

    # 測試缺少當責者 A 偵測
    item_empty_a = ActionItem(
        id="ACT-T2",
        task_title="未指派當責人之跨部門任務",
        raci=RACIModel(accountable="", responsible=["張三"]),
    )
    audited_empty = audit_action_item_governance(item_empty_a)
    assert audited_empty.raci.accountable == "待指定 (未明確歸屬)"
    assert any("缺少最終當責者 (A)" in g for g in audited_empty.governance_gaps)


def test_smart_hierarchy_and_qcdt_gap_detection() -> None:
    """驗證 SMART 四階層級分類與 QCD+T 缺口主動偵測."""
    incomplete_item = ActionItem(
        id="ACT-T3",
        task_title="模糊的行動事項",
        due_date="待定",
        raci=RACIModel(accountable="陳經理", responsible=["李專員"]),
        smart=SMARTGoalModel(
            hierarchy_level="個別活動 (Individual Activity)",
            specific="",
            measurable="",
            time_bound="",
        ),
        qcdt=QCDTModel(
            quality_criteria="",
            cost_budget="",
            delivery_milestone="",
            truthfulness_req="",
        ),
    )
    audited = audit_action_item_governance(incomplete_item)
    assert audited.smart.is_smart_compliant is False
    assert audited.qcdt.cost_budget == "0 元 (內部資源/工時)"
    assert any("SMART 缺口" in g for g in audited.governance_gaps)
    assert any("未定義 Q" in g for g in audited.governance_gaps)
    assert any("未定義 T" in g for g in audited.governance_gaps)


def test_done_status_requires_truthfulness_evidence() -> None:
    """驗證 QCD+T 中將狀態改為 Done 時必須提供 T (成果佐證)."""
    item = ActionItem(
        id="ACT-T4",
        task_title="完成資安弱點掃描",
        raci=RACIModel(accountable="張志豪 (資安官)", responsible=["張志豪 (資安官)"]),
    )
    ok_empty, msg_empty = validate_done_transition(item, "Done", "")
    assert ok_empty is False
    assert "Truthfulness/Evidence" in msg_empty

    ok_valid, msg_valid = validate_done_transition(
        item, "Done", "已完成掃描，0 高風險弱點，報告連結：https://internal.sec/report/99"
    )
    assert ok_valid is True
    assert "✅" in msg_valid


def test_full_meeting_audit_and_metrics() -> None:
    """驗證整份會議萃取治理與 KPI 統計計算."""
    schema = MeetingExtractionSchema(
        title="測試治理會議",
        meeting_date="2026-11-10",
        departments=["產品部"],
        attendees=["陳總監"],
        executive_summary="測試摘要",
        key_decisions=["決議 A"],
        action_items=[
            ActionItem(
                id="ACT-01",
                task_title="已完成任務",
                due_date="2026-11-01",
                status="Done",
                raci=RACIModel(accountable="陳總監", responsible=["陳總監"]),
                smart=SMARTGoalModel(
                    hierarchy_level="專案成果 (Project Outcome)",
                    specific="完成規格",
                    measurable="100%",
                    time_bound="2026-11-01",
                ),
                qcdt=QCDTModel(
                    quality_criteria="簽核通過",
                    delivery_milestone="2026-11-01",
                    truthfulness_req="簽核單號",
                    evidence_submitted="簽核單 #20261101 已歸檔",
                    evidence_verified=True,
                ),
            )
        ],
    )
    audited = audit_meeting_extraction(schema)
    assert len(audited.action_items[0].governance_gaps) == 0
