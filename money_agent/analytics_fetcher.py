"""
analytics_fetcher.py — X アナリティクス実績回収スクリプト

投稿から 24〜48 時間経過したツイートのインプレッション数を取得し、
Supabase の posts レコードを更新する。
同ジャンルの過去平均の 1.5 倍を超えた投稿には is_winner=True を付与する。

使い方:
  python3 money_agent/analytics_fetcher.py
"""

import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from db_client import db


# is_winner と判定するインプレッション倍率の閾値
WINNER_MULTIPLIER = 1.5

# ジャンル平均が取れない場合のフォールバック閾値（インプレッション絶対値）
WINNER_FALLBACK_IMPRESSIONS = 200


def _build_tweepy_client():
    """tweepy.Client を構築して返す。認証情報が不足している場合は None。"""
    try:
        import tweepy
        bearer_token       = os.getenv("X_BEARER_TOKEN")
        consumer_key       = os.getenv("X_API_KEY")
        consumer_secret    = os.getenv("X_API_SECRET")
        access_token       = os.getenv("X_ACCESS_TOKEN")
        access_token_secret = os.getenv("X_ACCESS_TOKEN_SECRET")
        if not bearer_token and not all([consumer_key, consumer_secret,
                                         access_token, access_token_secret]):
            print("[Analytics] X API 認証情報が不足しています。スキップ。")
            return None
        return tweepy.Client(
            bearer_token        = bearer_token,
            consumer_key        = consumer_key,
            consumer_secret     = consumer_secret,
            access_token        = access_token,
            access_token_secret = access_token_secret,
            wait_on_rate_limit  = True,
        )
    except ImportError:
        print("[Analytics] tweepy が未インストールです。pip install tweepy を実行してください。")
        return None
    except Exception as e:
        print(f"[Analytics] tweepy 初期化失敗: {e}")
        return None


def fetch_tweet_metrics(client, tweet_id: str) -> dict:
    """
    X API v2 で 1 件のツイートの public_metrics を取得して返す。
    取得失敗時は空 dict を返す。

    注意:
      - impression_count は public_metrics で取得可能（Basic アクセス以上が必要な場合あり）
      - click_count（リンククリック数）は X API の public_metrics には含まれないため 0 を返す
    """
    if not tweet_id or not client:
        return {}
    try:
        resp = client.get_tweet(
            id           = tweet_id,
            tweet_fields = ["public_metrics"],
        )
        if not resp.data:
            return {}
        metrics = resp.data.public_metrics or {}
        return {
            "impression_count": metrics.get("impression_count", 0),
            # X API の public_metrics にリンククリック数は含まれない
            "click_count":      0,
        }
    except Exception as e:
        print(f"  [Analytics] ツイート取得失敗 tweet_id={tweet_id}: {e}")
        return {}


def determine_winner(
    impression_count: int,
    genre: str,
    genre_avg: float,
) -> bool:
    """
    is_winner を判定する。

    ルール:
    - ジャンル平均が取得できている場合: 平均の 1.5 倍超で True
    - ジャンル平均が取得できていない場合: WINNER_FALLBACK_IMPRESSIONS 超で True
    """
    if genre_avg > 0:
        return impression_count >= genre_avg * WINNER_MULTIPLIER
    return impression_count >= WINNER_FALLBACK_IMPRESSIONS


def run_analytics_fetch() -> dict:
    """
    メイン処理。
    Returns: {"processed": int, "winners": int, "skipped": int}
    """
    print(f"\n[AnalyticsFetcher] {datetime.now().strftime('%Y/%m/%d %H:%M')} 開始")

    # 対象レコードを取得（24〜48 時間経過 + impression_count=0 + success=True）
    pending = db.get_pending_analytics_posts(hours_min=24, hours_max=48)
    print(f"[AnalyticsFetcher] 対象レコード: {len(pending)} 件")

    if not pending:
        print("[AnalyticsFetcher] 対象なし。終了。")
        return {"processed": 0, "winners": 0, "skipped": 0}

    client    = _build_tweepy_client()
    processed = 0
    winners   = 0
    skipped   = 0

    for record in pending:
        post_id  = record.get("id")
        tweet_id = record.get("tweet1_id") or ""
        genre    = record.get("genre") or ""

        if not tweet_id:
            print(f"  [skip] post_id={post_id}: tweet1_id が未記録")
            skipped += 1
            continue

        # X API からメトリクスを取得
        metrics = fetch_tweet_metrics(client, tweet_id)
        if not metrics:
            print(f"  [skip] post_id={post_id} tweet_id={tweet_id}: メトリクス取得失敗")
            skipped += 1
            continue

        imp_count = metrics.get("impression_count", 0)
        clk_count = metrics.get("click_count", 0)

        # ジャンル平均を取得して is_winner を判定
        genre_avg  = db.get_genre_impression_avg(genre) if genre else 0.0
        is_winner  = determine_winner(imp_count, genre, genre_avg)

        # DB を更新
        db.update_post_analytics(
            post_id          = post_id,
            impression_count = imp_count,
            click_count      = clk_count,
            is_winner        = is_winner,
        )

        winner_mark = " ★WINNER" if is_winner else ""
        print(
            f"  [OK] post_id={post_id} genre={genre or 'n/a'} "
            f"imp={imp_count} (avg={genre_avg:.0f}×{WINNER_MULTIPLIER}={genre_avg*WINNER_MULTIPLIER:.0f})"
            f"{winner_mark}"
        )
        processed += 1
        if is_winner:
            winners += 1

    print(
        f"\n[AnalyticsFetcher] 完了 — "
        f"処理: {processed} 件 / winner: {winners} 件 / スキップ: {skipped} 件"
    )
    return {"processed": processed, "winners": winners, "skipped": skipped}


if __name__ == "__main__":
    # .env を読み込む（ローカル実行時）
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

    result = run_analytics_fetch()
    print(f"\n結果: {result}")
