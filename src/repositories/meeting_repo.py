"""雙模資料持久化儲存層 (Dual-Mode Meeting Repository).

支援：
1. Supabase Cloud 模式：當設定 `SUPABASE_URL` 與 `SUPABASE_KEY` 時，直連 Supabase `meetings` 資料表 (JSONB 儲存待辦事項與決策)。
2. Local SQLite 自動備援模式：未設定雲端憑證或網路受限時，自動切換至本地 SQLite (`data/local_meetings.db`)，
   提供 100% 結構相容之 JSON 欄位存取，確保 0 元方案開箱即用與全自動測試閉環。
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src.config import get_local_db_path, get_supabase_credentials, is_supabase_configured
from src.schemas.models import (
    ActionItem,
    MeetingExtractionSchema,
    MeetingRecord,
    QCDTModel,
    RACIModel,
    SMARTGoalModel,
)
from src.services.governance import audit_action_item_governance, audit_meeting_extraction, validate_done_transition


def get_sample_meetings() -> list[MeetingRecord]:
    """產出預載之跨部門真實感範例會議記錄 (含 RACI / SMART / QCD+T 與治理缺口示範)."""
    today = datetime.now().date()
    d_minus_3 = (today - timedelta(days=3)).isoformat()
    d_minus_1 = (today - timedelta(days=1)).isoformat()
    d_plus_5 = (today + timedelta(days=5)).isoformat()
    d_plus_10 = (today + timedelta(days=10)).isoformat()
    d_plus_14 = (today + timedelta(days=14)).isoformat()

    m1 = MeetingRecord(
        id="11111111-2222-3333-4444-555555555501",
        title="2026 Q4 跨部門 AI 會議管理平台內部導入啟動會議",
        meeting_date=d_minus_1,
        departments=["產品部", "AI 研發部", "資安法遵部", "營運管理部"],
        attendees=["陳建宏 (產品總監)", "林雅婷 (AI 架構師)", "張志豪 (資安官)", "吳佩珊 (PMO 經理)"],
        executive_summary=(
            "本次啟動會議確立『AI 會議記錄管理 Web App』Phase 1 內部零成本試運行目標。"
            "會中決議全面導入 RACI 當責制、SMART 四階目標分類與自訂 QCD+T (品質、成本、交付、真實性佐證) 管理框架，"
            "並要求所有 API 金鑰嚴格透過 .env 或 BYOK 動態注入，於兩週內完成內部跨部門試用與回饋收集。"
        ),
        key_decisions=[
            "決議一：Phase 1 採 0 元方案架構（Streamlit + Supabase Free Tier + Gemini 2.5 Flash），嚴禁產生額外雲端固定授權費。",
            "決議二：每項跨部門待辦事項必須指定唯一最終當責者 (Accountable, A)，不得因跨部門協作而出現當責真空或多人推諉。",
            "決議三：待辦事項結案 (Done) 時必須填具 QCD+T 之『T (Truthfulness/Evidence)』可驗證證據連結，始得完成閉環。",
        ],
        action_items=[
            ActionItem(
                id="ACT-101",
                task_title="完成 Gemini Structured Outputs 萃取引擎與 RACI/SMART/QCD+T Schema 驗證",
                department="AI 研發部",
                owner="林雅婷 (AI 架構師)",
                due_date=d_minus_1,
                status="Done",
                raci=RACIModel(
                    accountable="林雅婷 (AI 架構師)",
                    responsible=["林雅婷 (AI 架構師)", "周哲宇 (後端工程師)"],
                    consulted=["陳建宏 (產品總監)"],
                    informed=["吳佩珊 (PMO 經理)"],
                ),
                smart=SMARTGoalModel(
                    hierarchy_level="專案成果 (Project Outcome)",
                    specific="實作 Pydantic V2 會議結構化萃取模型，涵蓋標題、摘要、決策與 RACI/SMART/QCD+T 待辦事項",
                    measurable="單元測試通過率 100%，結構化欄位解析成功率達 100%",
                    achievable="採用 google-genai 官方 SDK 原生 response_schema 功能即可達成",
                    relevant="支撐企業內部 AI 會議自動化治理之核心引擎",
                    time_bound=f"於 {d_minus_1} 18:00 前完成並通過自動化測試",
                    is_smart_compliant=True,
                ),
                qcdt=QCDTModel(
                    quality_criteria="通過 pytest 全套 Schema 與邊界條件驗證，且無任何硬編碼 API Key",
                    cost_budget="0 元 (使用 Gemini API 免費額度與內部研發工時 16h)",
                    delivery_milestone=f"{d_minus_1} 完成核心模組交付",
                    truthfulness_req="提供 Git Commit / PR 連結與 pytest 100% 通過之終端機測試紀錄",
                    evidence_submitted="PR #12 已合併，pytest 執行 18 項測試全數 PASSED (詳見 tests/test_schemas_and_governance.py)",
                    evidence_verified=True,
                    evidence_audit_feedback="✅ AI 稽核通過 (96/100)：已提供具體 PR 編號與量化測試通過證明，符合 Q 品質驗收標準。",
                ),
            ),
            ActionItem(
                id="ACT-102",
                task_title="執行 BYOK 金鑰動態注入與 Supabase RLS 資安合規審查",
                department="資安法遵部 / AI 研發部",
                owner="張志豪 (資安官)",
                due_date=d_plus_5,
                status="In Progress",
                raci=RACIModel(
                    accountable="張志豪 (資安官)",
                    responsible=["張志豪 (資安官)", "林雅婷 (AI 架構師)"],
                    consulted=["法務室"],
                    informed=["陳建宏 (產品總監)", "全體內部試用部門"],
                ),
                smart=SMARTGoalModel(
                    hierarchy_level="工作任務 (Work Task)",
                    specific="審查 .env 隔離機制、側邊欄 BYOK 密碼輸入框與 Supabase 001_init_meetings.sql RLS 腳本",
                    measurable="原始碼金鑰洩漏掃描 0 告警，RLS 讀寫權限腳本可於 Supabase SQL Editor 一鍵執行",
                    achievable="基於既有資安檢核清單與自動化正則掃描工具於 3 個工作天內完成",
                    relevant="確保 Phase 1 內部機敏會議資料不外洩並奠定 Phase 2 SaaS 資安基礎",
                    time_bound=f"於 {d_plus_5} 下班前出具資安簽核紀錄",
                    is_smart_compliant=True,
                ),
                qcdt=QCDTModel(
                    quality_criteria="零硬編碼金鑰殘留，且未設定 .env 時能平順顯示 BYOK 輸入框而不崩潰",
                    cost_budget="0 元 (內部資安審查工時 8h)",
                    delivery_milestone=f"{d_plus_5} 完成資安測試報告",
                    truthfulness_req="提交資安掃描測試報告與 RLS 腳本執行截圖",
                    evidence_submitted="",
                    evidence_verified=False,
                    evidence_audit_feedback="",
                ),
            ),
            ActionItem(
                id="ACT-103",
                task_title="收集第一波五個部門試用者回饋並整理 SaaS 商務化功能許願池",
                department="產品部 / 營運管理部",
                owner="待指定 (未明確歸屬)",
                due_date="待定",
                status="Pending",
                raci=RACIModel(
                    accountable="待指定 (未明確歸屬)",
                    responsible=["吳佩珊 (PMO 經理)", "產品企劃組"],
                    consulted=["各部門種子用戶"],
                    informed=["管理委員會"],
                ),
                smart=SMARTGoalModel(
                    hierarchy_level="個別活動 (Individual Activity)",
                    specific="訪談內部試用同仁並彙整操作體驗與 Bug 回報表單",
                    measurable="",
                    achievable="透過內部線上問卷與週會訪談執行",
                    relevant="作為 Phase 2 SaaS 上市定價與功能迭代依據",
                    time_bound="",
                    is_smart_compliant=False,
                ),
                qcdt=QCDTModel(
                    quality_criteria="涵蓋至少 5 個部門之結構化回饋清單",
                    cost_budget="0 元 (內部問卷工具)",
                    delivery_milestone="",
                    truthfulness_req="",
                    evidence_submitted="",
                    evidence_verified=False,
                    evidence_audit_feedback="",
                ),
            ),
        ],
        raw_transcript=(
            "陳建宏 (產品總監)：各位早安，今天我們召開 2026 Q4 跨部門 AI 會議管理平台啟動會議。"
            "初期 Phase 1 我們供企業內部使用，原則必須是 0 元方案、無發生成本，累積使用者經驗並持續修正 Bug，最終極目標 Phase 2 是 SaaS 上市銷售。\n"
            "林雅婷 (AI 架構師)：技術架構上我們已經完成 Gemini Structured Outputs 與 Pydantic 模型，包含 RACI、SMART 跟 QCD+T，昨天已經跑完 PR #12 全部 18 項 pytest 測試通過。\n"
            "張志豪 (資安官)：資安這塊我來當責 (Accountable)，我跟雅婷會在五天內完成 BYOK 動態金鑰跟 Supabase RLS 的資安審查，確保絕對沒有任何 API Key 寫死在程式碼裡，驗收時我會附上資安掃描報告。\n"
            "吳佩珊 (PMO 經理)：另外我們還需要收集第一波五個部門的試用回饋來規劃 SaaS 許願池，目前佩珊跟產品企劃組會去跑訪談，但最終當責人 A 是陳總還是佩珊還沒定案，截止日期跟驗收證據格式也還沒敲定，請系統先幫我們標註管理缺口提醒下次補齊！"
        ),
        source_type="sample",
    )

    m2 = MeetingRecord(
        id="11111111-2222-3333-4444-555555555502",
        title="供應鏈採購與 ERP 數據同步異常檢討暨改善會議",
        meeting_date=d_minus_3,
        departments=["資訊部", "採購部", "財務部"],
        attendees=["趙文成 (IT 經理)", "蔡淑芬 (採購主任)", "鄭家豪 (財務稽核)"],
        executive_summary=(
            "針對上週採購單與 ERP 庫存成本欄位同步延遲進行根因分析，確認為批次排程逾時且缺乏異常告警。"
            "會中依 RACI 與 QCD+T 指派資訊部進行 API 冪等重試機制改造，並由採購部與財務部完成歷史差異帳務核對。"
        ),
        key_decisions=[
            "決議一：ERP 採購同步排程改為每 15 分鐘增量同步並加入死信佇列 (DLQ) 告警。",
            "決議二：所有跨部門帳務修正必須附上對帳單差異報表作為 QCD+T 之 T (真實性證據)。",
        ],
        action_items=[
            ActionItem(
                id="ACT-201",
                task_title="重構 ERP 採購單增量同步批次程式並增設失敗自動重試機制",
                department="資訊部",
                owner="趙文成 (IT 經理)",
                due_date=d_minus_1,
                status="Blocked",
                raci=RACIModel(
                    accountable="趙文成 (IT 經理)",
                    responsible=["劉冠廷 (資深工程師)"],
                    consulted=["蔡淑芬 (採購主任)"],
                    informed=["鄭家豪 (財務稽核)"],
                ),
                smart=SMARTGoalModel(
                    hierarchy_level="工作任務 (Work Task)",
                    specific="升級 ERP 同步排程為 15 分鐘增量同步並支援 3 次指數退避重試",
                    measurable="同步延遲低於 15 分鐘，單日同步成功率 >= 99.9%",
                    achievable="需等待廠商提供測試環境憑證後部署",
                    relevant="消除採購與財務月結數據落差",
                    time_bound=f"原定 {d_minus_1} 完成，目前因廠商測試資料庫升級受阻",
                    is_smart_compliant=True,
                ),
                qcdt=QCDTModel(
                    quality_criteria="連續 72 小時壓力測試零掉單，且具備失敗告警通知",
                    cost_budget="0 元 (內部資訊部維運工時 12h)",
                    delivery_milestone=f"{d_minus_1} 部署至預備環境",
                    truthfulness_req="提供 72 小時同步監控日誌報表與告警觸發截圖",
                    evidence_submitted="",
                    evidence_verified=False,
                    evidence_audit_feedback="",
                ),
            ),
            ActionItem(
                id="ACT-202",
                task_title="完成 10 月份採購驗收單與財務應付帳款之差異調節表核對",
                department="採購部 / 財務部",
                owner="蔡淑芬 (採購主任)",
                due_date=d_plus_10,
                status="In Progress",
                raci=RACIModel(
                    accountable="蔡淑芬 (採購主任)",
                    responsible=["蔡淑芬 (採購主任)", "鄭家豪 (財務稽核)"],
                    consulted=["趙文成 (IT 經理)"],
                    informed=["營運副總"],
                ),
                smart=SMARTGoalModel(
                    hierarchy_level="專案成果 (Project Outcome)",
                    specific="逐筆核對 10 月份異常同步之 42 筆採購單並完成傳票修正",
                    measurable="42 筆差異單據 100% 完成平帳，帳實不符金額降至 0 元",
                    achievable="採購與財務聯合對帳 2 個工作天可完成",
                    relevant="確保季度財務報表真實性與內稽合規",
                    time_bound=f"於 {d_plus_10} 前完成簽核歸檔",
                    is_smart_compliant=True,
                ),
                qcdt=QCDTModel(
                    quality_criteria="42 筆單據金額、稅額與供應商統編完全一致並經雙部門主管覆核",
                    cost_budget="0 元 (內部跨部門對帳工時 10h)",
                    delivery_milestone=f"{d_plus_10} 提交最終調節表",
                    truthfulness_req="附上經採購與財務雙主管簽核之 ERP 差異調節表 PDF 編號",
                    evidence_submitted="",
                    evidence_verified=False,
                    evidence_audit_feedback="",
                ),
            ),
        ],
        raw_transcript=(
            "趙文成 (IT 經理)：上週採購單跟 ERP 同步延遲主要是夜間全量批次逾時。這項重構任務由我當責 (A)，劉冠廷負責執行 (R)，原本預計昨天完成，但目前等待 ERP 廠商測試機憑證所以暫時受阻 (Blocked)。\n"
            "蔡淑芬 (採購主任)：那 10 月份受影響的 42 筆採購單，跨採購部跟財務部的對帳由我擔任最終當責者 (A)，我跟財務鄭家豪一起執行 (R)，十天內把差異金額歸零，結案時會附上雙主管簽核的 ERP 差異調節表編號作為 T 佐證。"
        ),
        source_type="sample",
    )

    m3 = MeetingRecord(
        id="11111111-2222-3333-4444-555555555503",
        title="2027 年度企業數位轉型與 SaaS 產品商務化策略共識營",
        meeting_date=today.isoformat(),
        departments=["經營決策委員會", "商務開發部", "AI 研發部"],
        attendees=["王執行長 (CEO)", "陳建宏 (產品總監)", "何雅雯 (BD 總監)"],
        executive_summary=(
            "確立公司由內部工具孵化轉向外部 B2B SaaS 營收成長之雙軌策略。"
            "將『AI 會議記錄管理 Web App』列為旗艦商業化產品，先於內部達成零成本高穩定度驗證，再於下一階段啟動多租戶訂閱制上市。"
        ),
        key_decisions=[
            "決議一：Phase 1 內部累積滿 50 場真實會議治理數據並達成 95% 穩定度後，正式啟動 Phase 2 SaaS 商業化。",
            "決議二：以『RACI + SMART + QCD+T 內建管理治理引擎』作為市場差異化核心賣點。",
        ],
        action_items=[
            ActionItem(
                id="ACT-301",
                task_title="制定 2027 B2B SaaS 訂閱制定價模型與早鳥企業客戶導入方案",
                department="商務開發部",
                owner="何雅雯 (BD 總監)",
                due_date=d_plus_14,
                status="Pending",
                raci=RACIModel(
                    accountable="何雅雯 (BD 總監)",
                    responsible=["何雅雯 (BD 總監)", "市場分析小組"],
                    consulted=["陳建宏 (產品總監)", "財務部"],
                    informed=["王執行長 (CEO)"],
                ),
                smart=SMARTGoalModel(
                    hierarchy_level="企業目標 (Enterprise Goal)",
                    specific="完成 Free / Pro / Enterprise 三層級 SaaS 定價與毛利結構試算模型",
                    measurable="完成 10 家潛在企業訪談驗證，目標首年 ARR 達標率模型毛利率 >= 75%",
                    achievable="結合內部 Phase 1 Token 消耗實測數據與競品分析即可精準建模",
                    relevant="直接決定 Phase 2 SaaS 上市商業模式與營收成長曲線",
                    time_bound=f"於 {d_plus_14} 經營月會提報核准",
                    is_smart_compliant=True,
                ),
                qcdt=QCDTModel(
                    quality_criteria="包含 Token 單位成本分析、客戶獲客成本 (CAC) 與 LTV 財務試算表",
                    cost_budget="0 元 (內部 BD 與產品團隊協作)",
                    delivery_milestone=f"{d_plus_14} 提交定價企劃書與財務試算表",
                    truthfulness_req="提供 10 家潛在企業訪談紀錄摘要與定價試算試算表連結",
                    evidence_submitted="",
                    evidence_verified=False,
                    evidence_audit_feedback="",
                ),
            ),
        ],
        raw_transcript=(
            "王執行長 (CEO)：我們的 AI 會議記錄管理系統不只是做逐字稿摘要，重點是把 RACI、SMART 跟 QCD+T 變成企業自動運轉的治理基因。"
            "請 BD 總監何雅雯當責 (A)，在兩週內完成 Phase 2 B2B SaaS 三層級定價模型與 10 家潛在客戶訪談，結案時請附上訪談紀錄與財務試算表作為驗證證據！"
        ),
        source_type="sample",
    )

    return [audit_meeting_extraction(m1), audit_meeting_extraction(m2), audit_meeting_extraction(m3)]  # type: ignore[list-item]


class MeetingRepository:
    """雙模會議記錄儲存庫：自動協調 Supabase Cloud 與 Local SQLite."""

    def __init__(self, db_path: Path | None = None, force_local: bool = False) -> None:
        self.db_path = db_path or get_local_db_path()
        self.force_local = force_local
        self._supabase_client: Any = None
        self._active_mode: str = "sqlite"
        self._last_error: str = ""
        self._init_storage()

    def _init_storage(self) -> None:
        """初始化本地 SQLite 表結構，並嘗試連線 Supabase (若已設定)."""
        self._init_sqlite()
        if not self.force_local and is_supabase_configured():
            try:
                from supabase import create_client

                url, key = get_supabase_credentials()
                self._supabase_client = create_client(url, key)
                # 執行輕量探測查詢確認資料表可存取
                self._supabase_client.table("meetings").select("id").limit(1).execute()
                self._active_mode = "supabase"
                self._last_error = ""
            except Exception as exc:
                self._supabase_client = None
                self._active_mode = "sqlite"
                self._last_error = f"Supabase 連線或資料表探測失敗，已自動切換本地 SQLite 備援：{exc}"
        else:
            self._active_mode = "sqlite"

    def _get_sqlite_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_sqlite(self) -> None:
        """建立與 Supabase `meetings` 表完全對齊之本地 SQLite 資料表."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._get_sqlite_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS meetings (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    meeting_date TEXT NOT NULL,
                    departments TEXT NOT NULL DEFAULT '[]',
                    attendees TEXT NOT NULL DEFAULT '[]',
                    executive_summary TEXT NOT NULL DEFAULT '',
                    key_decisions TEXT NOT NULL DEFAULT '[]',
                    action_items TEXT NOT NULL DEFAULT '[]',
                    raw_transcript TEXT NOT NULL DEFAULT '',
                    source_type TEXT NOT NULL DEFAULT 'text',
                    workspace_id TEXT NOT NULL DEFAULT 'internal-default',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    @property
    def storage_mode_label(self) -> str:
        """回傳目前運作中的儲存引擎人類可讀名稱."""
        if self._active_mode == "supabase":
            return "☁️ Supabase Cloud (PostgreSQL + JSONB + RLS)"
        return "💾 Local SQLite 雙模備援引擎 (0 元免配置閉環模式)"

    @property
    def is_cloud_mode(self) -> bool:
        return self._active_mode == "supabase"

    @property
    def last_error(self) -> str:
        return self._last_error

    def ensure_sample_data_if_empty(self) -> int:
        """若目前資料庫無任何會議記錄，自動載入 3 筆跨部門範例會議."""
        existing = self.list_meetings()
        if not existing:
            return self.seed_sample_meetings(force=False)
        return 0

    def seed_sample_meetings(self, force: bool = True) -> int:
        """寫入或重置系統預載之跨部門範例會議資料."""
        samples = get_sample_meetings()
        count = 0
        for sample in samples:
            if force or not self.get_meeting_by_id(sample.id):
                self.save_meeting(sample)
                count += 1
        return count

    def _record_to_row_dict(self, record: MeetingRecord) -> dict[str, Any]:
        """將 MeetingRecord 轉換為資料庫列字典."""
        audited = audit_meeting_extraction(record)
        assert isinstance(audited, MeetingRecord)
        now_iso = datetime.now().isoformat(timespec="seconds")
        if not audited.created_at:
            audited.created_at = now_iso
        audited.updated_at = now_iso
        if not audited.id:
            audited.id = str(uuid.uuid4())

        return {
            "id": audited.id,
            "title": audited.title,
            "meeting_date": audited.meeting_date,
            "departments": audited.departments,
            "attendees": audited.attendees,
            "executive_summary": audited.executive_summary,
            "key_decisions": audited.key_decisions,
            "action_items": [item.model_dump() for item in audited.action_items],
            "raw_transcript": audited.raw_transcript,
            "source_type": audited.source_type,
            "workspace_id": audited.workspace_id,
            "created_at": audited.created_at,
            "updated_at": audited.updated_at,
        }

    def _row_to_record(self, row: dict[str, Any] | sqlite3.Row) -> MeetingRecord:
        """將資料庫列還原為 MeetingRecord 並執行治理檢核."""
        data = dict(row)
        for json_field in ("departments", "attendees", "key_decisions", "action_items"):
            val = data.get(json_field)
            if isinstance(val, str):
                try:
                    data[json_field] = json.loads(val)
                except Exception:
                    data[json_field] = []
            elif val is None:
                data[json_field] = []

        record = MeetingRecord.model_validate(data)
        audited = audit_meeting_extraction(record)
        assert isinstance(audited, MeetingRecord)
        return audited

    def save_meeting(self, meeting: MeetingRecord | MeetingExtractionSchema, raw_transcript: str = "", source_type: str = "text") -> MeetingRecord:
        """新增或覆寫儲存會議記錄 (Upsert)."""
        if isinstance(meeting, MeetingRecord):
            record = meeting
            if raw_transcript and not record.raw_transcript:
                record.raw_transcript = raw_transcript
            if source_type != "text" and record.source_type == "text":
                record.source_type = source_type
        else:
            record = MeetingRecord(
                **meeting.model_dump(),
                id=str(uuid.uuid4()),
                raw_transcript=raw_transcript,
                source_type=source_type,
            )

        row_dict = self._record_to_row_dict(record)

        if self._active_mode == "supabase" and self._supabase_client is not None:
            try:
                self._supabase_client.table("meetings").upsert(row_dict).execute()
                return self._row_to_record(row_dict)
            except Exception as exc:
                self._last_error = f"Supabase 寫入失敗，自動同步寫入本地 SQLite：{exc}"

        with self._get_sqlite_conn() as conn:
            conn.execute(
                """
                INSERT INTO meetings (
                    id, title, meeting_date, departments, attendees,
                    executive_summary, key_decisions, action_items,
                    raw_transcript, source_type, workspace_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    meeting_date = excluded.meeting_date,
                    departments = excluded.departments,
                    attendees = excluded.attendees,
                    executive_summary = excluded.executive_summary,
                    key_decisions = excluded.key_decisions,
                    action_items = excluded.action_items,
                    raw_transcript = excluded.raw_transcript,
                    source_type = excluded.source_type,
                    workspace_id = excluded.workspace_id,
                    updated_at = excluded.updated_at
                """,
                (
                    row_dict["id"],
                    row_dict["title"],
                    row_dict["meeting_date"],
                    json.dumps(row_dict["departments"], ensure_ascii=False),
                    json.dumps(row_dict["attendees"], ensure_ascii=False),
                    row_dict["executive_summary"],
                    json.dumps(row_dict["key_decisions"], ensure_ascii=False),
                    json.dumps(row_dict["action_items"], ensure_ascii=False),
                    row_dict["raw_transcript"],
                    row_dict["source_type"],
                    row_dict["workspace_id"],
                    row_dict["created_at"],
                    row_dict["updated_at"],
                ),
            )
            conn.commit()

        return self._row_to_record(row_dict)

    def get_meeting_by_id(self, meeting_id: str) -> MeetingRecord | None:
        """依 ID 查詢單筆會議記錄."""
        if self._active_mode == "supabase" and self._supabase_client is not None:
            try:
                resp = self._supabase_client.table("meetings").select("*").eq("id", meeting_id).limit(1).execute()
                if resp.data:
                    return self._row_to_record(resp.data[0])
            except Exception as exc:
                self._last_error = f"Supabase 讀取失敗：{exc}"

        with self._get_sqlite_conn() as conn:
            cur = conn.execute("SELECT * FROM meetings WHERE id = ?", (meeting_id,))
            row = cur.fetchone()
            if row:
                return self._row_to_record(row)
        return None

    def list_meetings(
        self,
        search_query: str = "",
        department_filter: str = "全部",
        status_filter: str = "全部",
    ) -> list[MeetingRecord]:
        """查詢歷史會議記錄，支援關鍵字搜尋、部門篩選與待辦事項狀態篩選."""
        records: list[MeetingRecord] = []

        if self._active_mode == "supabase" and self._supabase_client is not None:
            try:
                resp = self._supabase_client.table("meetings").select("*").order("meeting_date", desc=True).execute()
                records = [self._row_to_record(r) for r in (resp.data or [])]
            except Exception as exc:
                self._last_error = f"Supabase 查詢失敗，改讀本地 SQLite：{exc}"

        if not records:
            with self._get_sqlite_conn() as conn:
                cur = conn.execute("SELECT * FROM meetings ORDER BY meeting_date DESC, updated_at DESC")
                rows = cur.fetchall()
                records = [self._row_to_record(r) for r in rows]

        # 應用層搜尋與篩選 (同時相容 Supabase 與 SQLite JSON 欄位)
        query = (search_query or "").strip().lower()
        dept = (department_filter or "全部").strip()
        status = (status_filter or "全部").strip()

        filtered: list[MeetingRecord] = []
        for rec in records:
            if query:
                searchable_blob = " ".join(
                    [
                        rec.title,
                        rec.executive_summary,
                        rec.raw_transcript,
                        " ".join(rec.departments),
                        " ".join(rec.attendees),
                        " ".join(rec.key_decisions),
                        " ".join(
                            f"{a.task_title} {a.owner} {a.raci.accountable} {' '.join(a.raci.responsible)}"
                            for a in rec.action_items
                        ),
                    ]
                ).lower()
                if query not in searchable_blob:
                    continue

            if dept and dept != "全部":
                dept_matched = any(dept in d for d in rec.departments) or any(
                    dept in a.department for a in rec.action_items
                )
                if not dept_matched:
                    continue

            if status and status != "全部":
                status_matched = any(a.status == status for a in rec.action_items)
                if not status_matched:
                    continue

            filtered.append(rec)

        return filtered

    def update_action_item(
        self,
        meeting_id: str,
        action_id: str,
        new_status: str,
        evidence_submitted: str | None = None,
        accountable: str | None = None,
        due_date: str | None = None,
        quality_criteria: str | None = None,
        truthfulness_req: str | None = None,
        evidence_verified: bool | None = None,
        evidence_audit_feedback: str | None = None,
        enforce_evidence_on_done: bool = True,
    ) -> tuple[bool, str, MeetingRecord | None]:
        """更新指定會議中之待辦事項狀態與 RACI/QCD+T 欄位，並強制檢核 Done 狀態之 T (成果佐證) 閉環."""
        meeting = self.get_meeting_by_id(meeting_id)
        if not meeting:
            return False, f"找不到會議記錄 (ID: {meeting_id})", None

        target_item: ActionItem | None = None
        for idx, item in enumerate(meeting.action_items):
            if item.id == action_id:
                target_item = item
                break

        if target_item is None:
            return False, f"找不到待辦事項 (ID: {action_id})", None

        effective_evidence = (
            evidence_submitted if evidence_submitted is not None else target_item.qcdt.evidence_submitted
        )

        if enforce_evidence_on_done and new_status == "Done":
            ok, msg = validate_done_transition(target_item, new_status, effective_evidence)
            if not ok:
                return False, msg, meeting

        # 套用欄位更新
        target_item.status = new_status  # type: ignore[assignment]
        if evidence_submitted is not None:
            target_item.qcdt.evidence_submitted = evidence_submitted.strip()
        if accountable is not None and accountable.strip():
            target_item.raci.accountable = accountable.strip()
            target_item.owner = accountable.strip()
        if due_date is not None and due_date.strip():
            target_item.due_date = due_date.strip()
        if quality_criteria is not None:
            target_item.qcdt.quality_criteria = quality_criteria.strip()
        if truthfulness_req is not None:
            target_item.qcdt.truthfulness_req = truthfulness_req.strip()
        if evidence_verified is not None:
            target_item.qcdt.evidence_verified = evidence_verified
        if evidence_audit_feedback is not None:
            target_item.qcdt.evidence_audit_feedback = evidence_audit_feedback.strip()

        # 重新執行單項治理檢核
        audit_action_item_governance(target_item)
        saved = self.save_meeting(meeting)
        return True, f"✅ 待辦事項「{target_item.task_title}」已成功更新並寫入資料庫。", saved

    def delete_meeting(self, meeting_id: str) -> bool:
        """刪除指定會議記錄."""
        if self._active_mode == "supabase" and self._supabase_client is not None:
            try:
                self._supabase_client.table("meetings").delete().eq("id", meeting_id).execute()
            except Exception as exc:
                self._last_error = f"Supabase 刪除失敗：{exc}"

        with self._get_sqlite_conn() as conn:
            cur = conn.execute("DELETE FROM meetings WHERE id = ?", (meeting_id,))
            conn.commit()
            return cur.rowcount > 0
