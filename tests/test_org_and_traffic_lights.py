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


def test_flexible_date_formats_overdue_red_light_and_metrics() -> None:
    """回歸測試：驗證 Excel 斜線/時間戳、民國年與各式逾期日期皆正確判定為 🔴 紅燈 (🚨 逾期未完成)."""
    import pandas as pd

    from src.schemas.models import MeetingRecord
    from src.services.governance import (
        compute_governance_metrics,
        normalize_date_str,
        parse_flexible_date,
    )
    from src.services.meeting_template_service import parse_dataframe_to_meeting_schema
    from src.services.notification_service import scan_followup_targets

    ref_today = datetime.date(2026, 11, 25)

    def _make_item(due: str, status: str = "In Progress") -> ActionItem:
        return ActionItem(
            id="ACT-DATE",
            task_title=f"日期測試 ({due})",
            department="綠能部",
            owner="王經理",
            due_date=due,
            status=status,  # type: ignore[arg-type]
            raci=RACIModel(accountable="王經理", responsible=["王經理"]),
            smart=SMARTGoalModel(
                hierarchy_level="工作任務 (Work Task)",
                specific="完成任務",
                measurable="100%",
                time_bound=due,
            ),
            qcdt=QCDTModel(
                quality_criteria="驗收通過",
                delivery_milestone=due,
                truthfulness_req="提出報告",
                evidence_submitted="已完成佐證" if status == "Done" else "",
            ),
            governance_gaps=[],
        )

    # 1. 各式逾期日期（含螢幕截圖實際出現之 Excel 斜線/時間戳與台灣民國年格式）皆必須亮 🔴 紅燈
    overdue_samples = [
        "2026/11/15 00:00",
        "2026/11/16 00:00",
        "2026-11-23 12:00:00",
        "2026-11-23T12:00:00",
        "2026/11/5",
        "2026.11.15",
        "2026年11月15日",
        "11/15/2026",
        "20261115",
        "0115-11-23",
        "115/11/23",
        "115.11.23",
        "115年11月23日",
        "民國115年11月23日",
        "1151123",
        "２０２６／１１／１５ ００：００",
    ]
    for sample_due in overdue_samples:
        light, status_lbl, _ = classify_action_traffic_light(_make_item(sample_due, "In Progress"), ref_today)
        assert light == "🔴 紅燈", f"逾期日期 {sample_due!r} 應亮紅燈，實際得到 {light}"
        assert status_lbl == "🚨 逾期未完成", f"逾期日期 {sample_due!r} 狀態應為逾期未完成，實際得到 {status_lbl}"

    # 2. 即將到期 (1~3天內含時間戳) -> 🟡 黃燈
    for soon_due in ["2026-11-26 17:30:00", "2026-11-27 17:30:00", "2026/11/25 00:00"]:
        light, status_lbl, _ = classify_action_traffic_light(_make_item(soon_due, "In Progress"), ref_today)
        assert light == "🟡 黃燈", f"即將到期日期 {soon_due!r} 應亮黃燈，實際得到 {light}"
        assert status_lbl == "⏳ 即將到期"

    # 3. 超過 3 天之未來日期 (含時間戳) -> 🔵 藍燈
    for future_due in ["2026/11/30 00:00", "2026-11-30 09:00:00"]:
        light, status_lbl, _ = classify_action_traffic_light(_make_item(future_due, "In Progress"), ref_today)
        assert light == "🔵 藍燈", f"未來日期 {future_due!r} 應亮藍燈，實際得到 {light}"
        assert status_lbl == "⏳ 未完成/進行中"

    # 4. 驗證全域 KPI 統計與主動催辦掃描同步識別非 ISO 逾期日期
    mock_meeting = MeetingRecord(
        id="m-overdue-test",
        title="1151123 主管週會",
        meeting_date="2026-11-23",
        departments=["綠能部"],
        attendees=["王經理"],
        executive_summary="測試逾期日期解析",
        key_decisions=["決議"],
        action_items=[
            _make_item("2026/11/15 00:00", "In Progress"),
            _make_item("2026-11-23 12:00:00", "Pending"),
            _make_item("2026-11-30 09:00:00", "In Progress"),
        ],
    )
    metrics = compute_governance_metrics([mock_meeting], reference_date=ref_today)
    assert metrics["overdue_actions"] == 2

    followups = scan_followup_targets([mock_meeting], reference_date=ref_today)
    overdue_followups = [e for e in followups if e.urgency_category == "🚨 逾期未完成"]
    assert len(overdue_followups) == 2

    # 5. 驗證 Excel/CSV 公版匯入時自動正規化民國年與斜線時間戳
    assert parse_flexible_date("0115-11-23") == datetime.date(2026, 11, 23)
    assert normalize_date_str("0115-11-23") == "2026-11-23"
    assert normalize_date_str("2026/11/15 00:00", keep_nonzero_time=True) == "2026-11-15"
    assert normalize_date_str("2026-11-23 12:00:00", keep_nonzero_time=True) == "2026-11-23 12:00"

    df_excel = pd.DataFrame(
        [
            {
                "會議日期": "0115-11-23",
                "來源會議": "1151123 主管週會",
                "任務編號": "ACT-01",
                "待辦事項名稱": "確認臺旺儲能數據",
                "執行狀態": "Pending",
                "主責/跨部門": "綠能部",
                "A (最終當責者)": "王經理",
                "R (實際執行者)": "王經理",
                "截止日 (D)": "2026-11-23 12:00:00",
                "Q (品質驗收條件)": "提出臺旺儲能數據",
                "T (證據要求)": "提交數據報告",
            }
        ]
    )
    schema = parse_dataframe_to_meeting_schema(df_excel)
    assert schema is not None
    assert schema.meeting_date == "2026-11-23"
    assert schema.action_items[0].due_date == "2026-11-23 12:00"
    l_imp, s_imp, _ = classify_action_traffic_light(schema.action_items[0], ref_today)
    assert l_imp == "🔴 紅燈"
    assert s_imp == "🚨 逾期未完成"


def test_tracker_sorting_and_duplicate_detection() -> None:
    """驗證看板三四大排序模式（風險度紅➔黃➔藍➔綠置頂/置底、完成度分群、日期由新而舊含民國年）與重複任務標記."""
    from src.ui.tracker_view import (
        SORT_MODE_COMPLETION,
        SORT_MODE_DATE_DESC,
        SORT_MODE_DUE_ASC,
        SORT_MODE_RISK_FIRST,
        annotate_duplicate_tasks,
        sort_tracker_rows,
    )

    rows = [
        {
            "燈號預警": "🟢 綠燈",
            "🩺 治理與逾期狀態": "✅ 已完成 (Done)",
            "會議日期": "2026-11-24",
            "來源會議": "週會 C",
            "任務編號": "ACT-G",
            "待辦事項名稱": "已完成任務",
            "執行狀態": "Done",
            "A (最終當責者)": "陳經理",
            "截止日 (D)": "2026-11-24",
            "T (已提交佐證)": "報告連結",
        },
        {
            "燈號預警": "🔵 藍燈",
            "🩺 治理與逾期狀態": "⏳ 未完成/進行中",
            "會議日期": "0115-11-23",  # 民國 115 = 2026-11-23
            "來源會議": "1151123 主管週會",
            "任務編號": "ACT-B",
            "待辦事項名稱": "正常進行任務",
            "執行狀態": "In Progress",
            "A (最終當責者)": "王經理",
            "截止日 (D)": "2026-11-30",
            "T (已提交佐證)": "尚未提交",
        },
        {
            "燈號預警": "🟡 黃燈",
            "🩺 治理與逾期狀態": "⏳ 即將到期",
            "會議日期": "2026-11-20",
            "來源會議": "週會 B",
            "任務編號": "ACT-Y",
            "待辦事項名稱": "即將到期任務",
            "執行狀態": "In Progress",
            "A (最終當責者)": "林經理",
            "截止日 (D)": "2026-11-26",
            "T (已提交佐證)": "尚未提交",
        },
        {
            "燈號預警": "🔴 紅燈",
            "🩺 治理與逾期狀態": "🚨 逾期未完成",
            "會議日期": "2026-11-09",
            "來源會議": "週會 A",
            "任務編號": "ACT-R-OLD",
            "待辦事項名稱": "重複測試任務",
            "執行狀態": "In Progress",
            "A (最終當責者)": "張經理",
            "截止日 (D)": "2026/11/15 00:00",
            "T (已提交佐證)": "尚未提交",
        },
        {
            "燈號預警": "🔴 紅燈",
            "🩺 治理與逾期狀態": "🚨 逾期未完成",
            "會議日期": "0115-11-23",  # 較新紅燈，應排在 2026-11-09 紅燈前面
            "來源會議": "1151123 主管週會",
            "任務編號": "ACT-R-NEW",
            "待辦事項名稱": "重複測試任務",
            "執行狀態": "Pending",
            "A (最終當責者)": "張經理",
            "截止日 (D)": "2026-11-23 12:00:00",
            "T (已提交佐證)": "尚未提交",
        },
    ]

    # 1. 風險度優先：紅(新)->紅(舊)->黃->藍->綠(已完成置底)
    risk_sorted = sort_tracker_rows(rows, SORT_MODE_RISK_FIRST)
    assert [r["任務編號"] for r in risk_sorted] == ["ACT-R-NEW", "ACT-R-OLD", "ACT-Y", "ACT-B", "ACT-G"]

    # 2. 完成度分群：未完成(依日期新到舊) ➔ 已完成(置底)
    comp_sorted = sort_tracker_rows(rows, SORT_MODE_COMPLETION)
    assert comp_sorted[-1]["任務編號"] == "ACT-G"
    assert comp_sorted[0]["會議日期"] == "0115-11-23"

    # 3. 純會議日期排序（由新而舊，民國 0115-11-23 應排在 2026-11-24 之後、2026-11-20 之前）
    date_sorted = sort_tracker_rows(rows, SORT_MODE_DATE_DESC)
    assert date_sorted[0]["任務編號"] == "ACT-G"
    assert date_sorted[-1]["任務編號"] == "ACT-R-OLD"

    # 4. 截止日急迫度優先（最早逾期 2026/11/15 置頂，已完成置底）
    due_sorted = sort_tracker_rows(rows, SORT_MODE_DUE_ASC)
    assert due_sorted[0]["任務編號"] == "ACT-R-OLD"
    assert due_sorted[-1]["任務編號"] == "ACT-G"

    # 5. 重複任務自動偵測：同名同當責者之兩筆均標記疑似重複，且僅較舊者標記為 _is_redundant_dup=True
    annotated = annotate_duplicate_tasks(rows)
    by_id = {r["任務編號"]: r for r in annotated}
    assert by_id["ACT-R-NEW"]["_dup_count"] == 2
    assert by_id["ACT-R-OLD"]["_dup_count"] == 2
    assert by_id["ACT-R-NEW"]["_is_redundant_dup"] is False  # 保留較新 1 筆
    assert by_id["ACT-R-OLD"]["_is_redundant_dup"] is True   # 標記較舊副本可清理
    assert by_id["ACT-B"]["_dup_count"] == 1
