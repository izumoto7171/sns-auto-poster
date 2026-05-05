"""
ライターエージェント
キーワード + アナリストのインサイトを元に高品質SEO記事を生成する

【ai_saas カテゴリの差別化】
競合が多いAIツール記事では Gemini でツールの最新情報を取得し
「情報の鮮度」で検索上位を狙う。
"""
import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

# AI検索を使うカテゴリ
_FRESH_SEARCH_CATEGORIES = {"ai_saas", "ai_tools"}

# ツール名マッピング（キーワード → 正式名称）
_TOOL_NAME_MAP = {
    "chatgpt":   "ChatGPT（OpenAI GPT-4o）",
    "notion":    "Notion AI",
    "canva":     "Canva Pro",
    "claude":    "Claude（Anthropic）",
    "gemini":    "Google Gemini",
    "perplexity": "Perplexity AI",
}


def _fetch_latest_ai_info(keyword: str) -> dict:
    """
    Gemini でAIツールの最新情報を取得する（ai_saas カテゴリ専用）
    取得できない場合は空dictを返す（記事生成は続行）
    """
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return {}

    # ツール名を特定
    kw_lower = keyword.lower()
    tool_name = next(
        (v for k, v in _TOOL_NAME_MAP.items() if k in kw_lower),
        keyword.split()[0]
    )

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        prompt = f"""{tool_name}の2026年最新情報を教えてください。
中小企業・ビジネスパーソンが特に注目すべき点に絞って回答してください。

以下の形式でJSONのみ返してください（コードブロック不要）:
{{
  "latest_feature": "2026年時点での最新・注目機能（具体的に1〜2文）",
  "update_highlight": "最近の大きなアップデートや変更点（1文）",
  "business_use_case": "中小企業での具体的な活用例（1文）",
  "free_vs_paid": "無料プランと有料プランの実際の違い（1文）",
  "caution": "使用上の注意点・制限（1文）"
}}"""

        resp = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        text = resp.text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        return json.loads(text)
    except Exception as e:
        print(f"  ⚠️ [Writer] 最新情報取得スキップ: {e}")
        return {}


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

    # ai_saas / ai_tools カテゴリは最新情報を取得して差別化
    latest_ai_info = {}
    if category in _FRESH_SEARCH_CATEGORIES:
        print(f"  🔍 [Writer-{slot}] 最新情報を検索中（{category}）...")
        latest_ai_info = _fetch_latest_ai_info(keyword)
        if latest_ai_info:
            print(f"  ✅ [Writer-{slot}] 最新情報取得: {latest_ai_info.get('update_highlight', '')[:50]}")

    # 既存のSEO記事生成モジュールを活用
    from money_agent.seo_article_generator import generate_seo_article

    feedback_insights = {
        "title_tips": title_tips,
        "cta_tips": cta_tips,
        "today_strategy": today_strategy,
        "keyword_strategy": {
            "recommended_categories": analyst_report.get("top_categories", []),
        },
        "latest_ai_info": latest_ai_info,  # ai_saas 差別化情報
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
