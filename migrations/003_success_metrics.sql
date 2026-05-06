-- ============================================================
-- 003: クリックデータに基づく自動スコアリング用テーブル
-- ============================================================
-- Supabase SQL Editor で実行してください

-- ── success_metrics: ジャンル別の実績重みを保存 ──────────────────
CREATE TABLE IF NOT EXISTS success_metrics (
  id           BIGSERIAL   PRIMARY KEY,
  category     TEXT        NOT NULL UNIQUE,  -- ジャンル/キーワード (例: 'side_hustle', '節約')
  weight_bonus INT         NOT NULL DEFAULT 0,  -- priority に加算するボーナス点 (0〜10)
  click_count  INT         NOT NULL DEFAULT 0,  -- 累計クリック数
  impression_count INT     NOT NULL DEFAULT 0,  -- 累計インプレッション数
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_success_metrics_category
  ON success_metrics (category);

-- ── RLS: service_role のみ操作可能 ──────────────────────────────
ALTER TABLE success_metrics ENABLE ROW LEVEL SECURITY;

-- service_role は RLS をバイパスするため追加ポリシー不要
-- anon / authenticated からのアクセスはデフォルトで拒否される

-- ── 初期データ（全ジャンルを weight_bonus=0 で用意） ──────────────
INSERT INTO success_metrics (category, weight_bonus) VALUES
  ('side_hustle',        0),
  ('freelance',          0),
  ('tax',                0),
  ('accounting',         0),
  ('investment_savings', 0),
  ('nisa',               0),
  ('lifestyle',          0),
  ('productivity',       0),
  ('ai_tools',           0),
  ('blog',               0),
  ('daily_goods',        0),
  ('gadget',             0),
  ('pc',                 0),
  ('cooking_tools',      0),
  ('food',               0),
  ('cleaning',           0),
  ('audio',              0),
  ('smart_home',         0),
  ('kitchen',            0)
ON CONFLICT (category) DO NOTHING;
