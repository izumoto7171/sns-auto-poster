"""
アフィリエイトリンク計測トラッカー (Bitly + Supabase)

【Supabase テーブル作成SQL - 初回のみ実行】
  create table affiliate_links (
    id uuid default gen_random_uuid() primary key,
    original_url text not null,
    bitly_link text unique,
    bitly_id text,
    platform text,
    campaign_id text,
    article_title text,
    click_count int default 0,
    last_used_at timestamp with time zone,   -- クールダウン管理
    created_at timestamp with time zone default timezone('utc'::text, now()),
    updated_at timestamp with time zone default timezone('utc'::text, now())
  );

【既存テーブルへのカラム追加（追加済みなら不要）】
  alter table affiliate_links
    add column if not exists last_used_at timestamp with time zone;

【必要な GitHub Secrets】
  SUPABASE_URL         → SupabaseプロジェクトURL (https://xxxx.supabase.co)
  SUPABASE_SERVICE_KEY → service_role キー（Settings > API）
  BITLY_ACCESS_TOKEN   → Bitly Generic Access Token（bitly.comのアカウント設定から取得）

【使い方】
  from money_agent.affiliate_tracker import (
      generate_tracked_link, update_click_counts,
      get_top_performers, get_worst_performers, mark_as_used,
  )
"""

import os
import sys
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from retry_utils import with_retry


# 環境変数（GitHub Secrets からセット）
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
BITLY_TOKEN  = os.environ.get("BITLY_ACCESS_TOKEN", "")

# クールダウン期間（高パフォーマンスリンクの再利用制限）
COOLDOWN_DAYS = 3


def _is_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY and BITLY_TOKEN)


def _supabase_headers() -> dict:
    return {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "return=representation",
    }


# ── 投稿時: 短縮URL発行 ─────────────────────────────────────

def generate_tracked_link(
    original_url: str,
    platform: str,
    campaign_id: str = "",
    article_title: str = "",
) -> str:
    """
    元URLをBitlyで短縮し、Supabaseに記録して返す。
    Bitly/Supabaseが設定されていない場合は元URLをそのまま返す。

    Args:
        original_url:  追跡対象のURL（はてなブログ記事URLなど）
        platform:      投稿先 ('hatena', 'x', 'note', 'bluesky' など)
        campaign_id:   プログラムID（例: 'mf_kakutei_2026'）
        article_title: 記事タイトル（Supabaseで視認しやすくするため）

    Returns:
        Bitly短縮URL、または失敗時は元のURL
    """
    if not _is_configured():
        print("[Tracker] 環境変数未設定 → 元URLを使用")
        return original_url

    # --- 1. Bitly短縮URL発行 ---
    @with_retry(api="bitly", context=f"shorten:{original_url[:60]}", log_on_giveup=True)
    def _shorten():
        resp = requests.post(
            "https://api-ssl.bitly.com/v4/shorten",
            json={"long_url": original_url},
            headers={
                "Authorization": f"Bearer {BITLY_TOKEN}",
                "Content-Type":  "application/json",
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    data = _shorten()
    if data is None:
        print(f"[Tracker] Bitly発行失敗（全リトライ消耗）→ 元URLを使用")
        return original_url
    bitly_link = data.get("link", "")
    bitly_id   = data.get("id", "")

    # --- 2. Supabaseに保存 ---
    try:
        record = {
            "original_url":  original_url,
            "bitly_link":    bitly_link,
            "bitly_id":      bitly_id,
            "platform":      platform,
            "campaign_id":   campaign_id,
            "article_title": article_title[:200] if article_title else "",
            "click_count":   0,
        }
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/affiliate_links",
            json=record,
            headers=_supabase_headers(),
            timeout=10,
        )
        r.raise_for_status()
        print(f"[Tracker] 計測URL発行: {bitly_link} (platform={platform}, campaign={campaign_id})")
    except Exception as e:
        print(f"[Tracker] Supabase保存エラー: {e}")

    return bitly_link


# ── 分析時: クリック数更新 ──────────────────────────────────

def update_click_counts():
    """
    Supabaseの全レコードに対してBitlyからクリック数を取得・更新する。
    analytics.yml の分析ジョブから呼び出す（1日1回実行推奨）。
    """
    if not _is_configured():
        print("[Tracker] 環境変数未設定 → スキップ")
        return

    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/affiliate_links"
            f"?select=id,bitly_id,click_count",
            headers=_supabase_headers(),
            timeout=10,
        )
        r.raise_for_status()
        records = r.json()
    except Exception as e:
        print(f"[Tracker] Supabase取得エラー: {e}")
        return

    if not records:
        print("[Tracker] 計測対象レコードなし")
        return

    print(f"[Tracker] {len(records)}件のクリック数を更新中...")
    updated = 0

    for rec in records:
        bitly_id = rec.get("bitly_id", "")
        if not bitly_id:
            continue

        @with_retry(api="bitly", context=f"clicks:{bitly_id}", log_on_giveup=False)
        def _get_clicks():
            resp = requests.get(
                f"https://api-ssl.bitly.com/v4/bitlinks/{bitly_id}/clicks/summary",
                params={"unit": "month", "units": 3},
                headers={"Authorization": f"Bearer {BITLY_TOKEN}"},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json().get("total_clicks", 0)

        result = _get_clicks()
        if result is None:
            print(f"[Tracker] Bitlyクリック取得失敗 ({bitly_id})、スキップ")
            continue
        total_clicks = result

        if total_clicks == rec.get("click_count", 0):
            continue

        try:
            requests.patch(
                f"{SUPABASE_URL}/rest/v1/affiliate_links?id=eq.{rec['id']}",
                json={
                    "click_count": total_clicks,
                    "updated_at":  _utcnow(),
                },
                headers=_supabase_headers(),
                timeout=10,
            )
            print(f"  {bitly_id}: {rec['click_count']} → {total_clicks} クリック")
            updated += 1
        except Exception as e:
            print(f"[Tracker] Supabase更新エラー ({bitly_id}): {e}")

    print(f"[Tracker] 更新完了: {updated}/{len(records)}件")


# ── フィードバック用: パフォーマンス取得 ──────────────────────

def get_top_performers(limit: int = 5, cooldown: bool = True) -> list:
    """
    クリック数上位のリンクをSupabaseから取得する。

    Args:
        limit:    取得件数
        cooldown: True のとき、COOLDOWN_DAYS 以内に使用済みのリンクを除外する

    Returns:
        [{"original_url", "bitly_link", "platform", "campaign_id",
          "article_title", "click_count", "last_used_at"}, ...]
    """
    if not (SUPABASE_URL and SUPABASE_KEY):
        return []

    # クールダウンフィルタ: last_used_at が null または N日以上前のみ
    cooldown_filter = ""
    if cooldown:
        threshold = (datetime.now(timezone.utc) - timedelta(days=COOLDOWN_DAYS)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        # null OR threshold以前
        cooldown_filter = f"&or=(last_used_at.is.null,last_used_at.lt.{threshold})"

    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/affiliate_links"
            f"?select=id,original_url,bitly_link,platform,campaign_id,article_title,click_count,last_used_at"
            f"&click_count=gt.0"
            f"&order=click_count.desc"
            f"&limit={limit}"
            f"{cooldown_filter}",
            headers=_supabase_headers(),
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[Tracker] トップ取得エラー: {e}")
        return []


def get_worst_performers(limit: int = 5, min_age_days: int = 3) -> list:
    """
    クリック数が少ない（または0の）リンクをSupabaseから取得する。
    「負けパターン」の学習に使用。

    Args:
        limit:        取得件数
        min_age_days: 投稿後 N 日以上経過したものだけ対象（直後は判断不可のため）

    Returns:
        [{"original_url", "platform", "campaign_id", "article_title",
          "click_count", "created_at"}, ...]
    """
    if not (SUPABASE_URL and SUPABASE_KEY):
        return []

    # N日以上前に作成されたレコードのみ
    age_threshold = (datetime.now(timezone.utc) - timedelta(days=min_age_days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/affiliate_links"
            f"?select=original_url,platform,campaign_id,article_title,click_count,created_at"
            f"&created_at=lt.{age_threshold}"
            f"&order=click_count.asc"
            f"&limit={limit}",
            headers=_supabase_headers(),
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[Tracker] ワースト取得エラー: {e}")
        return []


def mark_as_used(record_id: str):
    """
    フィードバックループでリンクを「使用済み」にしてクールダウンを開始する。
    get_top_performers() の結果を参照して投稿を生成した後に呼び出す。

    Args:
        record_id: affiliate_links テーブルの id (UUID)
    """
    if not (SUPABASE_URL and SUPABASE_KEY):
        return

    try:
        requests.patch(
            f"{SUPABASE_URL}/rest/v1/affiliate_links?id=eq.{record_id}",
            json={"last_used_at": _utcnow()},
            headers=_supabase_headers(),
            timeout=10,
        )
        print(f"[Tracker] クールダウン開始: id={record_id[:8]}... ({COOLDOWN_DAYS}日間)")
    except Exception as e:
        print(f"[Tracker] mark_as_used エラー: {e}")


# ── ユーティリティ ──────────────────────────────────────────

def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


if __name__ == "__main__":
    import sys
    from pathlib import Path

    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

    SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
    SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
    BITLY_TOKEN  = os.environ.get("BITLY_ACCESS_TOKEN", "")

    cmd = sys.argv[1] if len(sys.argv) > 1 else "update"
    if cmd == "update":
        update_click_counts()
    elif cmd == "top":
        for t in get_top_performers():
            cd = f" [CD残{COOLDOWN_DAYS}d]" if t.get("last_used_at") else ""
            print(f"  {t['click_count']}クリック | {t['platform']} | {t.get('article_title','')[:50]}{cd}")
    elif cmd == "worst":
        for t in get_worst_performers():
            print(f"  {t['click_count']}クリック | {t['platform']} | {t.get('article_title','')[:50]}")
