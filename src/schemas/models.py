"""Pydantic V2 結構化資料模型：整合 RACI、SMART Goals 與 QCD+T 管理框架.

本模組定義：
1. Gemini Structured Outputs 專用之萃取 Schema (`MeetingExtractionSchema`, `EvidenceAuditResult`)
2. 資料庫持久化與前端展示共用之完整會議記錄模型 (`MeetingRecord`, `ActionItem`)
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class SMARTHierarchyLevel(str, Enum):
    """SMART 目標階層分類：嚴格區分企業目標、專案成果、工作任務與個別活動，不可混為一談."""

    ENTERPRISE_GOAL = "企業目標 (Enterprise Goal)"
    PROJECT_OUTCOME = "專案成果 (Project Outcome)"
    WORK_TASK = "工作任務 (Work Task)"
    INDIVIDUAL_ACTIVITY = "個別活動 (Individual Activity)"


class ActionStatus(str, Enum):
    """待辦事項執行狀態."""

    PENDING = "Pending"
    IN_PROGRESS = "In Progress"
    BLOCKED = "Blocked"
    DONE = "Done"


class RACIModel(BaseModel):
    """RACI 責任歸屬矩陣模型.

    原則：每項任務原則上須有且只有一名最終當責者 A (Accountable)；
    可以有多名實際執行者 R (Responsible)。跨部門任務不得因涉及多個部門而失去最終當責歸屬。
    """

    accountable: str = Field(
        default="待指定 (未明確歸屬)",
        description="A (Accountable) 最終當責者：必須且僅限單一人名或職稱。若會議中未明確指定唯一當責者，請填寫『待指定 (未明確歸屬)』。",
    )
    responsible: list[str] = Field(
        default_factory=list,
        description="R (Responsible) 實際執行者清單：可包含一名或多名負責具體執行的人員。",
    )
    consulted: list[str] = Field(
        default_factory=list,
        description="C (Consulted) 應徵詢意見者清單：提供專業意見或雙向溝通之人員/部門。",
    )
    informed: list[str] = Field(
        default_factory=list,
        description="I (Informed) 應被告知者清單：需要接收進度或結果通知之人員/部門。",
    )


class SMARTGoalModel(BaseModel):
    """SMART 原則與目標層級模型.

    區分企業目標、專案成果、工作任務與個別活動，並檢核五大維度。
    """

    hierarchy_level: Literal[
        "企業目標 (Enterprise Goal)",
        "專案成果 (Project Outcome)",
        "工作任務 (Work Task)",
        "個別活動 (Individual Activity)",
    ] = Field(
        default="工作任務 (Work Task)",
        description="目標層級分類：必須明確區分為『企業目標 (Enterprise Goal)』、『專案成果 (Project Outcome)』、『工作任務 (Work Task)』或『個別活動 (Individual Activity)』。",
    )
    specific: str = Field(
        default="",
        description="S (Specific 具體)：明確說明要完成什麼事項、範圍與對象。",
    )
    measurable: str = Field(
        default="",
        description="M (Measurable 可衡量)：具體的量化指標或可驗證的完成標準。",
    )
    achievable: str = Field(
        default="",
        description="A (Achievable 可達成)：以現有資源、權限與時間是否可達成之評估說明。",
    )
    relevant: str = Field(
        default="",
        description="R (Relevant 相關性)：此項目如何對齊上層專案成果或企業目標。",
    )
    time_bound: str = Field(
        default="",
        description="T (Time-bound 有期限)：明確的時間期限或階段查核點。",
    )
    is_smart_compliant: bool = Field(
        default=True,
        description="是否完整具備具體、可衡量、可達成、相關性與明確期限五項要件。",
    )


class QCDTModel(BaseModel):
    """QCD+T 自訂管理擴充框架模型.

    - Q (Quality)：品質與驗收條件
    - C (Cost/Budget)：成本與預算（含 0 元方案或內部工時資源）
    - D (Delivery)：交付期限與里程碑
    - T (Truthfulness/Evidence)：進度、狀態及成果的真實性與可驗證證據（本專案自訂擴充維度）
    """

    quality_criteria: str = Field(
        default="",
        description="Q (Quality 品質與驗收條件)：成果應達到的品質標準與驗收條件。",
    )
    cost_budget: str = Field(
        default="0 元 (內部資源/工時)",
        description="C (Cost/Budget 成本與預算)：所需預算、外部費用或內部人力工時配置。",
    )
    delivery_milestone: str = Field(
        default="",
        description="D (Delivery 交付期限與里程碑)：關鍵交付節點與最終期限。",
    )
    truthfulness_req: str = Field(
        default="",
        description="T (Truthfulness/Evidence 真實性與可驗證證據要求)：結案或回報進度時必須提供的具體佐證（如：系統截圖、PR 連結、測試報告、簽核紀錄）。",
    )
    evidence_submitted: str = Field(
        default="",
        description="執行者於更新狀態或完成任務時實際提交之佐證資料或連結。",
    )
    evidence_verified: bool = Field(
        default=False,
        description="提交之成果佐證 (T) 是否已通過品質驗收條件 (Q) 檢核。",
    )
    evidence_audit_feedback: str = Field(
        default="",
        description="AI 或管理者針對提交佐證 (T) 對照品質條件 (Q) 之查核評語。",
    )


class ActionItem(BaseModel):
    """會議待辦事項 (Action Item)，深度綁定 RACI + SMART + QCD+T."""

    id: str = Field(
        default_factory=lambda: f"ACT-{uuid.uuid4().hex[:6].upper()}",
        description="待辦事項唯一識別碼 (例如 ACT-01, ACT-02)。",
    )
    task_title: str = Field(
        ...,
        description="待辦事項具體名稱。",
    )
    department: str = Field(
        default="跨部門/未分類",
        description="主責或涉及之部門名稱（跨部門請標註如『產品部 / 研發部』）。",
    )
    owner: str = Field(
        default="待指定",
        description="主要負責人 (Owner)，應對應 RACI 之最終當責者 A 或主要執行者 R。",
    )
    due_date: str = Field(
        default="待定",
        description="截止日期，格式優先為 YYYY-MM-DD；若會議未明定請填『待定』。",
    )
    status: Literal["Pending", "In Progress", "Blocked", "Done"] = Field(
        default="Pending",
        description="任務狀態：Pending (待處理)、In Progress (進行中)、Blocked (受阻)、Done (已完成)。",
    )
    raci: RACIModel = Field(
        default_factory=RACIModel,
        description="RACI 責任歸屬設定。",
    )
    smart: SMARTGoalModel = Field(
        default_factory=SMARTGoalModel,
        description="SMART 目標層級與五維度評估。",
    )
    qcdt: QCDTModel = Field(
        default_factory=QCDTModel,
        description="QCD+T (品質、成本、交付、真實性佐證) 管理維度。",
    )
    governance_gaps: list[str] = Field(
        default_factory=list,
        description="管理缺口警示清單：當缺少唯一當責者 A、缺少期限、未定義驗收條件 Q 或可驗證證據 T 時自動列出警示。",
    )


class MeetingExtractionSchema(BaseModel):
    """提供予 Gemini Structured Outputs (`response_schema`) 之頂層會議萃取結構."""

    title: str = Field(
        ...,
        description="(a) 會議標題：精準反映會議主題與核心目的。",
    )
    meeting_date: str = Field(
        default_factory=lambda: date.today().isoformat(),
        description="會議日期 (YYYY-MM-DD 格式)。若逐字稿未提及則採用當日日期。",
    )
    departments: list[str] = Field(
        default_factory=list,
        description="參與或涉及之部門清單。",
    )
    attendees: list[str] = Field(
        default_factory=list,
        description="會議出席人員清單（含姓名與職稱/部門）。",
    )
    executive_summary: str = Field(
        ...,
        description="(b) 高階執行摘要 (Executive Summary)：濃縮會議背景、核心議題、跨部門共識與管理重點。",
    )
    key_decisions: list[str] = Field(
        default_factory=list,
        description="(c) 關鍵決策清單 (Key Decisions)：會議中正式拍板定案之決議事項。",
    )
    action_items: list[ActionItem] = Field(
        default_factory=list,
        description="(d) 待辦事項清單 (Action Items)：含負責人 Owner、截止日 Due Date、狀態 Status 以及完整 RACI / SMART / QCD+T 結構。",
    )


class MeetingRecord(MeetingExtractionSchema):
    """儲存於資料庫 (Supabase `meetings` 表或本地 SQLite) 之完整會議記錄實體."""

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="會議唯一 UUID。",
    )
    raw_transcript: str = Field(
        default="",
        description="原始會議逐字稿或輸入文本。",
    )
    source_type: str = Field(
        default="text",
        description="輸入來源類型：text (貼上文本)、file (上傳文檔)、audio (音訊轉譯)、sample (系統範例)。",
    )
    workspace_id: str = Field(
        default="internal-default",
        description="工作區識別碼 (Phase 1 為 internal-default，Phase 2 支援多租戶隔離)。",
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds"),
        description="建立時間 (ISO 8601)。",
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds"),
        description="最後更新時間 (ISO 8601)。",
    )


class EvidenceAuditResult(BaseModel):
    """QCD+T 中針對提交之『T (成果佐證)』對照『Q (品質驗收條件)』之 AI 稽核結果結構."""

    is_verified: bool = Field(
        ...,
        description="提交之成果佐證 (T) 是否具體可信且滿足品質驗收條件 (Q) 與證據要求。",
    )
    audit_score: int = Field(
        ...,
        description="佐證完整度與真實性可驗證評分 (0 到 100)。",
    )
    feedback: str = Field(
        ...,
        description="具體稽核結論：指出佐證已滿足哪些驗收條件，或尚缺哪些具體證據連結/數據。",
    )
