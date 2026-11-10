#!/usr/bin/env bash
# ==============================================================================
# AI 會議記錄管理 Web App — 一鍵自動化測試、上傳 GitHub 與觸發 Streamlit Cloud 部署腳本
# 用法: ./scripts/publish_update.sh "您的更新說明 (Commit Message)"
# ==============================================================================
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

COMMIT_MSG="${1:-feat(ui): update UI/UX layout and styling}"

echo "🔍 [Step 1/3] 執行全套自動化測試與資安鐵律掃描 (pytest)..."
./.venv/bin/pytest -c pyproject.toml tests -v

echo "📦 [Step 2/3] 檢查並提交程式碼變更至本地 Git (main 分支)..."
git add .
if git diff --cached --quiet; then
    echo "ℹ️ 目前沒有偵測到新的檔案變更需要提交。"
else
    git commit -m "$COMMIT_MSG"
    echo "✅ 已完成本地提交：$COMMIT_MSG"
fi

echo "🚀 [Step 3/3] 推送更新至 GitHub (ericpwa/ai-meeting-manager) 並自動觸發 Streamlit Cloud 部署..."
if [ -f ".env" ]; then
    GH_TOKEN="$(grep -E '^GITHUB_TOKEN=' .env | cut -d '=' -f2- | tr -d '[:space:]' || true)"
else
    GH_TOKEN=""
fi

if [ -n "$GH_TOKEN" ]; then
    AUTH_B64="$(printf "x-access-token:%s" "$GH_TOKEN" | base64 | tr -d '\n')"
    git -c "http.https://github.com/.extraheader=AUTHORIZATION: basic ${AUTH_B64}" push origin main
else
    git push origin main
fi

echo "🎉 推送完成！Streamlit Community Cloud 將於 5~15 秒內自動熱更新您的線上 Web App！"
