-- =============================================================
-- SNSアフィリエイトシステム Supabase スキーマ
-- JSON競合排除・並列実行安全のためのDB移行
-- =============================================================

-- ─────────────────────────────────────────
-- 1. posts — X / Bluesky / はてなブログ / note / 楽天ルーム 投稿ログ
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS posts (
    id            BIGSERIAL PRIMARY KEY,
    platform      TEXT        NOT NULL,           -- 'x' | 'bluesky' | 'hatena' | 'note' | 'rakuten'
    post_type     TEXT,                           -- 'amazon_thread' | 'useful' | 'empathy' | ...
    label         TEXT,
    chars         INT,
    text          TEXT,
    success       BOOLEAN     DEFAULT FALSE,
    mode          TEXT        DEFAULT 'live',      -- 'live' | 'dry_run' | 'live_thread'
    has_image     BOOLEAN     DEFAULT FALSE,
    url           TEXT,
    tweet1_id     TEXT,
    tweet2_id     TEXT,
    tweet3_id     TEXT,
    thread_url    TEXT,
    dry_run       BOOLEAN     DEFAULT FALSE,
    error_message TEXT,                           -- 投稿失敗時のエラー詳細（HTTP status + body）
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- 既存テーブルへのカラム追加（初回実行後の環境向け）
ALTER TABLE posts ADD COLUMN IF NOT EXISTS error_message    TEXT;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS genre            TEXT;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS writing_style    TEXT;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS posted_at_hour   INT;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS impression_count INT     DEFAULT 0;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS click_count      INT     DEFAULT 0;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS is_winner        BOOLEAN DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_posts_platform    ON posts (platform);
CREATE INDEX IF NOT EXISTS idx_posts_created_at  ON posts (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_posts_success     ON posts (platform, success);
CREATE INDEX IF NOT EXISTS idx_posts_is_winner   ON posts (platform, is_winner) WHERE is_winner = TRUE;
CREATE INDEX IF NOT EXISTS idx_posts_genre       ON posts (genre);
CREATE INDEX IF NOT EXISTS idx_posts_analytics   ON posts (platform, success, created_at DESC)
    WHERE impression_count = 0 AND success = TRUE;


-- ─────────────────────────────────────────
-- 2. amazon_products — Amazon商品 日次キャッシュ（毎日5件）
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS amazon_products (
    id            BIGSERIAL PRIMARY KEY,
    data          JSONB       NOT NULL,            -- 商品データ全体（product_rotator が生成した dict）
    intent_score  INT         DEFAULT 50,
    context_boost INT         DEFAULT 0,
    is_active     BOOLEAN     DEFAULT TRUE,        -- 当日分のみ TRUE
    fetched_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_amazon_products_active  ON amazon_products (is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_amazon_products_score   ON amazon_products (intent_score DESC) WHERE is_active = TRUE;


-- ─────────────────────────────────────────
-- 3. keyword_history — Amazon商品キーワード使用履歴（過去14日除外用）
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS keyword_history (
    id          BIGSERIAL PRIMARY KEY,
    keywords    JSONB       NOT NULL DEFAULT '[]', -- list[str] 当日使用キーワード群
    month       INT,
    season      TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_keyword_history_created_at ON keyword_history (created_at DESC);


-- ─────────────────────────────────────────
-- 4. static_products — Amazon商品静的マスタ（季節外れ差替え対象）
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS static_products (
    id          BIGSERIAL PRIMARY KEY,
    data        JSONB       NOT NULL,              -- 商品データ全体
    is_active   BOOLEAN     DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_static_products_active ON static_products (is_active) WHERE is_active = TRUE;


-- ─────────────────────────────────────────
-- 5. analytics_insights — SNS分析フィードバック（単一行 upsert）
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS analytics_insights (
    id          INT         PRIMARY KEY DEFAULT 1,
    data        JSONB       NOT NULL DEFAULT '{}', -- feedback_insights.json 全体
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- 初期行を挿入（存在しない場合）
INSERT INTO analytics_insights (id, data)
VALUES (1, '{}')
ON CONFLICT (id) DO NOTHING;


-- ─────────────────────────────────────────
-- 6. analytics_history — SNS投稿メトリクス累積（最大500件保持）
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS analytics_history (
    id              TEXT        PRIMARY KEY,        -- 'x_{tweet_id}' | 'bsky_{uri}'
    platform        TEXT        NOT NULL,
    text            TEXT,
    post_created_at TIMESTAMPTZ,
    likes           INT         DEFAULT 0,
    retweets        INT         DEFAULT 0,
    replies         INT         DEFAULT 0,
    impressions     INT         DEFAULT 0,
    reposts         INT         DEFAULT 0,
    score           FLOAT       DEFAULT 0,
    collected_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_analytics_history_platform ON analytics_history (platform);
CREATE INDEX IF NOT EXISTS idx_analytics_history_score    ON analytics_history (score DESC);
CREATE INDEX IF NOT EXISTS idx_analytics_history_collected ON analytics_history (collected_at DESC);


-- ─────────────────────────────────────────
-- 7. a8_processed — A8.net 処理済みプログラム（重複実行防止）
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS a8_processed (
    id           BIGSERIAL PRIMARY KEY,
    program_id   TEXT        NOT NULL,
    program_type TEXT        NOT NULL DEFAULT 'new', -- 'new' | 'approved'
    processed_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (program_id, program_type)
);

CREATE INDEX IF NOT EXISTS idx_a8_processed_type ON a8_processed (program_type);


-- ─────────────────────────────────────────
-- 8. affiliate_programs — A8.net / 楽天 / Amazon アフィリリンク管理
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS affiliate_programs (
    id          BIGSERIAL   PRIMARY KEY,
    program_id  TEXT        NOT NULL UNIQUE,        -- 'freee_accounting' etc.
    url         TEXT,
    status      TEXT        DEFAULT 'pending',       -- 'active' | 'pending' | 'inactive'
    note        TEXT,
    updated_at  TIMESTAMPTZ DEFAULT NOW(),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);


-- ─────────────────────────────────────────
-- 9. revenue_records — 収益トラッカー
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS revenue_records (
    id                         BIGSERIAL PRIMARY KEY,
    date                       DATE        NOT NULL,
    time                       TEXT,
    platform                   TEXT,                -- 'hatena' | 'note' | 'x' | 'bluesky'
    title                      TEXT,
    keyword                    TEXT,
    category                   TEXT,
    affiliate_count            INT         DEFAULT 0,
    url                        TEXT,
    estimated_pv_30days        INT         DEFAULT 0,
    estimated_revenue_30days   INT         DEFAULT 0,
    created_at                 TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_revenue_records_date     ON revenue_records (date DESC);
CREATE INDEX IF NOT EXISTS idx_revenue_records_platform ON revenue_records (platform);


-- ─────────────────────────────────────────
-- 10. agent_state — money_agent の進捗状態（単一行 upsert）
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agent_state (
    id          INT         PRIMARY KEY DEFAULT 1,
    data        JSONB       NOT NULL DEFAULT '{}',
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO agent_state (id, data)
VALUES (1, '{"total_articles": 0, "today_articles": 0, "last_run": ""}')
ON CONFLICT (id) DO NOTHING;


-- ─────────────────────────────────────────
-- Row Level Security（必要に応じて有効化）
-- service_key を使う場合は RLS を bypass するため不要だが、
-- anon_key を使う場合は以下を有効化してポリシーを設定する
-- ─────────────────────────────────────────
-- ALTER TABLE posts              ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE amazon_products    ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE keyword_history    ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE static_products    ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE analytics_insights ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE analytics_history  ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE a8_processed       ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE affiliate_programs ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE revenue_records    ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE agent_state        ENABLE ROW LEVEL SECURITY;
