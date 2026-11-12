# 🤝 AI 會議記錄管理 Web App — 專案完整交接文件 (Project Handoff)

- **交接產生時間**：2026-11-12
- **原對話 ID**：`ea05ccd2-160e-4dba-aecc-8cb075fb3501`
- **本地專案絕對路徑**：`/Users/wenanpan/.gemini/antigravity/scratch/ai-meeting-manager`
- **Git 遠端儲存庫**：`https://github.com/ericpwa/ai-meeting-manager.git`（分支：`main`，最新同步 Commit：`e5e7a67`）
- **Streamlit Cloud 一鍵部署網址**：`https://share.streamlit.io/deploy?repository=ericpwa/ai-meeting-manager&branch=main&mainModule=app.py`
- **Supabase 雲端專案端點**：`https://dkonpghcvdlquuecuyss.supabase.co`（資料表 `public.meetings` + `JSONB` + `RLS` 已建置並預載 3 場跨部門範例會議）

---

## 1. 🎯 專案核心定位與商業演進藍圖
1. **階段一（Phase 1 — 目前已完成並上線）**：
   - 供企業內部跨部門免費使用（**0 元方案架構**：Streamlit Community Cloud + Supabase Free Tier + Google Gemini 免費額度 + 本地 SQLite 自動備援），累積真實使用者經驗並持續修正迭代。
2. **階段二（Phase 2 — 終極目標）**：
   - 轉型為 B2B SaaS 多租戶訂閱制上市銷售（資料庫已預留 `workspace_id` 與 RLS 多租戶擴充結構）。
3. **三大內建管理治理鐵律（核心差異化價值）**：
   - **RACI 單一當責制**：強制每項待辦事項須有且僅有 **1 位最終當責者 (`A - Accountable`)**（跨部門任務亦不得推諉或多人共同當責），並區分實際執行者 (`R`)、應徵詢者 (`C`)、應被告知者 (`I`)。
   - **SMART 四階目標分類**：嚴格區分 `企業目標 (Enterprise Goal)`、`專案成果 (Project Outcome)`、`工作任務 (Work Task)`、`個別活動 (Individual Activity)` 四階層級。
   - **QCD+T 自訂管理擴充框架**：涵蓋品質驗收條件 (`Q`)、成本預算 (`C`，支援 0 元內部工時方案)、交付期限 (`D`) 與 **真實性可驗證成果佐證 (`T - Truthfulness/Evidence`)**。將任務標記為 `Done` 時，**必須填寫具體可查核之 `T` 成果佐證**，否則系統主動攔截並拒絕結案。

---

## 2. 🏗️ 技術架構與檔案地圖 (Clean Architecture)

```text
/Users/wenanpan/.gemini/antigravity/scratch/ai-meeting-manager/
├── app.py                                  # 主程式入口：全域 KPI 指標卡 + 六大功能頁籤 (Tab 1 ~ Tab 6)
├── requirements.txt / pyproject.toml       # Python 3.12 依賴清單 (streamlit, google-genai, supabase, pydantic, pandas, openpyxl, pytest)
├── USER_GUIDE.md                           # 超白話（小學生也能懂）離線版操作說明書
├── HANDOFF.md                              # 本交接文件（供新對話一秒銜接）
├── scripts/
│   └── publish_update.sh                   # 一鍵執行 pytest 測試 + git commit + 推送 GitHub 自動部署腳本
├── supabase/
│   └── migrations/001_init_meetings.sql    # Supabase PostgreSQL + JSONB + GIN Index + RLS 建表腳本
├── src/
│   ├── config.py                           # 資安與 BYOK 組態：同時支援 AQ 授權金鑰與 AIza/Alza 流量金鑰、多模型備援鏈
│   ├── schemas/
│   │   └── models.py                       # Pydantic V2 資料模型 (RACIModel, SMARTGoalModel, QCDTModel, ActionItem, MeetingRecord)
│   ├── services/
│   │   ├── governance.py                   # 主動治理稽核引擎 + 四色燈號預警分類器 (classify_action_traffic_light)
│   │   ├── ai_service.py                   # Gemini 音訊轉譯 (Stage 1)、Structured Outputs 萃取 (Stage 2)、T-vs-Q 佐證稽核 (Stage 3)
│   │   ├── meeting_template_service.py     # 17 欄「會議輸入格式公版」(.xlsx/.csv/.md/.txt) 產生器與零失真解析引擎
│   │   ├── org_directory_service.py        # 「部門名稱」與「與會人員」(.xlsx/.csv/.md) 批量匯入解析與範本產生器
│   │   └── notification_service.py         # 跨部門主動催辦引擎 (Email / Slack / Teams / LINE 文案產生 + AI 潤飾 + Webhook 推播)
│   ├── repositories/
│   │   └── meeting_repo.py                 # 雙模儲存庫：Supabase Cloud 優先 + Local SQLite 自動無縫降級備援 + 組織名冊持久化
│   └── ui/
│       ├── theme.py                        # 企業視覺主題：INPOWER 銓泰環能科技 SVG Logo、藍白灰玻璃擬態、霓虹四色燈號與結構化徽章
│       ├── sidebar.py                      # 左側邊欄：BYOK 金鑰注入 (AQ/AIza/Alza)、模組化狀態卡、部門/人員名冊批量匯入、範例載入
│       ├── extraction_view.py              # Tab 1：新增會議 & AI 結構化萃取（含下載/上傳 .xlsx/.csv/.txt/.md 輸入格式公版）
│       ├── meetings_view.py                # Tab 2：歷史會議檢索、四色燈號卡片、A/R 更新、T 成果佐證閉環與 AI 稽核
│       ├── tracker_view.py                 # Tab 3：全域行動方案追蹤看板（批量匯入名冊對應 A/R/部門選單 ＋ 紅/黃/藍/綠四色燈號預警）
│       ├── notification_view.py            # Tab 4：跨部門主動催辦與通知中心（依當責者 A 分群 ＋ 多通道文案 ＋ Webhook 推播）
│       ├── deployment_view.py              # Tab 5：雲端部署精靈 & 6 項線上即時系統自我查核中心
│       └── guide_view.py                   # Tab 6：內建新手教學與操作指南分頁
└── tests/                                  # 17 項自動化單元測試與 Streamlit AppTest E2E 測試 (100% PASSED)
    ├── test_schemas_and_governance.py
    ├── test_repository.py
    ├── test_ai_and_security.py
    ├── test_notifications.py
    ├── test_org_and_traffic_lights.py
    └── test_streamlit_e2e.py
```

---

## 3. ✅ 已完成之重要功能與修復紀錄（截至 Commit `e5e7a67`）

1. **🔑 Google API Key 雙制式相容（`AQ` 授權金鑰 ＋ `AIza` / `Alza` 流量金鑰）**：
   - 於 [`src/config.py`](file:///Users/wenanpan/.gemini/antigravity/scratch/ai-meeting-manager/src/config.py) 實作 `is_valid_gemini_key_format()` 與 `build_genai_clients()`：
     - 當輸入 **`AQ` 開頭授權金鑰**時，自動優先以 `genai.Client(api_key=..., vertexai=True)` 路由至 Vertex AI Express 授權端點（`aiplatform.googleapis.com`），並以 `vertexai=False` 為備援。
     - 當輸入 **`AIza` 或 `Alza` 開頭流量金鑰**時，自動優先以 `genai.Client(api_key=..., vertexai=False)` 路由至 Gemini Developer API 端點（`generativelanguage.googleapis.com`），且若首字誤植為小寫 `l` (`Alza`) 會自動修正為大寫 `I` (`AIza`)。
2. **🤖 Gemini 多模型版本自動降級備援鏈**：
   - 支援 `["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro", "gemini-2.0-flash"]` 依序自動備援；若未填金鑰或網路受限，則自動切換至「本地智慧規則治理引擎」，確保系統 100% 永不崩潰。
3. **📥 Tab 1「會議輸入格式公版」(`.xlsx` / `.csv` / `.md` / `.txt`) 直通車**：
   - 使用者可從 Tab 1 一鍵下載 4 種格式的 17 欄制式公版（含會議日期、來源會議、任務編號、待辦事項名稱、執行狀態、主責/跨部門、A、R、C、I、SMART 層級、截止日 D、Q、C、T 要求、T 已提交佐證、備註/記錄），填寫後上傳即可 **100% 零失真解析** 並同步至 Tab 2、Tab 3、Tab 4。
4. **👥 批量匯入「部門名稱」與「與會人員」(`.xlsx` / `.csv` / `.md`)**：
   - 可於左側邊欄或 Tab 3 批量上傳名冊，自動存入資料庫（Record ID `00000000-0000-0000-0000-000000000099`），並自動對應 **「👑 當責者 (A) 篩選」**、**「🛠️ 執行者 (R) 篩選」** 與 **「🏢 部門篩選」** 下拉選單。
5. **🚦 四色「燈號預警」系統（紅/黃/藍/綠燈）**：
   - 統一於 Tab 1、Tab 2、Tab 3、Tab 4 顯示並連動篩選：
     - **🔴 紅燈**：`🚨 逾期未完成`、`🛑 執行受阻 (Blocked)`
     - **🟡 黃燈**：`⚠️ 治理缺口`、`⏳ 即將到期`（3 日內）
     - **🔵 藍燈**：`⏳ 未完成/進行中`
     - **🟢 綠燈**：`✅ 已完成 (Done)`
6. **🎨 INPOWER 銓泰環能科技企業級 UI 美化升級（[`src/ui/theme.py`](file:///Users/wenanpan/.gemini/antigravity/scratch/ai-meeting-manager/src/ui/theme.py)）**：
   - 融合 **INPOWER 銓泰環能科技** 企業 Logo 與制服三層波浪色系（純白、深海藏青 `#162238`、寶石鋼藍 `#1E4E79`、金屬銀灰 `#94A3B8`）。
   - 頂部漸層商務橫幅 (Hero Header Card)、膠囊分段式六大頁籤導覽列 (Segmented Pill Tabs)、圓角立體色帶 KPI 指標卡、霓虹微光四色燈號預警列、待辦事項左側四色燈條與 RACI/SMART/QCD+T 結構化彩色膠囊徽章、以及側邊欄模組化玻璃擬態狀態卡。

---

## 4. 🔐 資安隔離與本地環境狀態（切勿外洩或提交至 Git）
- 本地環境變數與憑證已安全儲存於 `/Users/wenanpan/.gemini/antigravity/scratch/ai-meeting-manager/.env` 及 `.streamlit/secrets.toml`（兩者皆已寫入 `.gitignore` 嚴格排除於 Git 之外，且有 `test_zero_hardcoded_api_keys_security_scan` 自動化測試把關）。
- 本地虛擬環境位於 `/Users/wenanpan/.gemini/antigravity/scratch/ai-meeting-manager/.venv`（Python 3.12.14）。
- 常用驗證與部署指令：
  - 執行全套自動化測試：`/Users/wenanpan/.gemini/antigravity/scratch/ai-meeting-manager/.venv/bin/pytest -v /Users/wenanpan/.gemini/antigravity/scratch/ai-meeting-manager/tests`
  - 推送更新至 GitHub：執行 `/Users/wenanpan/.gemini/antigravity/brain/ea05ccd2-160e-4dba-aecc-8cb075fb3501/scratch/deploy_github.py` 或 `bash scripts/publish_update.sh "commit message"`
