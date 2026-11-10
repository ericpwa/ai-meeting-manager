"""組織部門與與會人員名冊批量匯入解析與範本產生服務 (`src/services/org_directory_service.py`).

支援上傳格式：
1. Excel (`.xlsx`)
2. CSV (`.csv`)
3. Markdown (`.md` — 支援 Markdown 表格與條列清單)

匯入後之「部門名稱」與「與會人員」將自動同步至：
- 👑 當責者 (A) 篩選選單
- 🛠️ 執行者 (R) 篩選選單
- 🏢 部門篩選選單
"""

from __future__ import annotations

import io
import re
import pandas as pd

DEPT_COL_KEYWORDS = {"部門", "部門名稱", "單位", "單位名稱", "department", "dept", "所屬部門", "主責部門"}
PERSON_COL_KEYWORDS = {
    "與會人員",
    "出席人員",
    "人員",
    "姓名",
    "人員姓名",
    "成員",
    "當責者",
    "執行者",
    "負責人",
    "attendee",
    "attendees",
    "name",
    "member",
    "owner",
    "person",
}
ROLE_COL_KEYWORDS = {"職稱", "角色", "職位", "title", "role", "position"}


def _clean_token(val: object) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val).strip()
    if s.lower() in {"nan", "none", "null", ""}:
        return ""
    return s


def _extract_from_dataframe(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    """從 pandas DataFrame 智慧識別『部門名稱』與『與會人員』欄位並擷取唯一清單."""
    if df.empty:
        return [], []

    departments: list[str] = []
    attendees: list[str] = []

    col_map = {str(c).strip().lower(): c for c in df.columns}
    dept_col = None
    person_col = None
    role_col = None

    for lower_name, orig_col in col_map.items():
        if dept_col is None and any(k in lower_name for k in DEPT_COL_KEYWORDS):
            dept_col = orig_col
        elif person_col is None and any(k in lower_name for k in PERSON_COL_KEYWORDS):
            person_col = orig_col
        elif role_col is None and any(k in lower_name for k in ROLE_COL_KEYWORDS):
            role_col = orig_col

    # 若欄位名稱未命中關鍵字，採位置啟發式：第1欄為部門、第2欄為人員
    cols = list(df.columns)
    if dept_col is None and person_col is None:
        if len(cols) >= 2:
            dept_col, person_col = cols[0], cols[1]
            if len(cols) >= 3:
                role_col = cols[2]
        elif len(cols) == 1:
            person_col = cols[0]

    for _, row in df.iterrows():
        d_raw = _clean_token(row[dept_col]) if dept_col is not None else ""
        p_raw = _clean_token(row[person_col]) if person_col is not None else ""
        r_raw = _clean_token(row[role_col]) if role_col is not None else ""

        # 支援單一儲存格以逗號或頓號分隔多筆
        row_depts = [x.strip() for x in re.split(r"[,，、/；;]", d_raw) if x.strip()]
        for d in row_depts:
            if d not in departments:
                departments.append(d)

        row_persons = [x.strip() for x in re.split(r"[,，、；;]", p_raw) if x.strip()]
        for p in row_persons:
            # 若有職稱或部門且人名尚未包含括號，自動組合成易讀格式如 "王大明 (研發部-工程師)" 或保留原樣
            formatted_p = p
            if "(" not in p and "（" not in p:
                if r_raw and d_raw and len(row_depts) == 1:
                    formatted_p = f"{p} ({r_raw})"
                elif r_raw:
                    formatted_p = f"{p} ({r_raw})"
            if formatted_p not in attendees:
                attendees.append(formatted_p)

    return departments, attendees


def _extract_from_markdown(md_text: str) -> tuple[list[str], list[str]]:
    """從 Markdown 文本（支援 Markdown 表格或標題條列清單）解析部門名稱與與會人員."""
    departments: list[str] = []
    attendees: list[str] = []

    lines = [ln.strip() for ln in (md_text or "").splitlines() if ln.strip()]

    # 1. 檢查是否包含 Markdown 表格
    table_lines = [ln for ln in lines if ln.startswith("|") and ln.endswith("|")]
    if len(table_lines) >= 2:
        header_cells = [c.strip() for c in table_lines[0].strip("|").split("|")]
        data_rows = []
        for tl in table_lines[1:]:
            # 略過分隔線 |---|---|
            if re.match(r"^\|[\s\-:|]+\|$", tl):
                continue
            cells = [c.strip() for c in tl.strip("|").split("|")]
            if len(cells) < len(header_cells):
                cells.extend([""] * (len(header_cells) - len(cells)))
            data_rows.append(cells[: len(header_cells)])
        if data_rows:
            df = pd.DataFrame(data_rows, columns=header_cells)
            d_list, p_list = _extract_from_dataframe(df)
            departments.extend(d_list)
            attendees.extend(p_list)

    # 2. 解析標題分區與清單格式 (例如 ## 部門名稱 / - 產品部 或 - 產品部：陳建宏、林雅婷)
    current_section = ""
    for ln in lines:
        if ln.startswith("|"):
            continue
        if ln.startswith("#"):
            heading_text = ln.lstrip("#").strip().lower()
            if any(k in heading_text for k in DEPT_COL_KEYWORDS):
                current_section = "dept"
            elif any(k in heading_text for k in PERSON_COL_KEYWORDS):
                current_section = "person"
            continue

        cleaned_item = re.sub(r"^[\-\*\+\d\.\)\s]+", "", ln).strip()
        if not cleaned_item:
            continue

        # 處理「產品部：王大明、李小華」格式
        if ("：" in cleaned_item or ":" in cleaned_item) and current_section == "":
            left, right = re.split(r"[：:]", cleaned_item, maxsplit=1)
            left = left.strip()
            right = right.strip()
            if left in DEPT_COL_KEYWORDS:
                for d in re.split(r"[,，、；;]", right):
                    if d.strip() and d.strip() not in departments:
                        departments.append(d.strip())
                continue
            if left in PERSON_COL_KEYWORDS:
                for p in re.split(r"[,，、；;]", right):
                    if p.strip() and p.strip() not in attendees:
                        attendees.append(p.strip())
                continue
            # 左側視為部門、右側視為人員清單
            if left and left not in departments:
                departments.append(left)
            for p in re.split(r"[,，、；;]", right):
                if p.strip() and p.strip() not in attendees:
                    attendees.append(p.strip())
            continue

        tokens = [t.strip() for t in re.split(r"[,，、；;]", cleaned_item) if t.strip()]
        for tok in tokens:
            if current_section == "dept" or (current_section == "" and tok.endswith(("部", "處", "室", "中心", "組", "委員會", "團隊"))):
                if tok not in departments:
                    departments.append(tok)
            else:
                if tok not in attendees:
                    attendees.append(tok)

    return departments, attendees


def parse_organization_upload(file_bytes: bytes, filename: str) -> tuple[list[str], list[str], str]:
    """解析上傳之 `.xlsx` / `.csv` / `.md` 檔案，回傳 `(departments, attendees, message)`."""
    fname = (filename or "").lower().strip()
    try:
        if fname.endswith(".xlsx"):
            df = pd.read_excel(io.BytesIO(file_bytes))
            depts, persons = _extract_from_dataframe(df)
        elif fname.endswith(".csv"):
            try:
                text = file_bytes.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = file_bytes.decode("big5", errors="replace")
            df = pd.read_csv(io.StringIO(text))
            depts, persons = _extract_from_dataframe(df)
        elif fname.endswith(".md") or fname.endswith(".txt"):
            text = file_bytes.decode("utf-8-sig", errors="replace")
            depts, persons = _extract_from_markdown(text)
        else:
            return [], [], f"❌ 不支援的檔案格式：`{filename}`（請上傳 `.xlsx`, `.csv` 或 `.md` 檔）。"

        if not depts and not persons:
            return [], [], f"⚠️ 於 `{filename}` 中未解析出有效的部門名稱或與會人員，請確認欄位包含『部門名稱』與『與會人員』。"

        return (
            depts,
            persons,
            f"✅ 成功從 `{filename}` 匯入 **{len(depts)} 個部門** 與 **{len(persons)} 位人員**！已自動同步至所有篩選選單。",
        )
    except Exception as exc:
        return [], [], f"❌ 解析檔案 `{filename}` 時發生錯誤：{exc}"


def generate_sample_roster_csv() -> bytes:
    """產出標準 CSV 組織名冊匯入範本."""
    df = pd.DataFrame(
        [
            {"部門名稱": "經營決策委員會", "與會人員": "王執行長 (CEO)"},
            {"部門名稱": "產品部", "與會人員": "陳建宏 (產品總監)"},
            {"部門名稱": "AI 研發部", "與會人員": "林雅婷 (AI 架構師)"},
            {"部門名稱": "AI 研發部", "與會人員": "周哲宇 (後端工程師)"},
            {"部門名稱": "資安法遵部", "與會人員": "張志豪 (資安官)"},
            {"部門名稱": "營運管理部", "與會人員": "吳佩珊 (PMO 經理)"},
            {"部門名稱": "客服營運部", "與會人員": "王志明 (客服經理)"},
            {"部門名稱": "採購部", "與會人員": "蔡淑芬 (採購主任)"},
            {"部門名稱": "財務部", "與會人員": "鄭家豪 (財務稽核)"},
            {"部門名稱": "資訊部", "與會人員": "趙文成 (IT 經理)"},
            {"部門名稱": "商務開發部", "與會人員": "何雅雯 (BD 總監)"},
        ]
    )
    return df.to_csv(index=False).encode("utf-8-sig")


def generate_sample_roster_xlsx() -> bytes:
    """產出標準 Excel (.xlsx) 組織名冊匯入範本."""
    df = pd.DataFrame(
        [
            {"部門名稱": "經營決策委員會", "與會人員": "王執行長 (CEO)"},
            {"部門名稱": "產品部", "與會人員": "陳建宏 (產品總監)"},
            {"部門名稱": "AI 研發部", "與會人員": "林雅婷 (AI 架構師)"},
            {"部門名稱": "資安法遵部", "與會人員": "張志豪 (資安官)"},
            {"部門名稱": "營運管理部", "與會人員": "吳佩珊 (PMO 經理)"},
            {"部門名稱": "客服營運部", "與會人員": "王志明 (客服經理)"},
            {"部門名稱": "採購部", "與會人員": "蔡淑芬 (採購主任)"},
            {"部門名稱": "財務部", "與會人員": "鄭家豪 (財務稽核)"},
        ]
    )
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="組織部門與人員名冊")
    return buf.getvalue()


def generate_sample_roster_md() -> bytes:
    """產出標準 Markdown (.md) 組織名冊匯入範本."""
    md = """# 企業跨部門與會人員標準名冊

| 部門名稱 | 與會人員 |
| :--- | :--- |
| 經營決策委員會 | 王執行長 (CEO) |
| 產品部 | 陳建宏 (產品總監) |
| AI 研發部 | 林雅婷 (AI 架構師) |
| 資安法遵部 | 張志豪 (資安官) |
| 營運管理部 | 吳佩珊 (PMO 經理) |
| 客服營運部 | 王志明 (客服經理) |
| 採購部 | 蔡淑芬 (採購主任) |
| 財務部 | 鄭家豪 (財務稽核) |
"""
    return md.encode("utf-8")
