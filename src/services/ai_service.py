"""Google Gemini AI 引擎服務：支援音訊兩階段多模態轉譯、Structured Outputs (Pydantic) 會議萃取與 QCD+T 佐證稽核.

核心能力：
1. Stage 1 音訊轉譯 (`transcribe_audio`)：使用 `gemini-2.5-flash` 免費額度多模態能力將 `.mp3`/`.wav`/`.m4a`/`.ogg` 轉為結構化逐字稿。
2. Stage 2 會議結構化萃取 (`extract_meeting_from_transcript`)：透過 `response_schema=MeetingExtractionSchema` 強制輸出符合 RACI + SMART + QCD+T 之結構化資料。
3. Stage 3 成果佐證 T vs Q 稽核 (`audit_action_evidence`)：驗證執行者提交之佐證 `T` 是否符合驗收標準 `Q`。
4. 離線智慧規則備援引擎：當使用者尚未填入 `GEMINI_API_KEY` 時，提供本地規則解析備援以便於零設定環境下體驗完整管理流程與自動化測試。
"""

from __future__ import annotations

import datetime
import re
from typing import Any

from src.config import get_candidate_gemini_models, get_gemini_api_key, get_gemini_model
from src.schemas.models import (
    ActionItem,
    EvidenceAuditResult,
    MeetingExtractionSchema,
    QCDTModel,
    RACIModel,
    SMARTGoalModel,
)
from src.services.governance import audit_meeting_extraction, is_vague_or_empty
from src.services.meeting_template_service import try_parse_structured_template_text

EXTRACTION_SYSTEM_PROMPT = """你是一位精通企業治理與專案管理的「AI 會議記錄管理專家」。
請根據使用者提供的會議逐字稿或紀錄文本，嚴格依照指定的 Pydantic Schema (`MeetingExtractionSchema`) 進行結構化萃取。

【管理框架強制規範】：
1. RACI Model：
   - R (Responsible)：實際執行者（可為一名或多名）。
   - A (Accountable)：最終當責者（每項任務原則上須有且只有一名最終當責者 A；跨部門任務不得因涉及多個部門而失去最終當責歸屬！若會議中未明確指定唯一當責者，請將 `accountable` 填為 `"待指定 (未明確歸屬)"`）。
   - C (Consulted)：應徵詢意見者。
   - I (Informed)：應被告知者。

2. SMART Goals：
   - 必須將每項待辦事項明確歸類至以下四個層級之一，不可混為一談：
     * `"企業目標 (Enterprise Goal)"`
     * `"專案成果 (Project Outcome)"`
     * `"工作任務 (Work Task)"`
     * `"個別活動 (Individual Activity)"`
   - 清楚拆解 Specific (具體)、Measurable (可衡量)、Achievable (可達成)、Relevant (相關性)、Time-bound (有期限)。

3. QCD+T 自訂管理擴充框架：
   - Q (Quality)：品質標準與驗收條件。
   - C (Cost/Budget)：成本、預算或工時資源（若為內部零成本專案請註明 `"0 元 (內部資源/工時)"`）。
   - D (Delivery)：交付期限與里程碑。
   - T (Truthfulness/Evidence)：進度、狀態及成果的真實性與可驗證證據要求（請具體指出結案時應提交何種證據，例如 PR 連結、測試報告、簽核單、數據截圖）。

4. 語言要求：請全面使用專業、精準的繁體中文（Traditional Chinese）輸出。
"""


def transcribe_audio(
    audio_bytes: bytes,
    mime_type: str = "audio/mp3",
    filename: str = "meeting_audio.mp3",
    api_key: str | None = None,
) -> tuple[str, bool, str]:
    """階段一：將上傳之音訊檔透過 Gemini 多模態能力轉譯為逐字稿文本.

    回傳:
        (transcript_text, used_real_gemini, status_message)
    """
    resolved_key = (api_key if api_key is not None else get_gemini_api_key()).strip()
    model_name = get_gemini_model()

    demo_transcript = (
        f"【音訊模擬轉譯逐字稿 - 檔案：{filename}（本地離線模擬轉譯模式）】\n"
        "主席 (林總監 - 產品部)：各位同仁好，今天針對本季產品上市與跨部門交付召開同步會議。\n"
        "王工程師 (AI 研發部)：目前模型推論 API 已經完成壓測，由我當責 (A) 在本週五前完成正式環境部署，"
        "驗收條件 Q 是 P95 延遲低於 800ms，結案時我會附上 Grafana 壓測報告連結作為 T 佐證。\n"
        "陳經理 (客服營運部)：客服 SOP 手冊更新由我擔任最終當責者 (A)，張專員與李專員負責執行 (R)，"
        "預計下週三前完成 20 題常見問題演練，預算為 0 元內部工時，完成後會提交教育訓練簽到表與測驗結果連結。\n"
        "主席 (林總監 - 產品部)：另外跨部門客戶滿意度追蹤機制請大家一起支援，但目前還沒指定誰是唯一當責者 A，請先列為待辦事項並標記管理缺口。"
    )

    if not resolved_key:
        return (
            demo_transcript,
            False,
            "ℹ️ 尚未設定 Gemini API Key，已產生模擬音訊轉譯逐字稿供您測試兩階段流程（於左側邊欄輸入 BYOK 金鑰即可啟用真實 Gemini 音訊轉譯）。",
        )

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=resolved_key)
        prompt = (
            "請將這段會議音訊完整、精準地轉譯為繁體中文會議逐字稿。"
            "若能辨識不同發言者或部門角色，請以『發言者：內容』格式分段呈現，並保留所有關於負責人、期限、預算、品質標準與決策的細節。"
        )
        last_exc: Exception | None = None
        for cand_model in get_candidate_gemini_models(model_name):
            try:
                response = client.models.generate_content(
                    model=cand_model,
                    contents=[
                        types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
                        prompt,
                    ],
                )
                text = (response.text or "").strip()
                if text:
                    return text, True, f"✅ 已透過 Google Gemini ({cand_model}) 完成音訊多模態逐字稿轉譯！"
            except Exception as inner_exc:
                last_exc = inner_exc
                continue
        if last_exc is not None:
            raise last_exc
        return demo_transcript, False, "⚠️ Gemini 音訊轉譯回傳空白內容，已自動切換模擬逐字稿供預覽。"
    except Exception as exc:
        return (
            demo_transcript,
            False,
            f"⚠️ Gemini 音訊轉譯連線受限或金鑰異常（{exc}），已自動切換本地模擬逐字稿，確保兩階段工作流不中斷。",
        )


def _fallback_rule_based_extraction(transcript: str) -> MeetingExtractionSchema:
    """當未提供 Gemini API Key 時之離線智慧規則萃取器，確保無金鑰環境下仍能 100% 驗證 RACI/SMART/QCD+T 流程."""
    lines = [ln.strip() for ln in (transcript or "").splitlines() if ln.strip()]
    today_iso = datetime.date.today().isoformat()
    plus_7_iso = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()

    # 嘗試從第一行或關鍵字擷取標題
    title = "跨部門專案管理與行動方案決策會議"
    for ln in lines[:4]:
        if any(k in ln for k in ["會議", "週會", "啟動", "檢討", "共識", "討論"]):
            cleaned_title = re.sub(r"^[#\-\*【\[]+|[\]】]+$", "", ln).strip()
            if 4 <= len(cleaned_title) <= 50:
                title = cleaned_title
                break

    # 擷取部門與出席者
    dept_candidates = ["產品部", "研發部", "AI 研發部", "資安部", "資安法遵部", "客服部", "客服營運部", "採購部", "財務部", "資訊部", "業務部", "行銷部", "營運部"]
    departments = [d for d in dept_candidates if d in transcript]
    if not departments:
        departments = ["產品部", "研發部", "營運管理部"]

    attendees: list[str] = []
    speaker_matches = re.findall(r"^([\u4e00-\u9fa5A-Za-z0-9_（）\(\)\s\-]{2,20})[：:]", transcript, flags=re.MULTILINE)
    for sp in speaker_matches:
        sp_clean = sp.strip()
        if sp_clean and sp_clean not in attendees and len(sp_clean) <= 18:
            attendees.append(sp_clean)
    if not attendees:
        attendees = ["會議主席", "跨部門專案代表"]

    # 擷取決策
    decisions: list[str] = []
    for ln in lines:
        if any(k in ln for k in ["決議", "拍板", "決定", "原則", "確定", "通過"]):
            decisions.append(ln)
    if not decisions:
        decisions = [
            "確立專案依循 RACI 單一當責制與 SMART 目標分層原則推進。",
            "所有交付項目於結案 (Done) 時須檢附 QCD+T 可驗證成果佐證 (T)。",
        ]

    # 根據段落產生結構化 Action Items
    action_items: list[ActionItem] = []
    action_idx = 1
    for ln in lines:
        if any(k in ln for k in ["當責", "負責", "完成", "提交", "部署", "待辦", "審查", "建立", "更新"]):
            if len(ln) < 10:
                continue
            # 判斷是否有明確當責人
            has_missing_a = any(k in ln for k in ["還沒指定", "未定", "待指定", "大家一起", "共同當責"])
            speaker_prefix = ln.split("：")[0].split(":")[0].strip() if ("：" in ln or ":" in ln) else ""
            accountable_person = "待指定 (未明確歸屬)" if has_missing_a else (speaker_prefix or attendees[0])

            # 判斷日期
            date_match = re.search(r"\d{4}-\d{2}-\d{2}", ln)
            due_date = date_match.group(0) if date_match else ("待定" if has_missing_a else plus_7_iso)

            task_desc = ln.split("：", 1)[-1].split(":", 1)[-1].strip()
            short_title = task_desc[:38] + ("..." if len(task_desc) > 38 else "")

            item = ActionItem(
                id=f"ACT-{action_idx:02d}",
                task_title=short_title,
                department=departments[0] if len(departments) == 1 else " / ".join(departments[:2]),
                owner=accountable_person,
                due_date=due_date,
                status="Pending",
                raci=RACIModel(
                    accountable=accountable_person,
                    responsible=[accountable_person] if not has_missing_a else ["跨部門執行小組"],
                    consulted=departments[:1],
                    informed=["專案管理辦公室 (PMO)"],
                ),
                smart=SMARTGoalModel(
                    hierarchy_level="工作任務 (Work Task)" if action_idx > 1 else "專案成果 (Project Outcome)",
                    specific=task_desc,
                    measurable="" if has_missing_a else "100% 通過驗收標準並完成交付物歸檔",
                    achievable="運用現有內部團隊資源與 0 元開源/免費方案即可執行",
                    relevant="直接對齊本次會議核心決議與部門季度目標",
                    time_bound="" if due_date == "待定" else f"於 {due_date} 前完成交付",
                    is_smart_compliant=not has_missing_a,
                ),
                qcdt=QCDTModel(
                    quality_criteria="" if has_missing_a else "符合會議決議之功能規格與品質指標",
                    cost_budget="0 元 (內部資源/工時)",
                    delivery_milestone="" if due_date == "待定" else f"{due_date} 里程碑驗收",
                    truthfulness_req="" if has_missing_a else "提交完成報告連結、系統截圖或測試通過紀錄",
                ),
            )
            action_items.append(item)
            action_idx += 1
            if action_idx > 5:
                break

    if not action_items:
        action_items.append(
            ActionItem(
                id="ACT-01",
                task_title="彙整會議決議並確認跨部門 RACI 最終當責者歸屬",
                department=" / ".join(departments[:2]),
                owner=attendees[0],
                due_date=plus_7_iso,
                status="Pending",
                raci=RACIModel(
                    accountable=attendees[0],
                    responsible=attendees[:2],
                    consulted=departments,
                    informed=["全體與會者"],
                ),
                smart=SMARTGoalModel(
                    hierarchy_level="工作任務 (Work Task)",
                    specific="根據會議討論內容完成行動方案展開與責任歸屬確認",
                    measurable="所有待辦事項 100% 完成 RACI 單一 A 指定與 QCD+T 設定",
                    achievable="於內部會議管理系統中直接編修即可達成",
                    relevant="確保會議決議落實執行不漏接",
                    time_bound=f"於 {plus_7_iso} 前完成確認",
                    is_smart_compliant=True,
                ),
                qcdt=QCDTModel(
                    quality_criteria="每項任務皆具備明確之 Q 驗收條件與 T 佐證規格",
                    cost_budget="0 元 (內部資源/工時)",
                    delivery_milestone=f"{plus_7_iso} 完成責任矩陣發布",
                    truthfulness_req="於系統內完成狀態更新並附上核准紀錄連結",
                ),
            )
        )

    summary = (
        f"本場「{title}」涵蓋 {', '.join(departments)} 等部門，共計濃縮出 {len(decisions)} 項關鍵決策與 "
        f"{len(action_items)} 項結構化待辦事項。所有任務均已納入 RACI 單一當責檢核、SMART 目標分層與 QCD+T 真實性佐證控管。"
    )

    extraction = MeetingExtractionSchema(
        title=title,
        meeting_date=today_iso,
        departments=departments,
        attendees=attendees,
        executive_summary=summary,
        key_decisions=decisions[:6],
        action_items=action_items,
    )
    audited = audit_meeting_extraction(extraction)
    assert isinstance(audited, MeetingExtractionSchema)
    return audited


def extract_meeting_from_transcript(
    transcript: str,
    api_key: str | None = None,
) -> tuple[MeetingExtractionSchema, bool, str]:
    """階段二：透過 Gemini Structured Outputs (Pydantic) 從逐字稿萃取結構化會議記錄.

    回傳:
        (MeetingExtractionSchema, used_real_gemini, status_message)
    """
    cleaned_transcript = (transcript or "").strip()
    if not cleaned_transcript:
        raise ValueError("會議逐字稿內容不可為空白。")

    # 優先檢核是否為「標準輸入格式公版 (xlsx/csv/txt/md)」結構化內容
    template_parsed = try_parse_structured_template_text(cleaned_transcript)
    if template_parsed is not None:
        audited_tpl = audit_meeting_extraction(template_parsed)
        assert isinstance(audited_tpl, MeetingExtractionSchema)
        return (
            audited_tpl,
            True,
            f"🎯 已識別為「標準輸入格式公版」，精準萃取 {len(audited_tpl.action_items)} 項待辦事項並完成 RACI / SMART / QCD+T 治理查核（100% 欄位對齊追蹤看板與催辦中心）！",
        )

    resolved_key = (api_key if api_key is not None else get_gemini_api_key()).strip()
    model_name = get_gemini_model()

    if not resolved_key:
        fallback_result = _fallback_rule_based_extraction(cleaned_transcript)
        return (
            fallback_result,
            False,
            "ℹ️ 目前未設定 `GEMINI_API_KEY`，已透過「本地智慧規則治理引擎」完成 RACI / SMART / QCD+T 結構化萃取（您可隨時於左側邊欄輸入 BYOK 金鑰切換為 Google Gemini 2.5 Flash 深度萃取）。",
        )

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=resolved_key)
        last_exc: Exception | None = None
        for cand_model in get_candidate_gemini_models(model_name):
            try:
                response = client.models.generate_content(
                    model=cand_model,
                    contents=(
                        "請分析以下會議逐字稿，並萃取結構化會議記錄（含標題、高階執行摘要、關鍵決策清單、"
                        "以及結合 RACI / SMART / QCD+T 之待辦事項清單）：\n\n"
                        f"{cleaned_transcript}"
                    ),
                    config=types.GenerateContentConfig(
                        system_instruction=EXTRACTION_SYSTEM_PROMPT,
                        response_mime_type="application/json",
                        response_schema=MeetingExtractionSchema,
                        temperature=0.1,
                    ),
                )

                if getattr(response, "parsed", None) is not None and isinstance(response.parsed, MeetingExtractionSchema):
                    parsed_obj = response.parsed
                else:
                    raw_json = (response.text or "").strip()
                    parsed_obj = MeetingExtractionSchema.model_validate_json(raw_json)

                audited = audit_meeting_extraction(parsed_obj)
                assert isinstance(audited, MeetingExtractionSchema)
                return (
                    audited,
                    True,
                    f"✅ 已透過 Google Gemini ({cand_model}) Structured Outputs 完成 RACI + SMART + QCD+T 結構化萃取與治理稽核！",
                )
            except Exception as inner_exc:
                last_exc = inner_exc
                continue
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("所有候選 Gemini 模型均未回傳有效結果。")
    except Exception as exc:
        fallback_result = _fallback_rule_based_extraction(cleaned_transcript)
        return (
            fallback_result,
            False,
            f"⚠️ Gemini API 呼叫異常（{exc}），已自動降級使用本地智慧規則引擎完成結構化萃取，確保工作流不中斷。",
        )


def audit_action_evidence(
    item: ActionItem,
    evidence_text: str,
    api_key: str | None = None,
) -> tuple[EvidenceAuditResult, bool]:
    """階段三：針對 QCD+T 中提交之『T (成果佐證)』對照『Q (品質驗收條件)』進行 AI 真實性與合規稽核.

    回傳:
        (EvidenceAuditResult, used_real_gemini)
    """
    cleaned_ev = (evidence_text or "").strip()
    if is_vague_or_empty(cleaned_ev) or len(cleaned_ev) < 5:
        return (
            EvidenceAuditResult(
                is_verified=False,
                audit_score=15,
                feedback="❌ 佐證內容過於簡略或為空白。請提供具體可查核之證據（如：PR/文件連結、測試數據、簽核單號或具體交付摘要）。",
            ),
            False,
        )

    resolved_key = (api_key if api_key is not None else get_gemini_api_key()).strip()
    model_name = get_gemini_model()

    if resolved_key:
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=resolved_key)
            prompt = (
                f"待辦事項名稱：{item.task_title}\n"
                f"Q (品質與驗收條件)：{item.qcdt.quality_criteria}\n"
                f"T (原訂可驗證證據要求)：{item.qcdt.truthfulness_req}\n"
                f"執行者實際提交之成果佐證 (Evidence Submitted)：{cleaned_ev}\n\n"
                "請以嚴謹的內部稽核角度，評估實際提交之成果佐證是否具體、真實可查核，且滿足 Q 與 T 之要求。"
            )
            for cand_model in get_candidate_gemini_models(model_name):
                try:
                    response = client.models.generate_content(
                        model=cand_model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=EvidenceAuditResult,
                            temperature=0.1,
                        ),
                    )
                    if getattr(response, "parsed", None) is not None and isinstance(response.parsed, EvidenceAuditResult):
                        return response.parsed, True
                    return EvidenceAuditResult.model_validate_json((response.text or "").strip()), True
                except Exception:
                    continue
        except Exception:
            pass

    # 本地啟發式稽核備援
    has_concrete_proof = any(
        token in cleaned_ev.lower()
        for token in ["http://", "https://", "pr", "#", "報告", "通過", "passed", "100%", "簽核", "完成", "pdf", "doc", "連結", "編號"]
    )
    if has_concrete_proof and len(cleaned_ev) >= 10:
        return (
            EvidenceAuditResult(
                is_verified=True,
                audit_score=90,
                feedback="✅ 稽核通過：提交之佐證包含具體紀錄指標或可查核參照，符合 QCD+T 之 T (Truthfulness/Evidence) 驗收要求。",
            ),
            False,
        )
    return (
        EvidenceAuditResult(
            is_verified=False,
            audit_score=55,
            feedback="⚠️ 佐證尚待補強：建議補充具體的交付物 URL、PR/單據編號或量化驗收數據，以完全滿足 Q (品質驗收條件)。",
        ),
        False,
    )
