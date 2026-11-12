"""單元測試：驗證 AI 結構化萃取、音訊兩階段轉譯、T-vs-Q 佐證稽核與「零硬編碼 API Key」資安鐵律."""

from __future__ import annotations

import re
from pathlib import Path

from src.config import (
    PROJECT_ROOT,
    SUPPORTED_GEMINI_MODELS,
    build_genai_clients,
    get_candidate_gemini_models,
    get_gemini_key_type_label,
    is_valid_gemini_key_format,
    mask_secret,
)
from src.schemas.models import ActionItem, QCDTModel, RACIModel
from src.services.ai_service import (
    audit_action_evidence,
    extract_meeting_from_transcript,
    transcribe_audio,
)


def test_offline_smart_extraction_and_audio_workflow() -> None:
    """驗證在未提供 API Key 時，音訊轉譯與結構化萃取具備完整 RACI/SMART/QCD+T 備援輸出."""
    transcript, used_gemini, msg = transcribe_audio(b"fake-audio-bytes", filename="test.mp3", api_key="")
    assert used_gemini is False
    assert len(transcript) > 20
    assert "當責" in transcript

    extracted, used_gemini_ext, ext_msg = extract_meeting_from_transcript(transcript, api_key="")
    assert used_gemini_ext is False
    assert extracted.title
    assert extracted.executive_summary
    assert len(extracted.key_decisions) >= 1
    assert len(extracted.action_items) >= 1
    for item in extracted.action_items:
        assert item.raci.accountable
        assert item.smart.hierarchy_level in {
            "企業目標 (Enterprise Goal)",
            "專案成果 (Project Outcome)",
            "工作任務 (Work Task)",
            "個別活動 (Individual Activity)",
        }


def test_evidence_audit_service() -> None:
    """驗證 QCD+T 之 T vs Q 成果佐證 AI/啟發式稽核功能."""
    item = ActionItem(
        id="ACT-501",
        task_title="部署正式環境 API",
        raci=RACIModel(accountable="林工程師", responsible=["林工程師"]),
        qcdt=QCDTModel(
            quality_criteria="P95 延遲低於 500ms",
            truthfulness_req="提供壓測報告連結與 PR 編號",
        ),
    )

    res_fail, _ = audit_action_evidence(item, "做好了", api_key="")
    assert res_fail.is_verified is False

    res_pass, _ = audit_action_evidence(
        item,
        "已完成部署，PR #108 合併，壓測報告 https://metrics.internal/p95 顯示延遲 320ms (100% 通過)",
        api_key="",
    )
    assert res_pass.is_verified is True
    assert res_pass.audit_score >= 85


def test_zero_hardcoded_api_keys_security_scan() -> None:
    """資安鐵律掃描：掃描專案所有 .py 與 .sql 檔案，確保絕無寫死任何真實 Google Gemini 或 Supabase 私密金鑰."""
    # Google API Key 格式: AIzaSy 後接 33 個字元
    gemini_key_pattern = re.compile(r"AIzaSy[A-Za-z0-9_\-]{33}")
    # JWT Service Role / Anon Key 格式: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
    jwt_key_pattern = re.compile(r"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}")

    scanned_files = 0
    for path in PROJECT_ROOT.rglob("*"):
        if ".venv" in path.parts or ".git" in path.parts or "__pycache__" in path.parts:
            continue
        # .env 與 .streamlit/secrets.toml 為被 .gitignore 排除之本地機密檔，不屬於入庫原始碼
        if path.name in {".env", "secrets.toml"}:
            continue
        if path.is_file() and path.suffix in {".py", ".sql", ".toml", ".md", ".example"}:
            content = path.read_text(encoding="utf-8", errors="ignore")
            assert not gemini_key_pattern.search(content), f"在 {path} 偵測到疑似硬編碼之 Gemini API Key!"
            assert not jwt_key_pattern.search(content), f"在 {path} 偵測到疑似硬編碼之 Supabase JWT Key!"
            scanned_files += 1

    assert scanned_files >= 8
    assert mask_secret("AIzaSyDummyKeyForMaskTesting123456789") == "AIza****...****6789"


def test_gemini_model_versions_and_fallback_chain() -> None:
    """驗證 Gemini 模型版本清單與自動降級備援鏈完整性."""
    assert "gemini-2.5-flash" in SUPPORTED_GEMINI_MODELS
    assert "gemini-2.5-pro" in SUPPORTED_GEMINI_MODELS
    assert "gemini-2.0-flash" in SUPPORTED_GEMINI_MODELS

    chain = get_candidate_gemini_models("gemini-2.5-pro")
    assert chain[0] == "gemini-2.5-pro"
    assert set(chain) == set(SUPPORTED_GEMINI_MODELS)

    # 未知模型名稱應自動降級回預設首選 gemini-2.5-flash
    fallback_chain = get_candidate_gemini_models("unknown-model-v0")
    assert fallback_chain[0] == "gemini-2.5-flash"

    assert is_valid_gemini_key_format("AIzaSyDummyKeyForMaskTesting123456789") is True
    assert is_valid_gemini_key_format("AlzaSyDummyKeyForMaskTesting123456789") is True
    assert is_valid_gemini_key_format("AQ.DummyAuthKeyForUnitTesting1234567890") is True
    assert is_valid_gemini_key_format("invalid-short-key") is False

    assert "AQ" in get_gemini_key_type_label("AQ.DummyAuthKeyForUnitTesting1234567890")
    assert "AIza" in get_gemini_key_type_label("AIzaSyDummyKeyForMaskTesting123456789")
    assert "AIza" in get_gemini_key_type_label("AlzaSyDummyKeyForMaskTesting123456789")

    aq_clients = build_genai_clients("AQ.DummyAuthKeyForUnitTesting1234567890")
    assert len(aq_clients) >= 2
    assert aq_clients[0][1] == "Vertex-Express(AQ)"

    aiza_clients = build_genai_clients("AIzaSyDummyKeyForMaskTesting123456789")
    assert len(aiza_clients) >= 2
    assert aiza_clients[0][1] == "Gemini-API(AIza)"
