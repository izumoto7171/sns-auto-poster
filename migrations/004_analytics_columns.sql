-- =============================================================
-- posts テーブルにアナリティクス自己学習ループ用カラムを追加
-- =============================================================

-- 投稿メタデータ
ALTER TABLE posts ADD COLUMN IF NOT EXISTS genre          TEXT;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS writing_style  TEXT;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS posted_at_hour INT;

-- X アナリティクス指標（analytics_fetcher.py が24時間後に埋める）
ALTER TABLE posts ADD COLUMN IF NOT EXISTS impression_count INT     DEFAULT 0;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS click_count      INT     DEFAULT 0;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS is_winner        BOOLEAN DEFAULT FALSE;

-- インデックス（winner クエリ・ジャンル別集計用）
CREATE INDEX IF NOT EXISTS idx_posts_is_winner      ON posts (platform, is_winner) WHERE is_winner = TRUE;
CREATE INDEX IF NOT EXISTS idx_posts_genre          ON posts (genre);
CREATE INDEX IF NOT EXISTS idx_posts_analytics      ON posts (platform, success, created_at DESC)
    WHERE impression_count = 0 AND success = TRUE;
