"""
reply_funnel_linker.py — ブログ自動公開 → Xリプライ連動スクリプト

フロー:
  1. A8/トレンド案件を X に投稿した直後に x_poster.py から subprocess で起動される
  2. seo_article_generator で記事を生成
  3. hatena_poster でブログを公開 → 記事URLを取得
  4. tweepy/twikit で元ツイートのリプライとしてブログURLを投稿（ツリー化）

使い方（直接実行）:
  python3 reply_funnel_linker.py --tweet-id 12345 --keyword 副業 --post-type a8
  python3 reply_funnel_linker.py --tweet-id 12345 --keyword 節約 --dry-run
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "x_automation"))
sys.path.insert(0, str(_ROOT / "hatena_automation"))
sys.path.insert(0, str(_ROOT / "money_agent"))


# ── キーワード → SEO記事カテゴリ マッピング ──────────────────────
_KW_TO_CATEGORY: dict[str, str] = {
    "副業":      "side_hustle",
    "在宅":      "side_hustle",
    "フリーランス": "side_hustle",
    "確定申告":  "tax",
    "節税":      "tax",
    "投資":      "investment_savings",
    "NISA":      "investment_savings",
    "iDeCo":     "investment_savings",
    "節約":      "lifestyle",
    "AI":        "ai_tools",
    "転職":      "side_hustle",
    "ブログ":    "side_hustle",
    "クレジット": "lifestyle",
    "保険":      "lifestyle",
}

_DEFAULT_CATEGORY = "lifestyle"


def _resolve_category(keyword: str) -> str:
    for k, cat in _KW_TO_CATEGORY.items():
        if k in keyword:
            return cat
    return _DEFAULT_CATEGORY


# ── ブログ記事生成 ────────────────────────────────────────────────

def generate_blog_article(keyword: str, category: str) -> dict:
    """
    seo_article_generator.generate_seo_article を呼んで記事を返す。
    失敗時は空 dict を返す。
    """
    try:
        from money_agent.seo_article_generator import generate_seo_article
        article = generate_seo_article(keyword=keyword, category=category)
        char_count = article.get("char_count", len(article.get("body", "")))
        print(f"[BlogPipeline] 記事生成完了: {article.get('title', '')} ({char_count}文字)")
        return article
    except Exception as e:
        print(f"[BlogPipeline] 記事生成失敗: {e}")
        return {}


# ── はてなブログ公開 ──────────────────────────────────────────────

def publish_to_hatena(article: dict) -> str:
    """
    hatena_poster.post_article で記事を公開し、ブログ URL を返す。
    失敗時は空文字列を返す。
    """
    if not article:
        return ""
    try:
        from hatena_automation.hatena_poster import post_article
        url = post_article(
            title    = article["title"],
            body_md  = article["body"],
            category = article.get("category", ""),
            draft    = False,
        )
        if url:
            print(f"[BlogPipeline] はてな公開成功: {url}")
        else:
            print("[BlogPipeline] はてな公開失敗（URLなし）")
        return url or ""
    except Exception as e:
        print(f"[BlogPipeline] はてな公開エラー: {e}")
        return ""


# ── Xリプライ投稿 ─────────────────────────────────────────────────

def post_reply_to_x(tweet_id: str, blog_url: str, article_title: str) -> bool:
    """
    tweet_id のリプライとしてブログURLを投稿する。
    tweepy → twikit の順でフォールバック。
    """
    if not tweet_id or not blog_url:
        print("[BlogPipeline] tweet_id または blog_url が空。リプライスキップ。")
        return False

    reply_text = f"詳しくはブログにまとめました👇\n\n{article_title}\n{blog_url}"
    # X 換算文字数チェック（280単位以内）
    try:
        sys.path.insert(0, str(_ROOT / "x_automation"))
        from x_post_generator import x_char_count
        if x_char_count(reply_text) > 275:
            reply_text = f"詳しくはブログで👇\n{blog_url}"
    except Exception:
        pass

    # tweepy でリプライ
    try:
        import tweepy
        api_key       = os.getenv("X_API_KEY")
        api_secret    = os.getenv("X_API_SECRET")
        access_token  = os.getenv("X_ACCESS_TOKEN")
        access_secret = os.getenv("X_ACCESS_TOKEN_SECRET")

        if all([api_key, api_secret, access_token, access_secret]):
            client = tweepy.Client(
                consumer_key=api_key,
                consumer_secret=api_secret,
                access_token=access_token,
                access_token_secret=access_secret,
            )
            resp = client.create_tweet(text=reply_text, in_reply_to_tweet_id=tweet_id)
            reply_id = resp.data["id"]
            print(f"[BlogPipeline] Xリプライ投稿成功: {reply_id}")
            return True
    except Exception as e:
        print(f"[BlogPipeline] tweepy リプライ失敗: {e}")

    # twikit フォールバック
    try:
        import asyncio
        from twikit import Client

        cookies_path = str(_ROOT / "x_automation" / "x_cookies.json")
        env_cookies  = os.getenv("X_COOKIES", "")
        if env_cookies and not os.path.exists(cookies_path):
            with open(cookies_path, "w") as f:
                f.write(env_cookies)

        if not os.path.exists(cookies_path):
            print("[BlogPipeline] x_cookies.json なし。twikit スキップ。")
            return False

        async def _reply():
            c = Client("ja")
            c.load_cookies(cookies_path)
            return await c.create_tweet(
                text             = reply_text,
                reply_to         = tweet_id,
            )

        tweet = asyncio.run(_reply())
        print(f"[BlogPipeline] twikit リプライ成功: {tweet.id}")
        return True
    except Exception as e:
        print(f"[BlogPipeline] twikit リプライ失敗: {e}")

    return False


# ── メイン実行 ────────────────────────────────────────────────────

def run(tweet_id: str, keyword: str, post_type: str = "a8", dry_run: bool = False) -> dict:
    """
    全フローを実行する。

    Returns:
        {"blog_url": str, "reply_posted": bool, "skipped": bool}
    """
    print(f"\n[BlogPipeline] 開始: tweet_id={tweet_id} keyword={keyword} post_type={post_type}")

    # はてな認証情報チェック
    hatena_id  = os.getenv("HATENA_ID", "")
    api_key    = os.getenv("HATENA_API_KEY", "")
    if not hatena_id or not api_key:
        print("[BlogPipeline] HATENA_ID / HATENA_API_KEY 未設定。スキップ。")
        return {"blog_url": "", "reply_posted": False, "skipped": True}

    category = _resolve_category(keyword)
    print(f"[BlogPipeline] カテゴリ: {category}")

    # 1. ブログ記事生成
    article = generate_blog_article(keyword, category)
    if not article:
        return {"blog_url": "", "reply_posted": False, "skipped": True}

    if dry_run:
        print(f"[BlogPipeline] [DRY-RUN] 記事タイトル: {article.get('title', '')}")
        print(f"[BlogPipeline] [DRY-RUN] ブログ公開・リプライをスキップ")
        return {"blog_url": "", "reply_posted": False, "skipped": True}

    # 2. はてなブログ公開
    blog_url = publish_to_hatena(article)
    if not blog_url:
        return {"blog_url": "", "reply_posted": False, "skipped": True}

    # 3. Xリプライ（5秒待機してツイートが確定してから投稿）
    time.sleep(5)
    replied = post_reply_to_x(tweet_id, blog_url, article.get("title", ""))

    return {"blog_url": blog_url, "reply_posted": replied, "skipped": False}


# ── CLI エントリポイント ──────────────────────────────────────────

if __name__ == "__main__":
    # .env 読み込み（ローカル実行時）
    env_path = _ROOT / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

    parser = argparse.ArgumentParser(description="ブログ自動公開 → Xリプライ連動")
    parser.add_argument("--tweet-id",  required=True, help="元ツイートのID")
    parser.add_argument("--keyword",   required=True, help="トレンドキーワード")
    parser.add_argument("--post-type", default="a8",  help="投稿タイプ (デフォルト: a8)")
    parser.add_argument("--dry-run",   action="store_true", help="記事生成のみ（公開・リプライしない）")
    args = parser.parse_args()

    result = run(
        tweet_id  = args.tweet_id,
        keyword   = args.keyword,
        post_type = args.post_type,
        dry_run   = args.dry_run,
    )

    print("\n[BlogPipeline] 結果:")
    print(f"  blog_url    : {result['blog_url'] or '（なし）'}")
    print(f"  reply_posted: {result['reply_posted']}")
    print(f"  skipped     : {result['skipped']}")
