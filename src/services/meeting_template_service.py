"""會議記錄「標準輸入格式公版」產生器與精準解析服務 (`src/services/meeting_template_service.py`).

目的：
讓使用者可從「🎙️ 1. 新增會議 & AI 結構化萃取」下載制式公版 (`.xlsx` / `.csv` / `.txt` / `.md`)，
於制式欄位填入：
- 會議日期、來源會議、任務編號、待辦事項名稱、執行狀態、主責/跨部門、
  A (最終當責者)、R (實際執行者)、C (應徵詢者)、I (應被告知者)、
  SMART 層級、截止日 (D)、Q (品質驗收條件)、C (成本預算)、T (證據要求)、T (已提交佐證)、備註/記錄
上傳後點擊「執行 AI 結構化萃取」，即可 100% 精準解析並無縫傳遞至：
- 📚 2. 歷史會議檢索 & 任務佐證更新
- 📊 3. 全域行動方案追蹤看板 (Global Action Tracker)
- 🔔 4. 跨部門主動催辦與通知中心
"""

from __future__ import annotations

import datetime
import io
import re
from typing import Any

import pandas as pd

from src.schemas.models import (
    ActionItem,
    MeetingExtractionSchema,
    QCDTModel,
    RACIModel,
    SMARTGoalModel,
)
from src.services.governance import audit_meeting_extraction

STANDARD_COLUMNS = [
    "會議日期",
    "來源會議",
    "任務編號",
    "待辦事項名稱",
    "執行狀態",
    "主責/跨部門",
    "A (最終當責者)",
    "R (實際執行者)",
    "C (應徵詢者)",
    "I (應被告知者)",
    "SMART 層級",
    "截止日 (D)",
    "Q (品質驗收條件)",
    "C (成本預算)",
    "T (證據要求)",
    "T (已提交佐證)",
    "備註/記錄",
]

VALID_STATUSES = {"Pending", "In Progress", "Blocked", "Done"}
STATUS_ALIAS_MAP = {
    "pending": "Pending",
    "待處理": "Pending",
    "未開始": "Pending",
    "in progress": "In Progress",
    "進行中": "In Progress",
    "處理中": "In Progress",
    "blocked": "Blocked",
    "受阻": "Blocked",
    "卡關": "Blocked",
    "執行受阻": "Blocked",
    "done": "Done",
    "已完成": "Done",
    "完成": "Done",
}

SMART_LEVEL_ALIAS_MAP = {
    "企業目標": "企業目標 (Enterprise Goal)",
    "enterprise goal": "企業目標 (Enterprise Goal)",
    "專案成果": "專案成果 (Project Outcome)",
    "project outcome": "專案成果 (Project Outcome)",
    "工作任務": "工作任務 (Work Task)",
    "work task": "工作任務 (Work Task)",
    "個別活動": "個別活動 (Individual Activity)",
    "individual activity": "個別活動 (Individual Activity)",
}


def _sample_template_rows() -> list[dict[str, str]]:
    """產生公版預設範例資料列."""
    today = datetime.date.today()
    d_today = today.isoformat()
    d_plus_5 = (today + datetime.timedelta(days=5)).isoformat()
    d_plus_10 = (today + datetime.timedelta(days=10)).isoformat()

    return [
        {
            "會議日期": d_today,
            "來源會議": "2026 跨部門產品開發與品質治理週會",
            "任務編號": "ACT-01",
            "待辦事項名稱": "完成 AI 會議記錄公版匯入模組與四色燈號預警測試",
            "執行狀態": "In Progress",
            "主責/跨部門": "AI 研發部 / 產品部",
            "A (最終當責者)": "林雅婷 (AI 架構師)",
            "R (實際執行者)": "林雅婷 (AI 架構師), 周哲宇 (後端工程師)",
            "C (應徵詢者)": "陳建宏 (產品總監)",
            "I (應被告知者)": "吳佩珊 (PMO 經理)",
            "SMART 層級": "專案成果 (Project Outcome)",
            "截止日 (D)": d_plus_5,
            "Q (品質驗收條件)": "支援 xlsx/csv/txt/md 四種公版且 pytest 100% 通過",
            "C (成本預算)": "0 元 (內部資源/工時)",
            "T (證據要求)": "提交 PR 連結與自動化測試通過截圖",
            "T (已提交佐證)": "",
            "備註/記錄": "決議一：全面採用標準輸入格式公版以確保跨部門追蹤看板與催辦中心資料 100% 對齊。",
        },
        {
            "會議日期": d_today,
            "來源會議": "2026 跨部門產品開發與品質治理週會",
            "任務編號": "ACT-02",
            "待辦事項名稱": "更新各部門種子用戶操作培訓手冊並完成演練",
            "執行狀態": "Pending",
            "主責/跨部門": "客服營運部 / 營運管理部",
            "A (最終當責者)": "王志明 (客服經理)",
            "R (實際執行者)": "王志明 (客服經理), 客服教育訓練組",
            "C (應徵詢者)": "產品部",
            "I (應被告知者)": "全體部門主管",
            "SMART 層級": "工作任務 (Work Task)",
            "截止日 (D)": d_plus_10,
            "Q (品質驗收條件)": "完成 5 個部門種子教官實機演練且滿意度達 90% 以上",
            "C (成本預算)": "0 元 (內部工時)",
            "T (證據要求)": "提供培訓簽到表與演練合格紀錄連結",
            "T (已提交佐證)": "",
            "備註/記錄": "決議二：所有結案任務必須於系統填具 T 成果佐證始得轉為綠燈 Done。",
        },
    ]


def generate_meeting_template_csv() -> bytes:
    """產出標準會議輸入格式公版 CSV (`.csv`)."""
    df = pd.DataFrame(_sample_template_rows(), columns=STANDARD_COLUMNS)
    return df.to_csv(index=False).encode("utf-8-sig")


def generate_meeting_template_xlsx() -> bytes:
    """產出標準會議輸入格式公版 Excel (`.xlsx`)."""
    df = pd.DataFrame(_sample_template_rows(), columns=STANDARD_COLUMNS)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="會議輸入格式公版")
    return buf.getvalue()


def generate_meeting_template_md() -> bytes:
    """產出標準會議輸入格式公版 Markdown (`.md`)."""
    rows = _sample_template_rows()
    meeting_date = rows[0]["會議日期"]
    meeting_title = rows[0]["來源會議"]

    md_lines = [
        "# 📋 AI 會議記錄管理 — 標準輸入格式公版 (Markdown)",
        "",
        "## 1. 會議基本資訊",
        f"- **會議日期**：{meeting_date}",
        f"- **來源會議**：{meeting_title}",
        "- **參與部門**：AI 研發部, 產品部, 客服營運部, 營運管理部",
        "- **出席人員**：陳建宏 (產品總監), 林雅婷 (AI 架構師), 王志明 (客服經理), 吳佩珊 (PMO 經理)",
        "- **高階執行摘要**：本次會議確立跨部門『輸入格式公版』標準，確保待辦事項能精準傳遞至歷史會議管理、全域追蹤看板與主動催辦中心。",
        "",
        "## 2. 關鍵決策清單",
        "1. 決議一：全面採用標準輸入格式公版 (xlsx/csv/txt/md) 以提升 AI 結構化萃取精準度。",
        "2. 決議二：所有任務結案時必須填寫 T (成果佐證) 方可轉為綠燈已完成 (Done)。",
        "",
        "## 3. 待辦事項公版表格 (RACI + SMART + QCD+T)",
        "",
        "| " + " | ".join(STANDARD_COLUMNS) + " |",
        "| " + " | ".join([":---"] * len(STANDARD_COLUMNS)) + " |",
    ]
    for r in rows:
        cells = [str(r.get(col, "")).replace("|", "｜") for col in STANDARD_COLUMNS]
        md_lines.append("| " + " | ".join(cells) + " |")

    return ("\n".join(md_lines) + "\n").encode("utf-8")


def generate_meeting_template_txt() -> bytes:
    """產出標準會議輸入格式公版純文字檔 (`.txt`)."""
    rows = _sample_template_rows()
    txt_lines = [
        "====================================================================",
        "【AI 會議記錄管理 — 標準輸入格式公版 (TXT)】",
        "====================================================================",
        f"會議日期：{rows[0]['會議日期']}",
        f"來源會議：{rows[0]['來源會議']}",
        "參與部門：AI 研發部, 產品部, 客服營運部, 營運管理部",
        "出席人員：陳建宏 (產品總監), 林雅婷 (AI 架構師), 王志明 (客服經理), 吳佩珊 (PMO 經理)",
        "高階執行摘要：本次會議確立跨部門輸入格式公版標準，確保待辦事項精準傳遞至追蹤看板與主動催辦中心。",
        "關鍵決策：",
        "- 決議一：全面採用標準輸入格式公版 (xlsx/csv/txt/md) 提升萃取精準度。",
        "- 決議二：所有任務結案時必須填寫 T (成果佐證) 方可轉為綠燈已完成 (Done)。",
        "",
    ]
    for idx, r in enumerate(rows, start=1):
        txt_lines.extend(
            [
                f"--- [待辦事項 {idx}] ---",
                f"任務編號：{r['任務編號']}",
                f"待辦事項名稱：{r['待辦事項名稱']}",
                f"執行狀態：{r['執行狀態']}",
                f"主責/跨部門：{r['主責/跨部門']}",
                f"A (最終當責者)：{r['A (最終當責者)']}",
                f"R (實際執行者)：{r['R (實際執行者)']}",
                f"C (應徵詢者)：{r['C (應徵詢者)']}",
                f"I (應被告知者)：{r['I (應被告知者)']}",
                f"SMART 層級：{r['SMART 層級']}",
                f"截止日 (D)：{r['截止日 (D)']}",
                f"Q (品質驗收條件)：{r['Q (品質驗收條件)']}",
                f"C (成本預算)：{r['C (成本預算)']}",
                f"T (證據要求)：{r['T (證據要求)']}",
                f"T (已提交佐證)：{r['T (已提交佐證)']}",
                f"備註/記錄：{r['備註/記錄']}",
                "",
            ]
        )
    return "\n".join(txt_lines).encode("utf-8")


def _clean_cell(val: Any) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val).strip()
    return "" if s.lower() in {"nan", "none", "null"} else s


def _normalize_status(raw_status: str) -> str:
    cleaned = (raw_status or "").strip()
    if cleaned in VALID_STATUSES:
        return cleaned
    lower = cleaned.lower()
    for k, v in STATUS_ALIAS_MAP.items():
        if k in lower:
            return v
    return "Pending"


def _normalize_smart_level(raw_lvl: str) -> str:
    cleaned = (raw_lvl or "").strip()
    valid_set = {
        "企業目標 (Enterprise Goal)",
        "專案成果 (Project Outcome)",
        "工作任務 (Work Task)",
        "個別活動 (Individual Activity)",
    }
    if cleaned in valid_set:
        return cleaned
    lower = cleaned.lower()
    for k, v in SMART_LEVEL_ALIAS_MAP.items():
        if k in lower:
            return v
    return "工作任務 (Work Task)"


def _split_list_str(raw: str) -> list[str]:
    if not raw:
        return []
    return [x.strip() for x in re.split(r"[,，、；;]", raw) if x.strip()]


def parse_dataframe_to_meeting_schema(
    df: pd.DataFrame,
    meta_overrides: dict[str, Any] | None = None,
) -> MeetingExtractionSchema | None:
    """將包含公版欄位之 DataFrame 直接轉為精準之 `MeetingExtractionSchema`."""
    if df.empty:
        return None

    col_lookup: dict[str, Any] = {}
    for c in df.columns:
        c_str = str(c).strip()
        col_lookup[c_str] = c
        col_lookup[c_str.lower()] = c

    def _get_val(row: pd.Series, candidates: list[str], default: str = "") -> str:
        for cand in candidates:
            if cand in col_lookup:
                v = _clean_cell(row[col_lookup[cand]])
                if v:
                    return v
            if cand.lower() in col_lookup:
                v = _clean_cell(row[col_lookup[cand.lower()]])
                if v:
                    return v
        return default

    # 確認是否至少具備「待辦事項名稱」或「任務名稱」欄位
    has_task_col = any(
        k in col_lookup
        for k in ["待辦事項名稱", "任務名稱", "行動方案", "待辦事項", "task_title", "task"]
    )
    if not has_task_col:
        return None

    meta = meta_overrides or {}
    meeting_title = str(meta.get("title", "")).strip()
    meeting_date = str(meta.get("meeting_date", "")).strip()
    depts_all: list[str] = list(meta.get("departments", []))
    attendees_all: list[str] = list(meta.get("attendees", []))
    decisions_all: list[str] = list(meta.get("key_decisions", []))
    notes_all: list[str] = []
    action_items: list[ActionItem] = []

    for idx, (_, row) in enumerate(df.iterrows(), start=1):
        task_title = _get_val(row, ["待辦事項名稱", "任務名稱", "行動方案", "待辦事項", "task_title", "task"])
        if not task_title:
            continue

        row_date = _get_val(row, ["會議日期", "日期", "meeting_date"])
        if row_date and not meeting_date:
            meeting_date = row_date[:10]

        row_source = _get_val(row, ["來源會議", "會議名稱", "會議標題", "title"])
        if row_source and not meeting_title:
            meeting_title = row_source

        act_id = _get_val(row, ["任務編號", "編號", "id"], default=f"ACT-{idx:02d}")
        status_str = _normalize_status(_get_val(row, ["執行狀態", "狀態", "status"], default="Pending"))
        dept_str = _get_val(row, ["主責/跨部門", "部門", "主責部門", "部門名稱", "department"], default="跨部門")
        acc_str = _get_val(row, ["A (最終當責者)", "最終當責者", "當責者", "A", "accountable", "負責人", "owner"], default="待指定 (未明確歸屬)")
        resp_str = _get_val(row, ["R (實際執行者)", "實際執行者", "執行者", "R", "responsible"])
        cons_str = _get_val(row, ["C (應徵詢者)", "應徵詢者", "徵詢者", "C", "consulted"])
        inf_str = _get_val(row, ["I (應被告知者)", "應被告知者", "告知者", "I", "informed"])
        smart_lvl = _normalize_smart_level(_get_val(row, ["SMART 層級", "目標層級", "層級", "hierarchy_level"]))
        due_str = _get_val(row, ["截止日 (D)", "截止日", "截止日期", "期限", "due_date", "D"], default="待定")
        q_str = _get_val(row, ["Q (品質驗收條件)", "品質驗收條件", "驗收條件", "Q", "quality_criteria"])
        c_str = _get_val(row, ["C (成本預算)", "成本預算", "預算", "成本", "C", "cost_budget"], default="0 元 (內部資源/工時)")
        t_req_str = _get_val(row, ["T (證據要求)", "證據要求", "可驗證證據要求", "T", "truthfulness_req"])
        t_sub_str = _get_val(row, ["T (已提交佐證)", "已提交佐證", "成果佐證", "evidence_submitted"])
        note_str = _get_val(row, ["備註/記錄", "備註", "會議記錄", "記錄", "notes"])

        for d_token in re.split(r"[/,，、；;]", dept_str):
            d_clean = d_token.strip()
            if d_clean and d_clean not in depts_all:
                depts_all.append(d_clean)

        if acc_str and "待指定" not in acc_str and acc_str not in attendees_all:
            attendees_all.append(acc_str)
        resp_list = _split_list_str(resp_str) or ([acc_str] if "待指定" not in acc_str else [])
        for r_p in resp_list:
            if r_p not in attendees_all:
                attendees_all.append(r_p)

        if note_str:
            notes_all.append(note_str)
            if any(k in note_str for k in ["決議", "決策", "拍板", "原則"]) and note_str not in decisions_all:
                decisions_all.append(note_str)

        action_items.append(
            ActionItem(
                id=act_id,
                task_title=task_title,
                department=dept_str,
                owner=acc_str,
                due_date=due_str,
                status=status_str,  # type: ignore[arg-type]
                raci=RACIModel(
                    accountable=acc_str,
                    responsible=resp_list,
                    consulted=_split_list_str(cons_str),
                    informed=_split_list_str(inf_str),
                ),
                smart=SMARTGoalModel(
                    hierarchy_level=smart_lvl,  # type: ignore[arg-type]
                    specific=note_str or task_title,
                    measurable=q_str,
                    achievable="依標準輸入公版排程與資源配置執行",
                    relevant=f"隸屬會議「{meeting_title or '跨部門管理會議'}」之行動方案",
                    time_bound="" if due_str == "待定" else due_str,
                    is_smart_compliant=bool(q_str and due_str != "待定"),
                ),
                qcdt=QCDTModel(
                    quality_criteria=q_str,
                    cost_budget=c_str,
                    delivery_milestone="" if due_str == "待定" else f"{due_str} 交付驗收",
                    truthfulness_req=t_req_str,
                    evidence_submitted=t_sub_str,
                    evidence_verified=bool(status_str == "Done" and t_sub_str),
                ),
            )
        )

    if not action_items:
        return None

    if not meeting_title:
        meeting_title = "標準公版匯入之跨部門管理會議"
    if not meeting_date:
        meeting_date = datetime.date.today().isoformat()
    if not decisions_all:
        decisions_all = [
            f"依循標準輸入格式公版確立 {len(action_items)} 項跨部門待辦事項與 RACI 單一當責歸屬。",
            "所有行動方案同步納管至全域行動方案追蹤看板與主動催辦中心。",
        ]

    summary = str(meta.get("executive_summary", "")).strip()
    if not summary:
        notes_joined = " ".join(notes_all[:3])
        summary = (
            f"本場會議「{meeting_title}」（日期：{meeting_date}）透過標準輸入格式公版匯入，"
            f"涵蓋 {', '.join(depts_all) or '跨部門'}，共計確立 {len(action_items)} 項結構化行動方案。"
            + (f" 重點備註：{notes_joined}" if notes_joined else "")
        )

    schema = MeetingExtractionSchema(
        title=meeting_title,
        meeting_date=meeting_date,
        departments=depts_all or ["跨部門"],
        attendees=attendees_all or ["跨部門與會代表"],
        executive_summary=summary,
        key_decisions=decisions_all,
        action_items=action_items,
    )
    audited = audit_meeting_extraction(schema)
    assert isinstance(audited, MeetingExtractionSchema)
    return audited


def try_parse_structured_template_text(text: str) -> MeetingExtractionSchema | None:
    """嘗試將貼上或上傳之 `.md` / `.txt` 文本依『標準輸入格式公版』解析為 `MeetingExtractionSchema`."""
    cleaned = (text or "").strip()
    if not cleaned:
        return None

    lines = [ln.strip() for ln in cleaned.splitlines() if ln.strip()]

    # 提取頂部會議基本資訊 (適用於 Markdown 與 TXT 公版)
    meta: dict[str, Any] = {
        "title": "",
        "meeting_date": "",
        "departments": [],
        "attendees": [],
        "executive_summary": "",
        "key_decisions": [],
    }

    for ln in lines:
        plain_ln = re.sub(r"^[\-\*\+#\d\.\s]+|\*\*", "", ln).strip()
        if plain_ln.startswith(("會議日期：", "會議日期:")):
            meta["meeting_date"] = re.split(r"[：:]", plain_ln, maxsplit=1)[1].strip()[:10]
        elif plain_ln.startswith(("來源會議：", "來源會議:", "會議名稱：", "會議標題：")):
            meta["title"] = re.split(r"[：:]", plain_ln, maxsplit=1)[1].strip()
        elif plain_ln.startswith(("參與部門：", "參與部門:")):
            meta["departments"] = _split_list_str(re.split(r"[：:]", plain_ln, maxsplit=1)[1])
        elif plain_ln.startswith(("出席人員：", "出席人員:")):
            meta["attendees"] = _split_list_str(re.split(r"[：:]", plain_ln, maxsplit=1)[1])
        elif plain_ln.startswith(("高階執行摘要：", "高階執行摘要:")):
            meta["executive_summary"] = re.split(r"[：:]", plain_ln, maxsplit=1)[1].strip()
        elif any( plain_ln.startswith(p) for p in ("決議一", "決議二", "決議三", "決議：") ):
            meta["key_decisions"].append(plain_ln)

    # Case 1: 檢查是否包含 Markdown 公版表格
    table_lines = [ln for ln in lines if ln.startswith("|") and ln.endswith("|")]
    if len(table_lines) >= 2:
        headers = [c.strip() for c in table_lines[0].strip("|").split("|")]
        rows_data = []
        for tl in table_lines[1:]:
            if re.match(r"^\|[\s\-:|]+\|$", tl):
                continue
            cells = [c.strip() for c in tl.strip("|").split("|")]
            if len(cells) < len(headers):
                cells.extend([""] * (len(headers) - len(cells)))
            rows_data.append(cells[: len(headers)])
        if rows_data:
            df = pd.DataFrame(rows_data, columns=headers)
            parsed = parse_dataframe_to_meeting_schema(df, meta_overrides=meta)
            if parsed is not None:
                return parsed

    # Case 2: 檢查是否為 TXT 公版區段 (包含 `--- [待辦事項` 或多組 `待辦事項名稱：`)
    if "待辦事項名稱：" in cleaned or "待辦事項名稱:" in cleaned:
        blocks = re.split(r"---\s*\[待辦事項[^\]]*\]\s*---", cleaned)
        task_blocks = blocks[1:] if len(blocks) > 1 else [cleaned]
        kv_rows: list[dict[str, str]] = []
        for blk in task_blocks:
            row_dict: dict[str, str] = {}
            for blk_ln in blk.splitlines():
                blk_ln = blk_ln.strip()
                if "：" in blk_ln or ":" in blk_ln:
                    k, v = re.split(r"[：:]", blk_ln, maxsplit=1)
                    row_dict[k.strip()] = v.strip()
            if "待辦事項名稱" in row_dict:
                kv_rows.append(row_dict)
        if kv_rows:
            df = pd.DataFrame(kv_rows)
            parsed = parse_dataframe_to_meeting_schema(df, meta_overrides=meta)
            if parsed is not None:
                return parsed

    return None


def schema_to_readable_transcript(schema: MeetingExtractionSchema) -> str:
    """將從 Excel/CSV 公版解析出之 `MeetingExtractionSchema` 轉為可讀性高之結構化逐字稿預覽文本."""
    lines = [
        f"會議日期：{schema.meeting_date}",
        f"來源會議：{schema.title}",
        f"參與部門：{', '.join(schema.departments)}",
        f"出席人員：{', '.join(schema.attendees)}",
        f"高階執行摘要：{schema.executive_summary}",
        "",
    ]
    for idx, act in enumerate(schema.action_items, start=1):
        lines.extend(
            [
                f"--- [待辦事項 {idx}] ---",
                f"任務編號：{act.id}",
                f"待辦事項名稱：{act.task_title}",
                f"執行狀態：{act.status}",
                f"主責/跨部門：{act.department}",
                f"A (最終當責者)：{act.raci.accountable}",
                f"R (實際執行者)：{', '.join(act.raci.responsible)}",
                f"C (應徵詢者)：{', '.join(act.raci.consulted)}",
                f"I (應被告知者)：{', '.join(act.raci.informed)}",
                f"SMART 層級：{act.smart.hierarchy_level}",
                f"截止日 (D)：{act.due_date}",
                f"Q (品質驗收條件)：{act.qcdt.quality_criteria}",
                f"C (成本預算)：{act.qcdt.cost_budget}",
                f"T (證據要求)：{act.qcdt.truthfulness_req}",
                f"T (已提交佐證)：{act.qcdt.evidence_submitted}",
                f"備註/記錄：{act.smart.specific}",
                "",
            ]
        )
    return "\n".join(lines)


def parse_uploaded_meeting_file(
    file_bytes: bytes,
    filename: str,
) -> tuple[str, MeetingExtractionSchema | None, str]:
    """解析於『🎙️ 1. 新增會議 & AI 結構化萃取』上傳之 `.xlsx` / `.csv` / `.txt` / `.md` 檔案.

    回傳:
        (transcript_text, pre_parsed_schema_or_none, status_message)
    """
    fname = (filename or "").lower().strip()
    try:
        if fname.endswith(".xlsx"):
            df = pd.read_excel(io.BytesIO(file_bytes))
            schema = parse_dataframe_to_meeting_schema(df)
            if schema is not None:
                text = schema_to_readable_transcript(schema)
                return (
                    text,
                    schema,
                    f"🎯 已成功讀取 Excel 輸入格式公版 `{filename}`（共精準識別 {len(schema.action_items)} 項待辦任務）！請點擊下方「🚀 執行 AI 結構化萃取」進行治理查核與預覽。",
                )
            # 若為非標準欄位之一般 Excel 表格，轉為 Markdown 文本供 AI 萃取
            text = df.to_markdown(index=False) if hasattr(df, "to_markdown") else df.to_csv(index=False)
            return text, None, f"✅ 已讀取 Excel 檔案 `{filename}`，請點擊下方按鈕執行 AI 萃取。"

        if fname.endswith(".csv"):
            try:
                raw_csv = file_bytes.decode("utf-8-sig")
            except UnicodeDecodeError:
                raw_csv = file_bytes.decode("big5", errors="replace")
            df = pd.read_csv(io.StringIO(raw_csv))
            schema = parse_dataframe_to_meeting_schema(df)
            if schema is not None:
                text = schema_to_readable_transcript(schema)
                return (
                    text,
                    schema,
                    f"🎯 已成功讀取 CSV 輸入格式公版 `{filename}`（共精準識別 {len(schema.action_items)} 項待辦任務）！請點擊下方「🚀 執行 AI 結構化萃取」進行治理查核與預覽。",
                )
            return raw_csv, None, f"✅ 已讀取 CSV 檔案 `{filename}`，請點擊下方按鈕執行 AI 萃取。"

        # .txt or .md
        decoded = file_bytes.decode("utf-8-sig", errors="replace")
        schema = try_parse_structured_template_text(decoded)
        if schema is not None:
            return (
                decoded,
                schema,
                f"🎯 已成功讀取 `{filename}` 標準輸入格式公版（共精準識別 {len(schema.action_items)} 項待辦任務）！請點擊下方「🚀 執行 AI 結構化萃取」進行治理查核與預覽。",
            )
        return decoded, None, f"✅ 已讀取檔案 `{filename}`（共 {len(decoded)} 字元）。"
    except Exception as exc:
        return "", None, f"❌ 讀取檔案 `{filename}` 發生錯誤：{exc}"
