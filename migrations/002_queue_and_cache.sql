-- ============================================================
-- 002: Geminiクォータ節約のためのキューとコンテンツキャッシュ
-- ============================================================
-- Supabase SQL Editor で実行してください

-- ── pending_tasks: クローラーが見つけた案件を一時保存 ──────────
CREATE TABLE IF NOT EXISTS pending_tasks (
  id            BIGSERIAL PRIMARY KEY,
  source        TEXT        NOT NULL,                -- 'amazon' | 'a8' | 'rakuten'
  product_key   TEXT        NOT NULL,                -- 重複防止用ユニークキー (ASIN/ins_id/item_code)
  raw_data      JSONB       NOT NULL,
  status        TEXT        NOT NULL DEFAULT 'pending', -- 'pending'|'processing'|'done'|'failed'
  priority      INT         NOT NULL DEFAULT 0,      -- 高いほど先に処理
  post_type     TEXT        NOT NULL DEFAULT 'x',    -- 'x' | 'hatena' | 'bluesky'
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  processed_at  TIMESTAMPTZ,
  error_msg     TEXT,
  UNIQUE (source, product_key, post_type)
);

CREATE INDEX IF NOT EXISTS idx_pending_tasks_status
  ON pending_tasks (status, priority DESC, created_at ASC);

-- ── content_cache: Geminiが生成した投稿文を保存・再利用 ────────
CREATE TABLE IF NOT EXISTS content_cache (
  id             BIGSERIAL PRIMARY KEY,
  product_key    TEXT        NOT NULL,
  source         TEXT        NOT NULL,   -- 'amazon' | 'a8' | 'rakuten'
  post_type      TEXT        NOT NULL,   -- 'x' | 'hatena' | 'bluesky'
  generated_text TEXT        NOT NULL,
  metadata       JSONB,                  -- 商品名・URL・価格等
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_used_at   TIMESTAMPTZ,
  use_count      INT         NOT NULL DEFAULT 0,
  UNIQUE (product_key, post_type)
);

CREATE INDEX IF NOT EXISTS idx_content_cache_lookup
  ON content_cache (product_key, post_type, created_at DESC);

-- ── RLS: service_role キーでのみ操作（GitHub Actions は service_role を使用）
ALTER TABLE pending_tasks  ENABLE ROW LEVEL SECURITY;
ALTER TABLE content_cache  ENABLE ROW LEVEL SECURITY;

-- service_role は RLS をバイパスするため追加ポリシー不要
-- anon / authenticated からのアクセスはデフォルトで拒否される
