"""
競合アカウント分析スクリプト
指定アカウントの直近50件を取得し、エンゲージメントの高い投稿パターンを
Geminiで分析して5つの文章構成テンプレートを生成する。

使い方:
  python3 competitor_analyzer.py <@username>
  python3 competitor_analyzer.py <@username> --count 100
  python3 competitor_analyzer.py <@username> --dry-run  # API不要・サンプルデータで動作確認

出力: competitor_templates.json
"""
import os
import sys
import json
import argparse
from datetime import datetime


# ─────────────────────────────────────────
# 設定
# ─────────────────────────────────────────
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "competitor_templates.json")
SAMPLE_POSTS_FOR_DRY_RUN = [
    {
        "text": "副業で月5万円稼いだ方法を正直に話します。\n\nAI使って記事書いて、アフィリエイトで収益化。\n最初の3ヶ月は1円も入らなかった。\n\n諦めなければ変わる。",
        "likes": 312, "retweets": 89, "replies": 34,
        "engagement": 435
    },
    {
        "text": "「時間がない」と言い続けて3年経った。\n\n結局、優先順位の問題だった。\n大事なことを先にやるだけで、1日2時間生まれた。",
        "likes": 256, "retweets": 67, "replies": 28,
        "engagement": 351
    },
    {
        "text": "AIツールを1ヶ月使い倒した結論。\n\n・ChatGPT：アイデア出し\n・Gemini：記事構成\n・Claude：コード補完\n\n全部無料プランで月3万円の仕組みを作れた。",
        "likes": 198, "retweets": 55, "replies": 22,
        "engagement": 275
    },
    {
        "text": "副業失敗した話を正直に書く。\n\nブログ100記事書いたけどゼロ円。\n原因：キーワード選定を完全に間違えてた。\n\n失敗は授業料。次に活かす。",
        "likes": 445, "retweets": 120, "replies": 67,
        "engagement": 632
    },
    {
        "text": "知らないと損するAI副業の始め方。\n\n①無料ツールから始める\n②小さく試す（1000円の壁を越える）\n③うまくいったものだけ拡張する\n\nこれだけで変わった。",
        "likes": 380, "retweets": 95, "replies": 41,
        "engagement": 516
    },
]


def fetch_user_tweets(username: str, count: int) -> list[dict]:
    """
    tweepy v2 で指定ユーザーの直近ツイートを取得する。
    public_metrics（likes/retweets/replies）も取得。
    """
    try:
        import tweepy

        bearer = os.getenv("X_BEARER_TOKEN")
        # Bearer Tokenがなければ OAuth1.0a のAppのみ認証でも試みる
        if not bearer:
            api_key    = os.getenv("X_API_KEY")
            api_secret = os.getenv("X_API_SECRET")
            if not (api_key and api_secret):
                print("⚠️  X_BEARER_TOKEN も X_API_KEY/X_API_SECRET も未設定")
                print("   --dry-run で動作確認できます")
                return []
            client = tweepy.Client(
                consumer_key=api_key,
                consumer_secret=api_secret,
                access_token=os.getenv("X_ACCESS_TOKEN"),
                access_token_secret=os.getenv("X_ACCESS_TOKEN_SECRET"),
                wait_on_rate_limit=True,
            )
        else:
            client = tweepy.Client(bearer_token=bearer, wait_on_rate_limit=True)

        # ユーザーID取得
        clean = username.lstrip("@")
        user_resp = client.get_user(username=clean)
        if not user_resp.data:
            print(f"❌ ユーザー @{clean} が見つかりません")
            return []

        user_id = user_resp.data.id
        print(f"@{clean} (ID: {user_id}) のツイートを最大{count}件取得中...")

        tweets_resp = client.get_users_tweets(
            id=user_id,
            max_results=min(count, 100),
            tweet_fields=["public_metrics", "text", "created_at"],
            exclude=["retweets", "replies"],
        )

        if not tweets_resp.data:
            print("ツイートが取得できませんでした")
            return []

        posts = []
        for tw in tweets_resp.data:
            m = tw.public_metrics
            posts.append({
                "text":       tw.text,
                "likes":      m.get("like_count", 0),
                "retweets":   m.get("retweet_count", 0),
                "replies":    m.get("reply_count", 0),
                "engagement": m.get("like_count", 0) + m.get("retweet_count", 0) * 3 + m.get("reply_count", 0) * 2,
            })

        posts.sort(key=lambda x: x["engagement"], reverse=True)
        print(f"{len(posts)}件取得完了（エンゲージメント順にソート済み）")
        return posts

    except ImportError:
        print("❌ tweepy 未インストール: pip install tweepy")
        return []
    except Exception as e:
        print(f"❌ ツイート取得エラー: {e}")
        return []


def analyze_with_gemini(posts: list[dict], username: str, api_key: str) -> list[dict]:
    """
    Gemini でエンゲージメント上位投稿を分析し、5つの文章構成テンプレートを返す。
    """
    from google import genai

    # 上位20件を分析対象に絞る（プロンプトが長くなりすぎないよう）
    top_posts = posts[:20]
    posts_text = "\n\n---\n\n".join([
        f"エンゲージメント: {p['engagement']} (いいね{p['likes']}/RT{p['retweets']}/返信{p['replies']})\n{p['text']}"
        for p in top_posts
    ])

    prompt = f"""
あなたはX（Twitter）のコンテンツ戦略アナリストです。
競合アカウント @{username} の高エンゲージメント投稿を分析してください。

【分析対象の投稿（エンゲージメント上位20件）】
{posts_text}

【依頼】
上記の投稿を読んで、エンゲージメントが高い投稿に共通する「文章構成パターン」を5つ抽出してください。

各テンプレートは以下のJSON形式で出力してください：
{{
  "templates": [
    {{
      "id": 1,
      "name": "テンプレート名（短く・分かりやすく）",
      "description": "このパターンが効く理由（1〜2文）",
      "structure": {{
        "hook": "1行目フックの型（例：失敗談＋数字）",
        "body": "本文の型（例：箇条書きで3つの要素）",
        "close": "締め方の型（例：前向きな一言）"
      }},
      "example_hook": "フックの例文（実際に使えるもの）",
      "avg_engagement": 推定エンゲージメント数（整数）,
      "best_for": "このテンプレートが効果的な投稿タイプ"
    }}
  ]
}}

JSONのみ出力してください。説明文は不要。
"""

    client = genai.Client(api_key=api_key)
    resp = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
    )
    raw = resp.text.strip()

    # コードブロックを取り除く
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    data = json.loads(raw)
    return data.get("templates", [])


def save_templates(username: str, posts: list[dict], templates: list[dict]):
    """分析結果をJSONに保存"""
    result = {
        "analyzed_at":   datetime.now().isoformat(),
        "target_account": username,
        "posts_analyzed": len(posts),
        "top_posts": posts[:10],  # 上位10件も保存しておく（差別化フェーズで参照）
        "templates": templates,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n✅ テンプレートを保存: {OUTPUT_FILE}")


def print_templates(templates: list[dict]):
    """テンプレートをコンソールに表示"""
    print("\n" + "=" * 55)
    print("📊 分析結果：文章構成テンプレート 5パターン")
    print("=" * 55)
    for t in templates:
        print(f"\n【テンプレート{t['id']}】{t['name']}")
        print(f"効果: {t['description']}")
        print(f"推定エンゲージメント: {t['avg_engagement']}")
        print(f"向き: {t['best_for']}")
        print(f"構成:")
        s = t["structure"]
        print(f"  フック: {s['hook']}")
        print(f"  本文 : {s['body']}")
        print(f"  締め : {s['close']}")
        print(f"フック例: {t['example_hook']}")
    print("\n" + "=" * 55)


def main():
    parser = argparse.ArgumentParser(description="競合アカウント投稿分析ツール")
    parser.add_argument("username", help="分析対象の@ユーザー名（@は省略可）")
    parser.add_argument("--count", type=int, default=50, help="取得件数（デフォルト: 50）")
    parser.add_argument("--dry-run", action="store_true", help="サンプルデータで動作確認")
    args = parser.parse_args()

    # .env 読み込み
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

    username = args.username.lstrip("@")
    print(f"🔍 @{username} の投稿を分析します")

    # 投稿データ取得
    if args.dry_run:
        print("【DRY RUNモード】サンプルデータを使用")
        posts = SAMPLE_POSTS_FOR_DRY_RUN
    else:
        posts = fetch_user_tweets(username, args.count)
        if not posts:
            print("投稿が取得できませんでした。--dry-run で動作確認できます。")
            sys.exit(1)

    # Gemini 分析
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ GEMINI_API_KEY が未設定です")
        sys.exit(1)

    print(f"\n🤖 Gemini で {len(posts)} 件を分析中...")
    try:
        templates = analyze_with_gemini(posts, username, api_key)
    except Exception as e:
        print(f"❌ Gemini分析エラー: {e}")
        sys.exit(1)

    if not templates:
        print("❌ テンプレートの生成に失敗しました")
        sys.exit(1)

    print_templates(templates)
    save_templates(username, posts, templates)


if __name__ == "__main__":
    main()
