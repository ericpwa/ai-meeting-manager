"""資安金鑰管理與環境組態模組 (Security & BYOK Configuration).

資安鐵律：
1. 嚴禁於代碼中硬編碼 (Hardcode) 任何 API Key 或機敏憑證。
2. 讀取優先順序：
   (a) 使用者於側邊欄動態輸入之 BYOK (Bring Your Own Key) Session 變數
   (b) 系統環境變數 / `.env` 檔案
   (c) Streamlit Cloud Secrets (`st.secrets`)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# 載入專案根目錄下的 .env (若存在)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=False)


def _has_streamlit_context() -> bool:
    """檢查當前執行緒是否處於 Streamlit ScriptRunContext 中，避免非 Streamlit 環境產生警告."""
    try:
        from streamlit.runtime.scriptrunner_utils.script_run_context import get_script_run_ctx

        return get_script_run_ctx(suppress_warning=True) is not None
    except Exception:
        return False


def _get_st_session_state() -> dict[str, Any]:
    """安全取得 Streamlit session_state，於非 Streamlit 執行環境 (如 pytest) 回傳空字典."""
    if not _has_streamlit_context():
        return {}
    try:
        import streamlit as st

        if hasattr(st, "session_state"):
            return st.session_state  # type: ignore[return-value]
    except Exception:
        pass
    return {}


def _get_st_secret(key: str) -> str:
    """安全讀取 st.secrets，若未配置 secrets.toml 不拋出例外."""
    if not _has_streamlit_context():
        return ""
    try:
        import streamlit as st

        secrets_toml = PROJECT_ROOT / ".streamlit" / "secrets.toml"
        home_secrets_toml = Path.home() / ".streamlit" / "secrets.toml"
        if not secrets_toml.exists() and not home_secrets_toml.exists():
            return ""
        if hasattr(st, "secrets") and key in st.secrets:
            val = st.secrets[key]
            return str(val).strip() if val is not None else ""
    except Exception:
        pass
    return ""


def get_config_value(key: str, default: str = "", session_key: str | None = None) -> str:
    """依優先序讀取設定值：Session BYOK -> 環境變數 (.env) -> st.secrets -> default."""
    state = _get_st_session_state()
    lookup_session_key = session_key or f"byok_{key.lower()}"
    if lookup_session_key in state and str(state[lookup_session_key]).strip():
        return str(state[lookup_session_key]).strip()

    env_val = os.getenv(key, "").strip()
    if env_val:
        return env_val

    secret_val = _get_st_secret(key)
    if secret_val:
        return secret_val

    return default


SUPPORTED_GEMINI_MODELS: list[str] = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
]


def is_valid_gemini_key_format(api_key: str) -> bool:
    """檢查 API Key 是否符合 Google AI Studio 標準金鑰格式 (以 AIza 開頭且長度合理)."""
    cleaned = (api_key or "").strip()
    return bool(cleaned.startswith("AIza") and len(cleaned) >= 30)


def get_gemini_api_key() -> str:
    """取得 Google Gemini API Key (支援 .env / st.secrets / Sidebar BYOK)."""
    return get_config_value("GEMINI_API_KEY", default="", session_key="byok_gemini_api_key")


def get_gemini_model() -> str:
    """取得 Gemini 模型名稱，預設使用免費額度支援度最佳之 gemini-2.5-flash."""
    model = get_config_value("GEMINI_MODEL", default="gemini-2.5-flash", session_key="byok_gemini_model")
    return model if model in SUPPORTED_GEMINI_MODELS else SUPPORTED_GEMINI_MODELS[0]


def get_candidate_gemini_models(preferred: str | None = None) -> list[str]:
    """回傳具備自動降級備援順序之 Gemini 模型清單（確保單一模型版本受限時自動切換可用版本）."""
    primary = (preferred or get_gemini_model()).strip()
    if primary not in SUPPORTED_GEMINI_MODELS:
        primary = SUPPORTED_GEMINI_MODELS[0]
    return [primary] + [m for m in SUPPORTED_GEMINI_MODELS if m != primary]


def get_supabase_credentials() -> tuple[str, str]:
    """取得 Supabase (URL, Key) 憑證組合."""
    url = get_config_value("SUPABASE_URL", default="", session_key="byok_supabase_url")
    key = get_config_value("SUPABASE_KEY", default="", session_key="byok_supabase_key")
    return url, key


def is_supabase_configured() -> bool:
    """檢查是否已提供完整之 Supabase URL 與 Key."""
    url, key = get_supabase_credentials()
    return bool(url and key and url.startswith("http"))


def get_workspace_passcode() -> str:
    """取得選用之企業內部工作區通行碼 (若未設定則為空字串，代表直接開放內部共享)."""
    return get_config_value("WORKSPACE_PASSCODE", default="")


def get_webhook_url() -> str:
    """取得選用之跨部門通知 Webhook URL (支援 Slack / Teams / Discord / Generic Webhook，透過 .env / st.secrets / Sidebar BYOK)."""
    return get_config_value("NOTIFICATION_WEBHOOK_URL", default="", session_key="byok_webhook_url")


def get_local_db_path() -> Path:
    """取得本地 SQLite 備援資料庫檔案路徑."""
    rel_path = get_config_value("LOCAL_DB_PATH", default="data/local_meetings.db")
    db_path = Path(rel_path)
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def mask_secret(secret: str) -> str:
    """將機敏金鑰遮罩處理以便安全顯示於 UI 診斷面板."""
    cleaned = (secret or "").strip()
    if not cleaned:
        return "未設定"
    if len(cleaned) <= 8:
        return "****"
    return f"{cleaned[:4]}****...****{cleaned[-4:]}"
