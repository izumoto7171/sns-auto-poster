-- =============================================================
-- affiliate_programs にストーリー型プロンプトカラムを追加
-- =============================================================

-- 各プログラム固有の投稿プロンプト（@single_life_lab スタイル: 悩み→解決→QOL向上）
ALTER TABLE affiliate_programs ADD COLUMN IF NOT EXISTS content_prompt    TEXT;
ALTER TABLE affiliate_programs ADD COLUMN IF NOT EXISTS prompt_updated_at TIMESTAMPTZ;
