# 🛡️ AI 會議記錄管理 Web App (RACI · SMART · QCD+T 企業治理中樞)

本專案為以 **Antigravity 規格驅動開發 (Spec-Driven Development, SDD)** 自動化閉環建置之企業級 **「AI 會議記錄管理 Web App」**。
支援 **Phase 1 企業內部 0 元無成本試運行**，並具備 Clean Architecture 分層設計以無縫演進至 **Phase 2 B2B SaaS 上市銷售**。

---

## ✨ 核心管理框架與系統特色

1. **三大管理框架深度治理 (`src/schemas/models.py`, `src/services/governance.py`)**
   - **RACI 責任歸屬矩陣**：強制每項待辦事項須有且只有一名 **最終當責者 (Accountable, A)**，支援多名 **實際執行者 (Responsible, R)**、**應徵詢者 (Consulted, C)** 與 **應被告知者 (Informed, I)**。跨部門任務若未明確指定唯一當責者 `A`，系統自動觸發「管理缺口警示」。
   - **SMART 四階目標分層與五維檢核**：嚴格區分 **「企業目標 (Enterprise Goal)」**、**「專案成果 (Project Outcome)」**、**「工作任務 (Work Task)」** 與 **「個別活動 (Individual Activity)」**，不可混為一談。
   - **QCD+T 自訂擴充管理框架**：
     - **Q (Quality)**：品質與驗收條件
     - **C (Cost/Budget)**：成本與預算（含 0 元方案或內部工時配置）
     - **D (Delivery)**：交付期限與里程碑
     - **T (Truthfulness/Evidence)**：進度、狀態及成果的真實性與可驗證證據。當任務狀態勾選為 `Done (已完成)` 時，系統強制檢核是否已提交可驗證之成果佐證，並提供 **AI 佐證對照品質條件 (T vs Q) 自動稽核**。

2. **資安鐵律與 BYOK 動態金鑰注入 (`src/config.py`, `src/ui/sidebar.py`)**
   - 嚴格禁止將任何 API Key 寫死於程式碼中（內建自動化正規表達式掃描測試驗證）。
   - 金鑰讀取優先序：`側邊欄 BYOK (Session 記憶體)` ➔ `.env 環境變數` ➔ `st.secrets (Streamlit Cloud)`。

3. **雙模資料持久化引擎 (`src/repositories/meeting_repo.py`)**
   - **Supabase Cloud 模式**：設定 `SUPABASE_URL` 與 `SUPABASE_KEY` 後自動連線 Supabase `meetings` 資料表（`action_items` 採用 `JSONB` 格式儲存並建立 GIN 索引與 RLS 策略）。
   - **Local SQLite 自動備援模式**：未設定雲端憑證時自動切換至本地 `data/local_meetings.db`，確保零成本開箱即用與 100% 無人值守自動化測試。

---

## 🚀 快速啟動指南 (Quick Start)

### 1. 啟動本地應用程式
```bash
cd /Users/wenanpan/.gemini/antigravity/scratch/ai-meeting-manager
./.venv/bin/streamlit run app.py
```

### 2. 執行全套自動化測試與資安稽核
```bash
cd /Users/wenanpan/.gemini/antigravity/scratch/ai-meeting-manager
./.venv/bin/pytest tests -v
```

### 3. 部署至 Supabase + Streamlit Community Cloud (0 元方案)
1. 於 Supabase SQL Editor 執行 [`supabase/migrations/001_init_meetings.sql`](supabase/migrations/001_init_meetings.sql) 完成 `meetings` 表、JSONB 索引與 RLS 建置。
2. 將本專案推送至 GitHub，並於 Streamlit Community Cloud 綁定儲存庫（主程式路徑設為 `app.py`）。
3. 於 Streamlit Cloud `Settings -> Secrets` 填入 `GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`，或直接透過介面左側邊欄之 **BYOK 金鑰輸入框** 動態注入使用。
