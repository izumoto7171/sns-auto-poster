"""
SNSパフォーマンス分析 → フィードバックループ

【フロー】
SNS投稿 → X/Bluesky メトリクス収集 → Gemini分析
→ feedback_insights.json 保存 → 次回の記事生成に反映

使い方:
  python3 money_agent/analytics_feedback.py   # 分析実行
"""

import os
import sys
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).parent

# Supabase クライアント
sys.path.insert(0, str(BASE_DIR.parent))
from db_client import db


# ============================================================
# ユーティリティ（DB版）
# ============================================================

def load_insights() -> dict:
    """feedback_insights を DB から読み込む"""
    try:
        return db.get_insights()
    except Exception as e:
        print(f"[Analytics] insights DB読み込み失敗: {e}")
        return {"x": "", "bluesky": "", "best_keywords": [], "avoid_patterns": [], "updated_at": ""}


def save_insights(insights: dict):
    """feedback_insights を DB に upsert する"""
    try:
        db.save_insights(insights)
    except Exception as e:
        print(f"[Analytics] insights DB書き込み失敗: {e}")


def load_history() -> list:
    """analytics_history を DB から読み込む"""
    try:
        return db.get_analytics_history(limit=500)
    except Exception as e:
        print(f"[Analytics] history DB読み込み失敗: {e}")
        return []


def save_history(records: list) -> int:
    """analytics_history を DB に保存し、新規挿入件数を返す"""
    try:
        return db.save_analytics_records(records)
    except Exception as e:
        print(f"[Analytics] history DB書き込み失敗: {e}")
        return 0


# ============================================================
# X (Twitter) メトリクス収集
# ============================================================

def collect_x_metrics() -> list:
    print("[Analytics/X] メトリクス収集中...")
    records = []
    try:
        import tweepy
        client = tweepy.Client(
            bearer_token=os.getenv("X_BEARER_TOKEN"),
            consumer_key=os.getenv("X_API_KEY"),
            consumer_secret=os.getenv("X_API_SECRET"),
            access_token=os.getenv("X_ACCESS_TOKEN"),
            access_token_secret=os.getenv("X_ACCESS_TOKEN_SECRET"),
            wait_on_rate_limit=True,
        )
        me = client.get_me()
        if not me.data:
            print("[Analytics/X] ユーザー情報取得失敗")
            return []
        my_id = me.data.id

        tweets = client.get_users_tweets(
            id=my_id,
            max_results=20,
            tweet_fields=["created_at", "text", "public_metrics"],
        )
        if not tweets.data:
            return []

        for t in tweets.data:
            m = t.public_metrics or {}
            records.append({
                "platform": "x",
                "id": f"x_{t.id}",
                "text": t.text[:200],
                "created_at": t.created_at.isoformat() if t.created_at else "",
                "likes": m.get("like_count", 0),
                "retweets": m.get("retweet_count", 0),
                "replies": m.get("reply_count", 0),
                "impressions": m.get("impression_count", 0),
                "score": (
                    m.get("like_count", 0) * 3
                    + m.get("retweet_count", 0) * 5
                    + m.get("reply_count", 0) * 2
                    + m.get("impression_count", 0) * 0.01
                ),
                "collected_at": datetime.now().isoformat(),
            })
        print(f"[Analytics/X] {len(records)}件取得")
    except Exception as e:
        print(f"[Analytics/X] エラー: {e}")
    return records


# ============================================================
# Bluesky メトリクス収集
# ============================================================

def collect_bluesky_metrics() -> list:
    print("[Analytics/Bluesky] メトリクス収集中...")
    records = []
    try:
        from atproto import Client as BskyClient
        handle = os.getenv("BSKY_HANDLE", "")
        password = os.getenv("BSKY_APP_PASSWORD", os.getenv("BSKY_PASSWORD", ""))
        if not handle or not password:
            print("[Analytics/Bluesky] 認証情報なし、スキップ")
            return []

        client = BskyClient()
        client.login(handle, password)

        feed = client.get_author_feed(actor=handle, limit=20)
        for item in feed.feed:
            post = item.post
            text = getattr(post.record, "text", "") or ""
            likes = getattr(post, "like_count", 0) or 0
            reposts = getattr(post, "repost_count", 0) or 0
            replies = getattr(post, "reply_count", 0) or 0
            records.append({
                "platform": "bluesky",
                "id": f"bsky_{post.uri}",
                "text": text[:200],
                "created_at": getattr(post.record, "created_at", ""),
                "likes": likes,
                "reposts": reposts,
                "replies": replies,
                "impressions": 0,
                "score": likes * 3 + reposts * 5 + replies * 2,
                "collected_at": datetime.now().isoformat(),
            })
        print(f"[Analytics/Bluesky] {len(records)}件取得")
    except Exception as e:
        print(f"[Analytics/Bluesky] エラー: {e}")
    return records


# ============================================================
# Gemini で分析
# ============================================================

def analyze_with_gemini(records: list) -> dict:
    """収集データをGeminiで分析してinsightsを生成"""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("[Analytics/AI] GEMINI_API_KEY なし、スキップ")
        return {}

    insights = {}

    # プラットフォーム別に分析
    by_platform: dict[str, list] = {}
    for r in records:
        by_platform.setdefault(r["platform"], []).append(r)

    for platform, posts in by_platform.items():
        if len(posts) < 3:
            print(f"[Analytics/AI] {platform}: データ不足（{len(posts)}件）")
            continue

        sorted_posts = sorted(posts, key=lambda x: x.get("score", 0), reverse=True)
        top3 = sorted_posts[:3]
        bottom3 = sorted_posts[-3:]

        top_text = "\n".join([
            f"・スコア{p['score']:.0f} | いいね{p.get('likes', 0)} | {p['text'][:80]}"
            for p in top3
        ])
        bottom_text = "\n".join([
            f"・スコア{p['score']:.0f} | いいね{p.get('likes', 0)} | {p['text'][:80]}"
            for p in bottom3
        ])

        prompt = f"""SNS投稿のパフォーマンスデータを分析してください。

プラットフォーム: {platform}

【スコア上位3件（いいね×3 + RT/RP×5 + リプライ×2 + インプレ×0.01）】
{top_text}

【スコア下位3件】
{bottom_text}

以下を分析して、次の投稿戦略に活かせる情報をJSON形式で出力してください:
{{
  "winning_patterns": ["伸びた投稿の共通パターン（3つ以内）"],
  "avoid_patterns": ["避けるべきパターン（2つ以内）"],
  "best_content_type": "最も反応が良いコンテンツタイプを1文で",
  "next_action": "次の投稿で試すべきこと1つ"
}}

JSONのみ出力してください。"""

        try:
            from gemini_client import generate, strip_code_block
            import re
            text = generate(prompt, use_cache=False)
            if text:
                json_match = re.search(r'\{.*\}', strip_code_block(text), re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group())
                    insights[platform] = data
                    print(f"[Analytics/AI] {platform} 分析完了")
                    print(f"  勝ちパターン: {data.get('winning_patterns', [])[:1]}")
                else:
                    print(f"[Analytics/AI] {platform}: JSON解析失敗")
            else:
                print(f"[Analytics/AI] {platform}: Gemini応答なし（全リトライ失敗）")
        except Exception as e:
            print(f"[Analytics/AI] {platform} エラー: {e}")

    return insights


# ============================================================
# 全プラットフォームデータを統合してキーワード戦略を生成
# ============================================================

def generate_keyword_strategy(records: list, current_insights: dict) -> dict:
    """
    過去の投稿テキストからキーワード傾向を抽出し
    次の記事生成に使えるカテゴリ優先度を返す
    """
    # スコア上位20件のテキストを集める
    top_posts = sorted(records, key=lambda x: x.get("score", 0), reverse=True)[:20]
    top_texts = [p["text"] for p in top_posts if p.get("score", 0) > 0]

    if not top_texts:
        return {}

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {}

    combined = "\n".join(top_texts[:10])
    prompt = f"""以下はSNSで反応が良かった投稿テキストです。

{combined}

これらを分析して、次に書くべきSEO記事のカテゴリをJSON形式で返してください:
{{
  "recommended_categories": ["カテゴリ1", "カテゴリ2", "カテゴリ3"],
  "hot_topics": ["トピック1", "トピック2"],
  "reasoning": "推奨理由を1文で"
}}

候補カテゴリ: ai_tools, side_hustle, investment_savings, productivity, lifestyle
JSONのみ出力してください。"""

    try:
        from gemini_client import generate, strip_code_block
        import re
        text = generate(prompt, use_cache=False)
        if text:
            json_match = re.search(r'\{.*\}', strip_code_block(text), re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
    except Exception as e:
        print(f"[Analytics/Strategy] エラー: {e}")

    return {}


# ============================================================
# メイン実行
# ============================================================

def run_analytics_feedback() -> dict:
    """
    全プラットフォームのデータ収集 → Gemini分析 → insights保存
    Returns: 保存したinsights
    """
    print(f"\n[Analytics] {datetime.now().strftime('%Y/%m/%d %H:%M')} 分析開始")

    # データ収集
    all_records = []
    all_records += collect_x_metrics()
    all_records += collect_bluesky_metrics()

    if not all_records:
        print("[Analytics] 収集データなし")
        return load_insights()

    # 履歴に保存
    new_count = save_history(all_records)
    print(f"[Analytics] 新規{new_count}件をhistoryに追加")

    # 全履歴を使って分析（データが多いほど精度向上）
    history = load_history()
    print(f"[Analytics] 累計{len(history)}件で分析")

    if len(history) < 3:
        print("[Analytics] データが少ないため分析スキップ（最低3件必要）")
        return load_insights()

    # Geminiで分析
    platform_insights = analyze_with_gemini(history)
    keyword_strategy = generate_keyword_strategy(history, platform_insights)

    # insightsを更新・保存
    current = load_insights()
    for platform, data in platform_insights.items():
        current[platform] = data
    if keyword_strategy:
        current["keyword_strategy"] = keyword_strategy

    save_insights(current)
    print("[Analytics] insights保存完了")

    # success_metrics をフィードバックデータで自動更新
    metrics_updated = update_success_metrics(history)
    if metrics_updated:
        current["success_metrics_updated"] = metrics_updated

    return current


# ============================================================
# success_metrics 自動更新（フィードバックループ）
# ============================================================

# 投稿テキストからカテゴリを推定するキーワードマッピング
_TEXT_TO_CATEGORY: list[tuple[list[str], str]] = [
    (["副業", "在宅ワーク", "フリーランス", "在宅"],   "side_hustle"),
    (["確定申告", "節税", "経費"],                      "tax"),
    (["会計", "帳簿", "クラウド会計"],                  "accounting"),
    (["NISA", "新NISA", "積立"],                        "nisa"),
    (["投資", "資産運用", "iDeCo"],                     "investment_savings"),
    (["ブログ", "アフィリエイト", "ドメイン"],          "blog"),
    (["節約", "コスパ", "食費", "光熱費"],              "lifestyle"),
    (["生産性", "効率", "時短"],                        "productivity"),
    (["AI", "ChatGPT", "Gemini"],                       "ai_tools"),
    (["ガジェット", "スマホ", "イヤホン"],              "gadget"),
    (["家電", "掃除", "洗濯"],                          "cleaning"),
    (["料理", "キッチン", "フライパン"],                "cooking_tools"),
    (["日用品", "洗剤", "シャンプー"],                  "daily_goods"),
]

# weight_bonus の上限・変動幅
_MAX_BONUS    = 8
_BONUS_STEP   = 2   # 高成績ジャンルへの加点
_PENALTY_STEP = 1   # 低成績ジャンルへの減点


def _infer_category(text: str) -> str:
    """投稿テキストからカテゴリを推定する"""
    for kws, cat in _TEXT_TO_CATEGORY:
        if any(kw in text for kw in kws):
            return cat
    return "lifestyle"  # デフォルト


def update_success_metrics(records: list) -> dict:
    """
    過去7日間のパフォーマンスデータから高CTRジャンルを特定し、
    success_metrics テーブルの weight_bonus を自動更新する。

    高スコア（上位30%）ジャンル: weight_bonus +2
    低スコア（下位30%）ジャンル: weight_bonus -1（最低0）

    Returns: {category: new_weight_bonus} の辞書
    """
    if not records:
        print("[Analytics/Metrics] データなし。スキップ。")
        return {}

    from datetime import datetime, timedelta

    # 7日以内のレコードのみ対象
    cutoff = (datetime.now() - timedelta(days=7)).isoformat()
    recent = [r for r in records if r.get("collected_at", "9999") >= cutoff]
    if len(recent) < 3:
        print(f"[Analytics/Metrics] 直近7日のデータが少ない（{len(recent)}件）。スキップ。")
        return {}

    # カテゴリ別スコア集計
    cat_scores: dict[str, list[float]] = {}
    for r in recent:
        cat   = _infer_category(r.get("text", ""))
        score = float(r.get("score", 0))
        cat_scores.setdefault(cat, []).append(score)

    # カテゴリ別平均スコアを計算
    cat_avg: dict[str, float] = {
        cat: sum(scores) / len(scores)
        for cat, scores in cat_scores.items()
        if scores
    }

    if not cat_avg:
        return {}

    avg_values  = sorted(cat_avg.values())
    n           = len(avg_values)
    low_thresh  = avg_values[max(0, int(n * 0.3) - 1)]
    high_thresh = avg_values[min(n - 1, int(n * 0.7))]

    print(f"[Analytics/Metrics] カテゴリ数: {len(cat_avg)} / 低閾値: {low_thresh:.1f} / 高閾値: {high_thresh:.1f}")

    # 現在の weight_bonus を取得
    try:
        current_metrics = db.get_success_metrics_dict()
    except Exception as e:
        print(f"[Analytics/Metrics] DB読み込み失敗: {e}")
        return {}

    updated: dict[str, int] = {}
    for cat, avg in cat_avg.items():
        current_bonus = current_metrics.get(cat, 0)

        if avg >= high_thresh:
            new_bonus = min(current_bonus + _BONUS_STEP, _MAX_BONUS)
            action    = f"+{_BONUS_STEP} (高パフォーマンス)"
        elif avg <= low_thresh:
            new_bonus = max(current_bonus - _PENALTY_STEP, 0)
            action    = f"-{_PENALTY_STEP} (低パフォーマンス)"
        else:
            continue  # 中間帯は変更しない

        try:
            db.upsert_success_metric(
                category     = cat,
                weight_bonus = new_bonus,
                click_delta  = 0,
                impression_delta = 0,
            )
            print(f"  [{cat}] {current_bonus} → {new_bonus} ({action}, avg={avg:.1f})")
            updated[cat] = new_bonus
        except Exception as e:
            print(f"  [{cat}] 更新失敗: {e}")

    print(f"[Analytics/Metrics] {len(updated)}カテゴリを更新")
    return updated


if __name__ == "__main__":
    # .envを読み込む（ローカル実行時）
    env_path = BASE_DIR.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

    result = run_analytics_feedback()
    print("\n[Analytics] 最終insights:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
