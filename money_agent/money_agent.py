"""
月10万円AIエージェント - メインオーケストレーター

【収益モデル】
はてなブログ SEO記事 × アフィリエイト → メイン収益（目標7万円/月）
note 記事          × アフィリエイト → サブ収益（目標2万円/月）
LINE Bot ステップ配信 × 商品紹介    → 高額商品（目標1万円/月）
────────────────────────────────────────
合計目標: 月100,000円

【実行フロー】
1. SNSメトリクス収集 → Gemini分析（前回の伸び要因を把握）
2. キーワード選定（商業意図 × 検索ボリューム × 競合度 × SNS傾向）
3. SEO最適化記事生成（2000〜4000文字 + アフィリエイトリンク + insights反映）
4. はてなブログに投稿（SEO設定込み）
5. noteに同内容を投稿（無料記事として流入獲得）
6. X / Blueskyで記事をシェア（+LINE誘導CTA）
7. 収益ログに記録
8. ダッシュボード更新
"""

import os
import sys
import json
import random
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# .env読み込み
def load_env():
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ[k] = v

load_env()

from money_agent.keywords_db import get_next_keyword, get_affiliates_for_category
from money_agent.seo_article_generator import generate_seo_article
from money_agent.revenue_tracker import record_post, print_dashboard

# ============================================================
# SNS投稿文生成（記事シェア用）
# ============================================================

def generate_sns_post_for_article(article: dict) -> dict:
    """記事シェア用のSNS投稿文を生成"""

    keyword = article["keyword"]
    title = article["title"]

    # X用（140文字以内）
    x_posts = [
        f"✅ 新記事を書きました！\n\n「{title[:30]}...」\n\n{keyword}について基礎から実践まで解説。\nアフィリエイトリンクもまとめてます👇\n\nプロフィールからLINE登録で更に詳しい情報をお届け📩",
        f"💡 {keyword}で月3万円稼ぐ方法を記事にまとめました\n\n初心者でもできる具体的な手順付き✅\n\n詳しくはブログで→\nLINE登録で限定情報も配信中📲",
        f"【新記事】{title[:25]}...\n\n✅ 具体的な手順あり\n✅ おすすめツール紹介\n✅ よくある失敗も解説\n\n読んで損なし！LINE登録者には更に詳細な情報も👆",
    ]

    # Bluesky用（簡潔・コミュニティ感）
    bsky_posts = [
        f"新しい記事を書きました📝\n\n{keyword}について詳しくまとめたので、気になる方はぜひ。\n\nアフィリエイトリンクもあるので参考にしてください🙌",
        f"「{keyword}」の記事を書きました。\n\n初心者向けに分かりやすく解説したつもりです。\nよかったら読んでみてください😊",
    ]

    return {
        "x": random.choice(x_posts),
        "bluesky": random.choice(bsky_posts),
    }


# ============================================================
# メインエージェント実行
# ============================================================

def run_money_agent(dry_run: bool = False, force_category: str = None) -> dict:
    """
    月10万円エージェントのメイン実行
    Returns: 実行結果サマリー
    """

    print("\n" + "="*60)
    print("  💰 月10万円 AIエージェント 起動")
    print(f"  🕐 {datetime.now().strftime('%Y/%m/%d %H:%M')}")
    print("="*60)

    results = {
        "success": [],
        "failed": [],
        "article": None,
        "revenue_estimate": 0
    }

    # === STEP 0: SNS分析（フィードバックループ） ===
    print("\n🔄 STEP 0: SNSパフォーマンス分析...")
    try:
        from money_agent.analytics_feedback import run_analytics_feedback, load_insights
        feedback_insights = run_analytics_feedback()
        print("  ✅ 分析完了 — 次の記事生成に反映します")
    except Exception as e:
        print(f"  ⚠️ 分析スキップ: {e}")
        try:
            from money_agent.analytics_feedback import load_insights
            feedback_insights = load_insights()
        except Exception:
            feedback_insights = {}

    # === STEP 1: キーワード選定 ===
    print("\n📊 STEP 1: キーワード選定...")

    # 使用済みキーワードを読み込み
    used_kw_file = os.path.join(os.path.dirname(__file__), "used_keywords.json")
    used_keywords = []
    if os.path.exists(used_kw_file):
        with open(used_kw_file) as f:
            used_keywords = json.load(f)

    kw_data = get_next_keyword(used_keywords)

    # force_category が未指定でも、insightsの推奨カテゴリがあれば使用
    if force_category:
        kw_data["category"] = force_category
    elif feedback_insights:
        strategy = feedback_insights.get("keyword_strategy", {})
        recommended = strategy.get("recommended_categories", [])
        if recommended:
            kw_data = get_next_keyword(used_keywords, preferred_category=recommended[0])
            print(f"  📊 SNS分析から推奨カテゴリ: {recommended[0]}")

    keyword = kw_data["keyword"]
    category = kw_data["category"]

    print(f"  ✅ キーワード: 「{keyword}」")
    print(f"  📂 カテゴリ: {category}")
    print(f"  🎯 検索意図: {kw_data['intent']}")

    # === STEP 2: SEO記事生成 ===
    print("\n✍️  STEP 2: SEO記事生成...")

    # Gemini APIが利用可能なら使用、なければテンプレート（insights反映）
    article = _generate_article_with_ai_or_template(keyword, category, feedback_insights)

    print(f"  ✅ タイトル: {article['title'][:50]}...")
    print(f"  📝 文字数: {article['char_count']}文字")
    print(f"  🔗 アフィリエイト: {article['affiliate_count']}件")

    results["article"] = article

    if dry_run:
        print("\n🔍 ドライランモード - 実際の投稿はスキップ")
        print_dashboard()
        return results

    # === STEP 3: はてなブログに投稿 ===
    print("\n📝 STEP 3: はてなブログ投稿...")
    hatena_result = _post_to_hatena(article)

    if hatena_result["success"]:
        print(f"  ✅ 投稿成功: {hatena_result.get('url', '')}")
        results["success"].append("hatena")
        record_post(
            platform="hatena",
            title=article["title"],
            keyword=keyword,
            category=category,
            affiliate_count=article["affiliate_count"],
            url=hatena_result.get("url", "")
        )
    else:
        print(f"  ❌ 投稿失敗: {hatena_result.get('error', '')}")
        results["failed"].append("hatena")

    # === STEP 4: noteに投稿 ===
    print("\n📓 STEP 4: note投稿...")
    note_result = _post_to_note(article)

    if note_result["success"]:
        print(f"  ✅ 投稿成功")
        results["success"].append("note")
        record_post(
            platform="note",
            title=article["title"],
            keyword=keyword,
            category=category,
            affiliate_count=article["affiliate_count"],
        )
    else:
        print(f"  ❌ 投稿失敗: {note_result.get('error', '')}")
        results["failed"].append("note")

    # === STEP 5: SNSでシェア ===
    print("\n📱 STEP 5: SNSシェア...")
    sns_posts = generate_sns_post_for_article(article)

    x_result = _post_to_x(sns_posts["x"])
    bsky_result = _post_to_bluesky(sns_posts["bluesky"])

    if x_result:
        print("  ✅ X投稿成功")
        results["success"].append("x")
    else:
        print("  ❌ X投稿失敗（全手段失敗）")
        results["failed"].append("x")
    if bsky_result:
        print("  ✅ Bluesky投稿成功")
        results["success"].append("bluesky")
    else:
        print("  ❌ Bluesky投稿失敗")
        results["failed"].append("bluesky")

    # === STEP 6: 使用済みキーワードを記録 ===
    used_keywords.append(keyword)
    if len(used_keywords) > 100:  # 古いものを削除
        used_keywords = used_keywords[-50:]
    with open(used_kw_file, "w") as f:
        json.dump(used_keywords, f, ensure_ascii=False)

    # === STEP 7: ダッシュボード表示 ===
    print("\n📊 STEP 7: 収益ダッシュボード")
    print_dashboard()

    print(f"\n✅ エージェント完了！")
    print(f"  成功: {', '.join(results['success'])}")
    if results["failed"]:
        print(f"  失敗: {', '.join(results['failed'])}")

    return results


# ============================================================
# 内部ヘルパー関数
# ============================================================

def _generate_article_with_ai_or_template(keyword: str, category: str, insights: dict = None) -> dict:
    """Gemini APIまたはテンプレートで記事生成"""

    api_key = os.getenv("GEMINI_API_KEY")

    if api_key:
        try:
            return _generate_with_gemini(keyword, category, api_key, insights)
        except Exception as e:
            print(f"  ⚠️ Gemini失敗、テンプレート使用: {e}")

    from money_agent.seo_article_generator import generate_seo_article
    return generate_seo_article(keyword, category)


def _build_insights_hint(insights: dict) -> str:
    """insightsからプロンプトに追加するヒントテキストを構築"""
    if not insights:
        return ""

    lines = []

    # プラットフォーム別の勝ちパターン
    for platform in ("x", "bluesky"):
        data = insights.get(platform, {})
        if isinstance(data, dict):
            patterns = data.get("winning_patterns", [])
            if patterns:
                lines.append(f"【{platform.upper()}で伸びたパターン】" + "、".join(patterns[:2]))
            avoid = data.get("avoid_patterns", [])
            if avoid:
                lines.append(f"【{platform.upper()}で避けるべきパターン】" + "、".join(avoid[:1]))

    # キーワード戦略
    strategy = insights.get("keyword_strategy", {})
    hot_topics = strategy.get("hot_topics", [])
    if hot_topics:
        lines.append(f"【SNSで今ホットなトピック】" + "、".join(hot_topics[:2]))

    if not lines:
        return ""

    return "\n【SNS分析からの改善ヒント（前回の伸び要因）】\n" + "\n".join(lines) + "\n"


def _generate_with_gemini(keyword: str, category: str, api_key: str, insights: dict = None) -> dict:
    """Gemini APIで高品質な記事生成（SNS insightsを反映）"""
    from gemini_client import generate, strip_code_block

    affiliates = get_affiliates_for_category(category)
    affiliate_text = "\n".join([f"- {a['name']}: {a['description']} ({a['commission']})" for a in affiliates[:3]])

    insights_hint = _build_insights_hint(insights)

    prompt = f"""
あなたはSEOライターです。以下の条件で記事を書いてください。

【キーワード】{keyword}
【カテゴリ】{category}
【目標文字数】2500〜3500文字
【読者】初心者〜中級者
【目的】読者の悩みを解決し、以下のアフィリエイト商品を自然に紹介する
{insights_hint}
【紹介するアフィリエイト商品】
{affiliate_text}

【記事構成】
1. タイトル（検索キーワードを含む・50文字以内）
2. 導入（読者の悩みに共感）
3. 本文（見出しH2×3〜4個、各500文字程度）
4. アフィリエイト商品の自然な紹介（押し売り感なく）
5. まとめ

【出力形式】
JSON形式で出力:
{{
  "title": "記事タイトル",
  "body": "本文（Markdown形式）"
}}
"""

    text = generate(prompt, use_cache=False)
    if not text:
        raise ValueError("Gemini APIが応答を返しませんでした（全リトライ失敗）")

    import re
    json_match = re.search(r'\{.*\}', strip_code_block(text), re.DOTALL)
    if json_match:
        data = json.loads(json_match.group())
        affiliates = get_affiliates_for_category(category)
        return {
            "title": data.get("title", f"【{keyword}】完全ガイド"),
            "body": data.get("body", ""),
            "keyword": keyword,
            "category": category,
            "char_count": len(data.get("body", "")),
            "affiliate_count": len(affiliates),
            "generated_at": datetime.now().isoformat()
        }

    raise ValueError("Geminiの出力をJSONとして解析できませんでした")


def _post_to_hatena(article: dict) -> dict:
    """はてなブログに投稿（AtomPub API）"""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "hatena_automation"))
        from hatena_poster import post_article, save_log
        url     = post_article(
            article["title"], article["body"],
            category=article.get("category", ""),
            tags=article.get("tags", []),
        )
        success = bool(url and not url.startswith("file://"))
        error   = "" if success else "投稿失敗"
        save_log(article, success=success, url=url or "", error_message=error)
        return {"success": success, "url": url}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _post_to_note(article: dict) -> dict:
    """noteに投稿（note.com API）"""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "note_automation"))
        from note_poster import post_article, save_log
        url     = post_article(article["title"], article["body"])
        success = bool(url)
        error   = "" if success else "投稿失敗"
        save_log(article, success=success, url=url or "", error_message=error)
        return {"success": success, "url": url}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _post_to_x(text: str) -> bool:
    """Xに投稿（tweepy公式API → ブラウザ の順でフォールバック）"""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "x_automation"))
        from x_poster import post_with_tweepy, post_with_browser
        # tweepy優先（GitHub Actions対応）
        if post_with_tweepy(text):
            return True
        print("  ⚠️ tweepy失敗、ブラウザ投稿にフォールバック...")
        return post_with_browser(text)
    except Exception as e:
        print(f"  ⚠️ X投稿エラー: {e}")
        return False


def _post_to_bluesky(text: str) -> bool:
    """Blueskyに投稿"""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "bluesky_automation"))
        from bsky_poster import post_to_bluesky
        result = post_to_bluesky(text)
        return result.get("success", False)
    except Exception as e:
        print(f"  ⚠️ Bluesky投稿エラー: {str(e)[:50]}")
        return False


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="月10万円AIエージェント")
    parser.add_argument("command", nargs="?", default="run",
                        choices=["run", "dry-run", "dashboard"])
    parser.add_argument("--category", help="カテゴリ指定")
    args = parser.parse_args()

    if args.command == "dashboard":
        print_dashboard()
    elif args.command == "dry-run":
        run_money_agent(dry_run=True, force_category=args.category)
    else:
        run_money_agent(dry_run=False, force_category=args.category)
