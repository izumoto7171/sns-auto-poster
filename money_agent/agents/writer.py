"""
ライターエージェント v2
キーワード + アナリストのインサイトを元に高品質SEO記事を生成する

【v2の変更点】
- 全カテゴリでGemini最新情報取得を実施（ai_saas/ai_tools限定を撤廃）
- プロンプトを深化（ROI、導入事例、失敗パターン、隠れたコスト）
- reader_concernsをペルソナから自動生成
"""
import json
import os
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

# ツール名マッピング（キーワード → 正式名称）
_TOOL_NAME_MAP = {
    "chatgpt":       "ChatGPT（OpenAI GPT-4o）",
    "notion":        "Notion AI",
    "canva":         "Canva Pro",
    "claude":        "Claude（Anthropic）",
    "gemini":        "Google Gemini",
    "perplexity":    "Perplexity AI",
    "freee":         "freee会計",
    "マネーフォワード": "マネーフォワード クラウド",
    "chatwork":      "Chatwork",
    "sbi":           "SBI証券",
    "楽天証券":       "楽天証券",
    "ideco":         "iDeCo",
    "nisa":          "新NISA",
    "楽天カード":     "楽天カード",
}

# カテゴリ別の情報取得プロンプト
_CATEGORY_PROMPTS = {
    "ai_tools": "AIツールとしての最新機能、無料vs有料の違い、ビジネス活用事例",
    "ai_saas": "中小企業でのAI活用事例、導入ROI、競合ツールとの比較",
    "dx_tools": "中小企業での導入事例、コスト削減効果の具体的数値、インボイス/電帳法対応状況",
    "investment_savings": "最新の手数料体系、口座開設キャンペーン、他社との比較データ",
    "side_hustle": "実際の収益事例、必要な初期投資、成功率のデータ",
    "savings_lifestyle": "料金改定情報、乗り換え手続きの具体的手順、節約額の実例",
    "high_value": "受講者の転職成功率、年収アップ実績、カリキュラム比較",
    "productivity": "最新アップデート情報、他ツールとの連携、実際の時短効果",
}


def _fetch_latest_info(keyword: str, category: str) -> dict:
    """
    Geminiで対象キーワードの最新情報を取得する（全カテゴリ対応）
    """
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return {}

    kw_lower = keyword.lower()
    tool_name = next(
        (v for k, v in _TOOL_NAME_MAP.items() if k in kw_lower),
        keyword.split()[0]
    )

    focus_area = _CATEGORY_PROMPTS.get(category, "最新の動向、具体的な活用事例、料金比較")

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        prompt = f"""「{tool_name}」について、{datetime.now().year}年最新の情報を教えてください。

特に以下の観点で具体的に回答してください:
- {focus_area}

以下の形式でJSONのみ返してください（コードブロック不要）:
{{
  "latest_feature": "最新・注目の機能や変更点（具体的に1〜2文）",
  "update_highlight": "最近の大きなアップデートや制度変更（1文）",
  "business_use_case": "具体的な活用事例（数字を含めて1文）",
  "free_vs_paid": "無料と有料の実際の違い、またはコスト比較（1文）",
  "caution": "使用上の注意点・見落としがちなデメリット（1文）"
}}"""

        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        text = resp.text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        return json.loads(text)
    except Exception as e:
        print(f"  [Writer] 最新情報取得スキップ: {e}")
        return {}


def _generate_reader_concerns(keyword: str, category: str) -> list:
    """ペルソナの懸念点を生成（GEO懸念払拭セクション用）"""
    from money_agent.seo_article_generator import READER_PERSONAS
    persona = READER_PERSONAS.get(category, {})
    concern = persona.get("concern", "")
    if not concern:
        return []
    return [c.strip() for c in concern.split("、") if c.strip()]


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

    print(f"  [Writer-{slot}] 「{keyword}」記事生成中...")

    analyst_report = state.get("analyst_report", {})
    title_tips = analyst_report.get("title_tips", "")
    cta_tips = analyst_report.get("cta_tips", "")
    today_strategy = analyst_report.get("today_strategy", "")

    # 全カテゴリで最新情報を取得
    print(f"  [Writer-{slot}] 最新情報を検索中（{category}）...")
    latest_ai_info = _fetch_latest_info(keyword, category)
    if latest_ai_info:
        print(f"  [Writer-{slot}] 最新情報取得: {latest_ai_info.get('update_highlight', '')[:50]}")

    # 読者の懸念点をペルソナから自動生成
    reader_concerns = research.get("reader_concerns", [])
    if not reader_concerns:
        reader_concerns = _generate_reader_concerns(keyword, category)

    from money_agent.seo_article_generator import generate_seo_article

    feedback_insights = {
        "title_tips": title_tips,
        "cta_tips": cta_tips,
        "today_strategy": today_strategy,
        "keyword_strategy": {
            "recommended_categories": analyst_report.get("top_categories", []),
        },
        "latest_ai_info": latest_ai_info,
        "reader_concerns": reader_concerns,
    }

    article = generate_seo_article(
        keyword=keyword,
        category=category,
        affiliates=affiliates,
        feedback_insights=feedback_insights,
    )

    print(f"  [Writer-{slot}] タイトル: {article.get('title', '')[:40]}...")
    print(f"         文字数: {article.get('char_count', 0)}文字 / アフィリエイト: {article.get('affiliate_count', 0)}件")
    print(f"         テンプレート: {article.get('template', 'unknown')}")

    article["slot"] = slot
    return article
