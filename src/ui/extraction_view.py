"""Tab 1：會議輸入端與 AI 結構化萃取視圖 (支援貼上逐字稿、上傳 .txt/.md 與音訊檔兩階段工作流)."""

from __future__ import annotations

import datetime
import streamlit as st

from src.repositories.meeting_repo import MeetingRepository
from src.schemas.models import (
    ActionItem,
    MeetingExtractionSchema,
    QCDTModel,
    RACIModel,
    SMARTGoalModel,
)
from src.services.ai_service import extract_meeting_from_transcript, transcribe_audio
from src.services.governance import audit_meeting_extraction, classify_action_traffic_light
from src.services.meeting_template_service import (
    STANDARD_COLUMNS,
    generate_meeting_template_csv,
    generate_meeting_template_md,
    generate_meeting_template_txt,
    generate_meeting_template_xlsx,
    parse_uploaded_meeting_file,
)

SAMPLE_TRANSCRIPT_TEMPLATE = """會議名稱：2026 Q4 跨部門 AI 客服知識庫上線與資安驗收會議
會議日期：2026-11-10
參與部門：產品部、AI 研發部、客服營運部、資安法遵部
出席人員：陳建宏 (產品總監)、林雅婷 (AI 架構師)、王志明 (客服經理)、張志豪 (資安官)

陳建宏 (產品總監)：各位好，今天我們要拍板 Q4 內部 AI 知識庫檢索系統的上線計畫。我們維持 Phase 1 零元方案原則，使用開源向量庫搭配免費額度模型。
決議一：系統將於下週五 (2026-11-20) 正式對內部客服團隊開放試用，所有跨部門任務必須指定唯一最終當責者 (A)。
決議二：任何任務在標記為完成 (Done) 時，都必須附上 QCD+T 的 T (可驗證成果證據連結)。

林雅婷 (AI 架構師)：RAG 檢索準確率調校這塊由我擔任最終當責者 (A)，我跟劉工程師一起負責執行 (R)，會徵詢客服部王經理 (C)，並告知陳總監 (I)。我們預計在 2026-11-17 前將 Top-3 檢索召回率提升到 90% 以上，這屬於「專案成果 (Project Outcome)」層級，預算 0 元，驗收條件 Q 是通過 100 題黃金測試集驗證，結案時我會附上評測報告連結作為 T 佐證。

王志明 (客服經理)：客服團隊的 50 份常見客訴標準問答集清洗，由我當責 (A)，客服組三位組長負責執行 (R)，在 2026-11-15 前匯入系統，這是「工作任務 (Work Task)」，驗收標準 Q 是零過期條款且格式符合 Markdown 規範，完成後會提供知識庫匯入清單截圖與簽核單號作為 T 佐證。

陳建宏 (產品總監)：另外還有一項「跨部門異常回饋雙週通報機制」，請產品部與客服部共同推進，但目前還沒決定誰是唯一當責人 A，截止日期與具體的佐證格式也還沒定案，請系統先幫我們列進待辦並標示管理缺口！
"""


def render_extraction_view(repo: MeetingRepository) -> None:
    """渲染會議輸入與 AI 結構化萃取工作台."""
    st.markdown("### 🎙️ 新增會議記錄 & AI 結構化治理萃取")
    st.caption(
        "支援 **(1) 直接貼上會議逐字稿或公版文本**、**(2) 上傳「輸入格式公版」或會議檔 (`.xlsx` / `.csv` / `.txt` / `.md`)**、或 **(3) 上傳會議音訊檔（兩階段轉譯＋結構化萃取）**。"
        "AI 引擎將自動依循 **RACI + SMART + QCD+T** 框架精準萃取並無縫傳遞至歷史會議、全域追蹤看板與主動催辦中心。"
    )

    # 新增：標準「輸入格式公版」下載專區 (xlsx / csv / txt / md)
    with st.container(border=True):
        st.markdown("##### 📥 下載「會議輸入格式公版」(`.xlsx` / `.csv` / `.txt` / `.md`) — 讓 AI 100% 精準對齊所有管理欄位")
        st.caption(
            f"📌 **制式公版欄位**：`{'`、`'.join(STANDARD_COLUMNS[:9])}`、`Q/C/T`、`備註/記錄` 等（填寫後上傳或貼上，即可 100% 零失真傳遞至 Tab 2、Tab 3 追蹤看板與 Tab 4 催辦中心）。"
        )
        tpl_c1, tpl_c2, tpl_c3, tpl_c4 = st.columns(4)
        with tpl_c1:
            st.download_button(
                "📊 下載 Excel 輸入公版 (.xlsx)",
                data=generate_meeting_template_xlsx(),
                file_name="meeting_input_template.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="btn_dl_meeting_tpl_xlsx",
            )
        with tpl_c2:
            st.download_button(
                "📄 下載 CSV 輸入公版 (.csv)",
                data=generate_meeting_template_csv(),
                file_name="meeting_input_template.csv",
                mime="text/csv",
                key="btn_dl_meeting_tpl_csv",
            )
        with tpl_c3:
            st.download_button(
                "📝 下載 Markdown 輸入公版 (.md)",
                data=generate_meeting_template_md(),
                file_name="meeting_input_template.md",
                mime="text/markdown",
                key="btn_dl_meeting_tpl_md",
            )
        with tpl_c4:
            st.download_button(
                "📃 下載 TXT 輸入公版 (.txt)",
                data=generate_meeting_template_txt(),
                file_name="meeting_input_template.txt",
                mime="text/plain",
                key="btn_dl_meeting_tpl_txt",
            )

    input_mode = st.radio(
        "選擇會議資料輸入方式",
        options=[
            "📝 貼上會議逐字稿文本",
            "📄 上傳文字/表格檔案 (.xlsx / .csv / .txt / .md)",
            "🎧 上傳音訊檔案 (.mp3 / .wav / .m4a / .ogg) - 兩階段可控轉譯",
        ],
        horizontal=True,
        key="extraction_input_mode",
    )

    source_type = "text"

    if input_mode.startswith("📝"):
        col_btn1, col_btn2, col_btn3 = st.columns([1.4, 1.6, 3])
        with col_btn1:
            if st.button("📋 載入測試逐字稿範本", key="btn_load_demo_transcript"):
                st.session_state["draft_transcript_text"] = SAMPLE_TRANSCRIPT_TEMPLATE
                st.session_state["textarea_direct_transcript"] = SAMPLE_TRANSCRIPT_TEMPLATE
        with col_btn2:
            if st.button("📑 載入標準輸入公版範本", key="btn_load_structured_template"):
                tpl_txt = generate_meeting_template_txt().decode("utf-8")
                st.session_state["draft_transcript_text"] = tpl_txt
                st.session_state["textarea_direct_transcript"] = tpl_txt
        with col_btn3:
            if st.button("🧹 清空文本", key="btn_clear_transcript"):
                st.session_state["draft_transcript_text"] = ""
                st.session_state["textarea_direct_transcript"] = ""
                st.session_state["textarea_file_transcript"] = ""
                st.session_state["textarea_audio_transcript"] = ""
                st.session_state.pop("pre_parsed_template_schema", None)
                st.session_state.pop("latest_extracted_meeting", None)

        if "textarea_direct_transcript" not in st.session_state:
            st.session_state["textarea_direct_transcript"] = st.session_state.get("draft_transcript_text", "")

        transcript_text = st.text_area(
            "會議逐字稿或會議紀錄內容",
            height=240,
            placeholder="請在此貼上會議逐字稿、討論紀錄，或貼上『標準輸入格式公版 (.txt/.md)』內容...",
            key="textarea_direct_transcript",
        )
        st.session_state["draft_transcript_text"] = transcript_text
        source_type = "text"

    elif input_mode.startswith("📄"):
        uploaded_doc = st.file_uploader(
            "上傳會議記錄檔案或『輸入格式公版』(.xlsx / .csv / .txt / .md)",
            type=["xlsx", "csv", "txt", "md"],
            key="uploader_doc_file",
        )
        if uploaded_doc is not None:
            raw_bytes = uploaded_doc.getvalue()
            parsed_text, pre_parsed_schema, parse_msg = parse_uploaded_meeting_file(raw_bytes, uploaded_doc.name)
            if parsed_text:
                st.session_state["draft_transcript_text"] = parsed_text
                st.session_state["textarea_file_transcript"] = parsed_text
                if pre_parsed_schema is not None:
                    st.session_state["pre_parsed_template_schema"] = pre_parsed_schema.model_dump()
                else:
                    st.session_state.pop("pre_parsed_template_schema", None)
                st.success(parse_msg)
            else:
                st.error(parse_msg)

        if "textarea_file_transcript" not in st.session_state:
            st.session_state["textarea_file_transcript"] = st.session_state.get("draft_transcript_text", "")

        transcript_text = st.text_area(
            "檔案內容預覽與微調（可於萃取前直接編修）",
            height=220,
            key="textarea_file_transcript",
        )
        st.session_state["draft_transcript_text"] = transcript_text
        source_type = "file"

    else:
        st.info(
            "💡 **音訊兩階段可控工作流**：\n"
            "1. **Stage 1 (音訊轉譯)**：上傳音訊檔後點擊「轉譯音訊為逐字稿」，由 Gemini 2.5 Flash 多模態引擎免費轉出逐字稿。\n"
            "2. **Stage 2 (校對與結構化萃取)**：檢視或微調轉出之逐字稿（如修正專有名詞或人名），再執行 RACI/SMART/QCD+T 結構化萃取。"
        )
        uploaded_audio = st.file_uploader(
            "上傳會議錄音檔 (.mp3, .wav, .m4a, .ogg, .aac)",
            type=["mp3", "wav", "m4a", "ogg", "aac"],
            key="uploader_audio_file",
        )
        if uploaded_audio is not None:
            st.audio(uploaded_audio)
            if st.button("🎙️ Stage 1：執行 Gemini 音訊轉逐字稿", type="primary", key="btn_run_audio_stt"):
                with st.spinner("正在透過 Gemini 2.5 Flash 多模態引擎轉譯音訊內容..."):
                    audio_bytes = uploaded_audio.getvalue()
                    mime_type = uploaded_audio.type or "audio/mp3"
                    transcribed, _, msg = transcribe_audio(
                        audio_bytes=audio_bytes,
                        mime_type=mime_type,
                        filename=uploaded_audio.name,
                    )
                    if transcribed:
                        st.session_state["draft_transcript_text"] = transcribed
                        st.success(msg)
                    else:
                        st.error(msg)

        transcript_text = st.text_area(
            "Stage 1 音訊轉譯逐字稿結果（可於執行 Stage 2 結構化萃取前人工校對）",
            value=st.session_state.get("draft_transcript_text", ""),
            height=220,
            placeholder="上傳音訊並點擊上方按鈕後，轉譯之逐字稿將顯示於此；您亦可直接貼上或編修文字...",
            key="textarea_audio_transcript",
        )
        st.session_state["draft_transcript_text"] = transcript_text
        source_type = "audio"

    # 執行 AI 結構化萃取按鈕
    if st.button(
        "🚀 執行 AI 結構化萃取 (Gemini Structured Outputs + RACI/SMART/QCD+T 稽核)",
        type="primary",
        key="btn_execute_extraction",
    ):
        current_text = st.session_state.get("draft_transcript_text", "").strip()
        if not current_text:
            st.warning("⚠️ 請先輸入、貼上或上傳會議逐字稿內容（可點擊「📋 載入測試逐字稿範本」快速體驗）。")
        else:
            with st.spinner("🤖 AI 正在萃取會議摘要、決策、待辦事項並執行 RACI / SMART / QCD+T 管理缺口稽核..."):
                extracted, used_gemini, status_msg = extract_meeting_from_transcript(current_text)
                st.session_state["latest_extracted_meeting"] = extracted.model_dump()
                st.session_state["latest_extraction_msg"] = status_msg
                st.session_state["latest_extraction_used_gemini"] = used_gemini
                st.session_state["latest_extraction_source_type"] = source_type

    # 若已有萃取結果，顯示互動預覽、管理缺口警示與儲存表單
    if "latest_extracted_meeting" in st.session_state:
        st.divider()
        msg = st.session_state.get("latest_extraction_msg", "")
        if st.session_state.get("latest_extraction_used_gemini"):
            st.success(msg)
        else:
            st.info(msg)

        extracted_obj = MeetingExtractionSchema.model_validate(st.session_state["latest_extracted_meeting"])
        audited_obj = audit_meeting_extraction(extracted_obj)
        assert isinstance(audited_obj, MeetingExtractionSchema)

        _render_extraction_preview_and_save(
            repo=repo,
            extraction=audited_obj,
            raw_transcript=st.session_state.get("draft_transcript_text", ""),
            source_type=st.session_state.get("latest_extraction_source_type", "text"),
        )


def _render_extraction_preview_and_save(
    repo: MeetingRepository,
    extraction: MeetingExtractionSchema,
    raw_transcript: str,
    source_type: str,
) -> None:
    """渲染 AI 萃取結果預覽、RACI/SMART/QCD+T 缺口檢視與入庫確認介面."""
    st.markdown("### 📊 AI 結構化萃取與管理治理預覽（確認或微調後儲存）")

    # 統計管理缺口
    total_gaps = sum(len(item.governance_gaps) for item in extraction.action_items)
    if total_gaps > 0:
        st.warning(
            f"🚨 **AI 主動治理稽核警示**：在 {len(extraction.action_items)} 項待辦事項中偵測到 **{total_gaps} 項管理缺口** "
            "（例如缺少唯一最終當責者 A、未明確設定期限或未定義可驗證證據 T）。您可於下方直接補齊，或帶缺口標記存入資料庫追蹤。"
        )
    else:
        st.success("✅ **AI 治理稽核通過**：所有待辦事項均具備唯一最終當責者 (A)、SMART 指標與 QCD+T 驗收佐證定義！")

    col_meta1, col_meta2 = st.columns([2, 1])
    with col_meta1:
        edited_title = st.text_input("📌 (a) 會議標題", value=extraction.title, key="edit_ext_title")
    with col_meta2:
        edited_date = st.text_input("📅 會議日期 (YYYY-MM-DD)", value=extraction.meeting_date, key="edit_ext_date")

    col_dep, col_att = st.columns(2)
    with col_dep:
        edited_depts = st.text_input(
            "🏢 參與部門 (以逗號分隔)",
            value=", ".join(extraction.departments),
            key="edit_ext_depts",
        )
    with col_att:
        edited_attendees = st.text_input(
            "👥 出席人員 (以逗號分隔)",
            value=", ".join(extraction.attendees),
            key="edit_ext_attendees",
        )

    org_depts, org_persons = repo.get_org_directory(include_from_meetings=True)
    if org_depts or org_persons:
        st.caption(
            f"💡 **組織名冊快速參照（已與 Tab 2 / Tab 3 / Tab 4 選單同步）** — "
            f"🏢 部門：`{', '.join(org_depts[:10])}` ｜ 👥 人員：`{', '.join(org_persons[:10])}`"
        )

    edited_summary = st.text_area(
        "📝 (b) 高階執行摘要 (Executive Summary)",
        value=extraction.executive_summary,
        height=100,
        key="edit_ext_summary",
    )

    decisions_str = st.text_area(
        "⚖️ (c) 關鍵決策清單 (每行一項決議)",
        value="\n".join(extraction.key_decisions),
        height=100,
        key="edit_ext_decisions",
    )

    st.markdown("#### 🎯 (d) 待辦事項清單 (Action Items — 綁定 RACI + SMART + QCD+T)")

    updated_action_items: list[ActionItem] = []
    smart_levels = [
        "企業目標 (Enterprise Goal)",
        "專案成果 (Project Outcome)",
        "工作任務 (Work Task)",
        "個別活動 (Individual Activity)",
    ]
    status_options = ["Pending", "In Progress", "Blocked", "Done"]

    for idx, item in enumerate(extraction.action_items):
        _, _, combined_light_badge = classify_action_traffic_light(item)
        gap_badge = f" ⚠️ ({len(item.governance_gaps)} 項治理缺口)" if item.governance_gaps else " ✅ (治理合規)"
        with st.expander(
            f"【{item.id}】{combined_light_badge} ｜ {item.task_title} ｜ 當責者(A)：{item.raci.accountable} ｜ 期限：{item.due_date}{gap_badge}",
            expanded=True,
        ):
            if item.governance_gaps:
                for g in item.governance_gaps:
                    st.warning(g)

            c1, c2, c3, c4 = st.columns([3, 2, 2, 1.5])
            with c1:
                t_title = st.text_input("任務名稱", value=item.task_title, key=f"ext_act_title_{idx}")
            with c2:
                t_dept = st.text_input("主責/跨部門", value=item.department, key=f"ext_act_dept_{idx}")
            with c3:
                t_due = st.text_input("截止日 (Due Date)", value=item.due_date, key=f"ext_act_due_{idx}")
            with c4:
                cur_status_idx = status_options.index(item.status) if item.status in status_options else 0
                t_status = st.selectbox("狀態", options=status_options, index=cur_status_idx, key=f"ext_act_status_{idx}")

            st.markdown("**1️⃣ RACI 責任歸屬設定（A 須為唯一最終當責者；R 可多人）**")
            rc1, rc2, rc3, rc4 = st.columns(4)
            with rc1:
                r_acc = st.text_input("A 最終當責者 (唯一)", value=item.raci.accountable, key=f"ext_raci_a_{idx}")
            with rc2:
                r_resp = st.text_input(
                    "R 實際執行者 (逗號分隔)",
                    value=", ".join(item.raci.responsible),
                    key=f"ext_raci_r_{idx}",
                )
            with rc3:
                r_cons = st.text_input(
                    "C 應徵詢者 (逗號分隔)",
                    value=", ".join(item.raci.consulted),
                    key=f"ext_raci_c_{idx}",
                )
            with rc4:
                r_inf = st.text_input(
                    "I 應被告知者 (逗號分隔)",
                    value=", ".join(item.raci.informed),
                    key=f"ext_raci_i_{idx}",
                )

            st.markdown("**2️⃣ SMART 目標層級與衡量標準**")
            sc1, sc2, sc3 = st.columns([1.5, 2, 2])
            with sc1:
                lvl_idx = smart_levels.index(item.smart.hierarchy_level) if item.smart.hierarchy_level in smart_levels else 2
                s_level = st.selectbox(
                    "SMART 層級分類",
                    options=smart_levels,
                    index=lvl_idx,
                    key=f"ext_smart_lvl_{idx}",
                )
            with sc2:
                s_spec = st.text_input("S (具體內容)", value=item.smart.specific, key=f"ext_smart_s_{idx}")
            with sc3:
                s_meas = st.text_input("M (可衡量指標)", value=item.smart.measurable, key=f"ext_smart_m_{idx}")

            st.markdown("**3️⃣ QCD+T 品質、成本、交付與真實性可驗證證據要求**")
            qc1, qc2, qc3, qc4, qc5 = st.columns(5)
            with qc1:
                q_qual = st.text_input("Q (品質與驗收條件)", value=item.qcdt.quality_criteria, key=f"ext_qcdt_q_{idx}")
            with qc2:
                q_cost = st.text_input("C (成本與預算)", value=item.qcdt.cost_budget, key=f"ext_qcdt_c_{idx}")
            with qc3:
                q_deliv = st.text_input("D (交付里程碑)", value=item.qcdt.delivery_milestone, key=f"ext_qcdt_d_{idx}")
            with qc4:
                q_truth = st.text_input("T (可驗證證據要求)", value=item.qcdt.truthfulness_req, key=f"ext_qcdt_t_{idx}")
            with qc5:
                q_ev_sub = st.text_input(
                    "T (已提交成果佐證)",
                    value=item.qcdt.evidence_submitted,
                    key=f"ext_qcdt_ev_sub_{idx}",
                    help="若公版匯入時任務狀態已為 Done，請確保此欄填寫具體成果佐證連結或紀錄。",
                )

            updated_item = ActionItem(
                id=item.id,
                task_title=t_title.strip() or item.task_title,
                department=t_dept.strip() or "跨部門",
                owner=r_acc.strip() or item.owner,
                due_date=t_due.strip() or "待定",
                status=t_status,  # type: ignore[arg-type]
                raci=RACIModel(
                    accountable=r_acc.strip(),
                    responsible=[x.strip() for x in r_resp.split(",") if x.strip()],
                    consulted=[x.strip() for x in r_cons.split(",") if x.strip()],
                    informed=[x.strip() for x in r_inf.split(",") if x.strip()],
                ),
                smart=SMARTGoalModel(
                    hierarchy_level=s_level,  # type: ignore[arg-type]
                    specific=s_spec.strip(),
                    measurable=s_meas.strip(),
                    achievable=item.smart.achievable,
                    relevant=item.smart.relevant,
                    time_bound=t_due.strip(),
                    is_smart_compliant=bool(s_spec.strip() and s_meas.strip() and t_due.strip() != "待定"),
                ),
                qcdt=QCDTModel(
                    quality_criteria=q_qual.strip(),
                    cost_budget=q_cost.strip() or "0 元 (內部資源/工時)",
                    delivery_milestone=q_deliv.strip(),
                    truthfulness_req=q_truth.strip(),
                    evidence_submitted=q_ev_sub.strip(),
                    evidence_verified=bool(item.qcdt.evidence_verified or (t_status == "Done" and q_ev_sub.strip())),
                    evidence_audit_feedback=item.qcdt.evidence_audit_feedback,
                ),
            )
            updated_action_items.append(updated_item)

    if st.button("💾 確認無誤並儲存至資料庫 (meetings 表 + JSONB)", type="primary", key="btn_save_extracted_meeting"):
        final_schema = MeetingExtractionSchema(
            title=edited_title.strip() or extraction.title,
            meeting_date=edited_date.strip() or datetime.date.today().isoformat(),
            departments=[d.strip() for d in edited_depts.split(",") if d.strip()],
            attendees=[a.strip() for a in edited_attendees.split(",") if a.strip()],
            executive_summary=edited_summary.strip(),
            key_decisions=[d.strip() for d in decisions_str.splitlines() if d.strip()],
            action_items=updated_action_items,
        )
        saved_record = repo.save_meeting(
            meeting=final_schema,
            raw_transcript=raw_transcript,
            source_type=source_type,
        )
        st.session_state.pop("latest_extracted_meeting", None)
        st.success(
            f"🎉 會議記錄「{saved_record.title}」已成功存入資料庫（共 {len(saved_record.action_items)} 項 RACI/SMART/QCD+T 任務）！請切換至「📚 歷史會議管理」或「📊 全域行動方案追蹤看板」檢視。"
        )
