"""
ライターエージェント
キーワード + アナリストのインサイトを元に高品質SEO記事を生成する
"""
import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent


def run(state: dict, research: dict) -> dict:
    """
    ライター実行

    Args:
        state: CEO共有状態（analyst_reportを含む）
        research: Researcherの出力（keyword, category, affiliates）

    Returns: 生成記事 dict
    """
    slot = research.get("slot", 0)
    keyword = research["keyword"]
    category = research["category"]
    affiliates = research["affiliates"]

    print(f"  ✍️  [Writer-{slot}] 「{keyword}」記事生成中...")

    analyst_report = state.get("analyst_report", {})
    title_tips = analyst_report.get("title_tips", "")
    cta_tips = analyst_report.get("cta_tips", "")
    today_strategy = analyst_report.get("today_strategy", "")

    # 既存のSEO記事生成モジュールを活用
    # ただし、アナリストのインサイトを feedback として渡す
    from money_agent.seo_article_generator import generate_seo_article

    feedback_insights = {
        "title_tips": title_tips,
        "cta_tips": cta_tips,
        "today_strategy": today_strategy,
        "keyword_strategy": {
            "recommended_categories": analyst_report.get("top_categories", []),
        },
    }

    article = generate_seo_article(
        keyword=keyword,
        category=category,
        affiliates=affiliates,
        feedback_insights=feedback_insights,
    )

    print(f"  ✅ [Writer-{slot}] タイトル: {article.get('title', '')[:40]}...")
    print(f"         文字数: {article.get('char_count', 0)}文字 / アフィリエイト: {article.get('affiliate_count', 0)}件")

    article["slot"] = slot
    return article
