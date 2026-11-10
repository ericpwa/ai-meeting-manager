"""單元測試：驗證組織部門與與會人員名冊批量匯入 (.xlsx / .csv / .md) 以及全域追蹤看板四色燈號預警邏輯."""

from __future__ import annotations

import datetime
from pathlib import Path

from src.repositories.meeting_repo import MeetingRepository
from src.schemas.models import ActionItem, QCDTModel, RACIModel, SMARTGoalModel
from src.services.governance import classify_action_traffic_light
from src.services.org_directory_service import (
    generate_sample_roster_csv,
    generate_sample_roster_md,
    generate_sample_roster_xlsx,
    parse_organization_upload,
)


def test_parse_organization_upload_xlsx_csv_md(tmp_path: Path) -> None:
    """驗證 .xlsx, .csv, .md 三種格式之部門名稱與與會人員批量解析及資料庫持久化."""
    # 1. 測試 Excel (.xlsx)
    xlsx_bytes = generate_sample_roster_xlsx()
    depts_x, persons_x, msg_x = parse_organization_upload(xlsx_bytes, "company_roster.xlsx")
    assert "產品部" in depts_x
    assert "陳建宏 (產品總監)" in persons_x
    assert "✅" in msg_x

    # 2. 測試 CSV (.csv)
    csv_bytes = generate_sample_roster_csv()
    depts_c, persons_c, msg_c = parse_organization_upload(csv_bytes, "company_roster.csv")
    assert "AI 研發部" in depts_c
    assert "林雅婷 (AI 架構師)" in persons_c
    assert "✅" in msg_c

    # 3. 測試 Markdown (.md)
    md_bytes = generate_sample_roster_md()
    depts_m, persons_m, msg_m = parse_organization_upload(md_bytes, "company_roster.md")
    assert "資安法遵部" in depts_m
    assert "張志豪 (資安官)" in persons_m
    assert "✅" in msg_m

    # 4. 測試寫入 MeetingRepository 並檢索
    repo = MeetingRepository(db_path=tmp_path / "roster_test.db", force_local=True)
    repo.save_org_directory(["創新實驗室", "法務合規處"], ["孫小美 (法務長)", "周杰倫 (創新總監)"], merge=True)
    saved_depts, saved_persons = repo.get_org_directory(include_from_meetings=False)
    assert "創新實驗室" in saved_depts
    assert "法務合規處" in saved_depts
    assert "孫小美 (法務長)" in saved_persons
    assert "周杰倫 (創新總監)" in saved_persons

    # 確認特殊系統名冊紀錄不會混入一般會議列表
    assert len(repo.list_meetings()) == 0


def test_classify_action_traffic_light_all_six_states() -> None:
    """驗證紅/黃/藍/綠四色燈號與 6 種『🩺 治理與逾期狀態』精準對應."""
    ref_today = datetime.date(2026, 11, 10)

    def _make_clean_item(status: str, due_date: str, gaps: list[str] | None = None) -> ActionItem:
        return ActionItem(
            id="ACT-L1",
            task_title="燈號測試任務",
            department="測試部",
            owner="王測試",
            due_date=due_date,
            status=status,  # type: ignore[arg-type]
            raci=RACIModel(accountable="王測試", responsible=["王測試"]),
            smart=SMARTGoalModel(
                hierarchy_level="工作任務 (Work Task)",
                specific="具體",
                measurable="可衡量",
                time_bound=due_date,
            ),
            qcdt=QCDTModel(
                quality_criteria="Q",
                delivery_milestone=due_date,
                truthfulness_req="T",
                evidence_submitted="已提交證據" if status == "Done" else "",
            ),
            governance_gaps=gaps or [],
        )

    # 1. 🚨 逾期未完成 -> 🔴 紅燈
    l1, s1, _ = classify_action_traffic_light(_make_clean_item("In Progress", "2026-11-08"), ref_today)
    assert l1 == "🔴 紅燈"
    assert s1 == "🚨 逾期未完成"

    # 2. 🛑 執行受阻 (Blocked) -> 🔴 紅燈
    l2, s2, _ = classify_action_traffic_light(_make_clean_item("Blocked", "2026-11-20"), ref_today)
    assert l2 == "🔴 紅燈"
    assert s2 == "🛑 執行受阻 (Blocked)"

    # 3. ⚠️ 治理缺口 -> 🟡 黃燈
    l3, s3, _ = classify_action_traffic_light(
        _make_clean_item("Pending", "2026-11-25", gaps=["【RACI 缺口】缺少最終當責者 (A)"]),
        ref_today,
    )
    assert l3 == "🟡 黃燈"
    assert s3 == "⚠️ 治理缺口"

    # 4. ⏳ 即將到期 (3日內) -> 🟡 黃燈
    l4, s4, _ = classify_action_traffic_light(_make_clean_item("In Progress", "2026-11-12"), ref_today)
    assert l4 == "🟡 黃燈"
    assert s4 == "⏳ 即將到期"

    # 5. ⏳ 未完成/進行中 -> 🔵 藍燈
    l5, s5, _ = classify_action_traffic_light(_make_clean_item("In Progress", "2026-11-25"), ref_today)
    assert l5 == "🔵 藍燈"
    assert s5 == "⏳ 未完成/進行中"

    # 6. ✅ 已完成 (Done) -> 🟢 綠燈
    l6, s6, _ = classify_action_traffic_light(_make_clean_item("Done", "2026-11-09"), ref_today)
    assert l6 == "🟢 綠燈"
    assert s6 == "✅ 已完成 (Done)"


def test_meeting_input_templates_all_four_formats() -> None:
    """驗證『會議輸入格式公版』(xlsx/csv/md/txt) 之產生、上傳解析與 AI 結構化萃取 100% 精準對映."""
    from src.services.ai_service import extract_meeting_from_transcript
    from src.services.meeting_template_service import (
        generate_meeting_template_csv,
        generate_meeting_template_md,
        generate_meeting_template_txt,
        generate_meeting_template_xlsx,
        parse_uploaded_meeting_file,
    )

    # 1. Excel (.xlsx) 公版產生與解析
    xlsx_bytes = generate_meeting_template_xlsx()
    txt_x, schema_x, msg_x = parse_uploaded_meeting_file(xlsx_bytes, "meeting_input_template.xlsx")
    assert schema_x is not None
    assert len(schema_x.action_items) == 2
    assert schema_x.action_items[0].id == "ACT-01"
    assert schema_x.action_items[0].raci.accountable == "林雅婷 (AI 架構師)"
    assert "🎯" in msg_x

    # 2. CSV (.csv) 公版產生與解析
    csv_bytes = generate_meeting_template_csv()
    txt_c, schema_c, _ = parse_uploaded_meeting_file(csv_bytes, "meeting_input_template.csv")
    assert schema_c is not None
    assert len(schema_c.action_items) == 2
    assert schema_c.action_items[1].id == "ACT-02"

    # 3. Markdown (.md) 公版產生與解析
    md_bytes = generate_meeting_template_md()
    txt_m, schema_m, _ = parse_uploaded_meeting_file(md_bytes, "meeting_input_template.md")
    assert schema_m is not None
    assert len(schema_m.action_items) == 2

    # 4. TXT (.txt) 公版產生並送入 extract_meeting_from_transcript
    txt_bytes = generate_meeting_template_txt()
    extracted, _, ext_msg = extract_meeting_from_transcript(txt_bytes.decode("utf-8"), api_key="")
    assert len(extracted.action_items) == 2
    assert extracted.action_items[0].task_title == "完成 AI 會議記錄公版匯入模組與四色燈號預警測試"
    assert "標準輸入格式公版" in ext_msg
