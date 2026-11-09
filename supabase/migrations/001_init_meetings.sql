-- ==============================================================================
-- AI 會議記錄管理 Web App (Phase 1 內部共享 -> Phase 2 SaaS 上市演進架構)
-- Supabase PostgreSQL + JSONB + Row Level Security (RLS) 初始化腳本
-- 檔案路徑: supabase/migrations/001_init_meetings.sql
-- ==============================================================================

-- 啟用 UUID 擴充功能
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 建立核心 meetings 資料表
-- 其中 action_items 採用 JSONB 儲存完整的 RACI + SMART + QCD+T 結構化任務陣列
CREATE TABLE IF NOT EXISTS public.meetings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    meeting_date DATE NOT NULL DEFAULT CURRENT_DATE,
    departments JSONB NOT NULL DEFAULT '[]'::jsonb,
    attendees JSONB NOT NULL DEFAULT '[]'::jsonb,
    executive_summary TEXT NOT NULL DEFAULT '',
    key_decisions JSONB NOT NULL DEFAULT '[]'::jsonb,
    action_items JSONB NOT NULL DEFAULT '[]'::jsonb,
    raw_transcript TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL DEFAULT 'text',
    workspace_id TEXT NOT NULL DEFAULT 'internal-default',
    created_by UUID NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 建立效能在地索引與 JSONB GIN 索引（加速跨會議 RACI / SMART / QCD+T 檢索）
CREATE INDEX IF NOT EXISTS idx_meetings_meeting_date ON public.meetings (meeting_date DESC);
CREATE INDEX IF NOT EXISTS idx_meetings_workspace_id ON public.meetings (workspace_id);
CREATE INDEX IF NOT EXISTS idx_meetings_action_items_gin ON public.meetings USING GIN (action_items);
CREATE INDEX IF NOT EXISTS idx_meetings_departments_gin ON public.meetings USING GIN (departments);

-- 自動更新 updated_at 觸發器
CREATE OR REPLACE FUNCTION public.handle_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_meetings_updated_at ON public.meetings;
CREATE TRIGGER trg_meetings_updated_at
    BEFORE UPDATE ON public.meetings
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_updated_at();

-- ==============================================================================
-- Row Level Security (RLS) 資安策略設定
-- ==============================================================================
ALTER TABLE public.meetings ENABLE ROW LEVEL SECURITY;

-- [Phase 1 預設啟用] 企業內部單一共享工作區策略
-- 允許持有專案 Anon/Service Key 之內部應用端進行跨部門會議讀寫與任務更新
DROP POLICY IF EXISTS "Phase1_Internal_Shared_Select" ON public.meetings;
CREATE POLICY "Phase1_Internal_Shared_Select"
    ON public.meetings
    FOR SELECT
    USING (true);

DROP POLICY IF EXISTS "Phase1_Internal_Shared_Insert" ON public.meetings;
CREATE POLICY "Phase1_Internal_Shared_Insert"
    ON public.meetings
    FOR INSERT
    WITH CHECK (true);

DROP POLICY IF EXISTS "Phase1_Internal_Shared_Update" ON public.meetings;
CREATE POLICY "Phase1_Internal_Shared_Update"
    ON public.meetings
    FOR UPDATE
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS "Phase1_Internal_Shared_Delete" ON public.meetings;
CREATE POLICY "Phase1_Internal_Shared_Delete"
    ON public.meetings
    FOR DELETE
    USING (true);

-- ==============================================================================
-- [Phase 2 SaaS 上市預備策略] (升級至多租戶/個人隔離時，停用上方 Phase 1 Policy 並啟用下方策略)
-- ==============================================================================
/*
CREATE POLICY "Phase2_SaaS_Tenant_Isolation"
    ON public.meetings
    FOR ALL
    TO authenticated
    USING (
        created_by = auth.uid()
        OR workspace_id = (auth.jwt() ->> 'workspace_id')
    )
    WITH CHECK (
        created_by = auth.uid()
        OR workspace_id = (auth.jwt() ->> 'workspace_id')
    );
*/
