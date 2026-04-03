"""
アナリストエージェント
過去の投稿パフォーマンスを分析し、今日の戦略をCEOに報告する
"""
import json
import os
from pathlib import Path
from datetime import datetime, timedelta
from google import genai

BASE_DIR = Path(__file__).parent.parent


def _load_post_logs() -> dict:
    """各プラットフォームの投稿ログを収集"""
    logs = {}

    # はてな
    hatena_log = BASE_DIR.parent / "hatena_automation" / "hatena_post_log.json"
    if hatena_log.exists():
        try:
            logs["hatena"] = json.loads(hatena_log.read_text(encoding="utf-8"))
        except Exception:
            logs["hatena"] = []

    # note
    note_log = BASE_DIR.parent / "note_automation" / "note_post_log.json"
    if note_log.exists():
        try:
            logs["note"] = json.loads(note_log.read_text(encoding="utf-8"))
        except Exception:
            logs["note"] = []

    # X
    x_log = BASE_DIR.parent / "x_automation" / "post_log.json"
    if x_log.exists():
        try:
            logs["x"] = json.loads(x_log.read_text(encoding="utf-8"))
        except Exception:
            logs["x"] = []

    return logs


def _load_revenue_data() -> dict:
    """収益データを読み込み"""
    revenue_file = BASE_DIR / "analytics_history.json"
    if revenue_file.exists():
        try:
            return json.loads(revenue_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _load_search_console_data() -> dict:
    """Search Console分析結果を読み込む（CSVがあれば自動更新）"""
    try:
        from money_agent.search_console_analyzer import run as sc_run
        return sc_run()
    except Exception:
        pass
    # フォールバック: 既存JSONを読む
    sc_file = BASE_DIR / "search_console_analysis.json"
    if sc_file.exists():
        try:
            return json.loads(sc_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def run(state: dict) -> dict:
    """
    アナリスト実行
    Returns: 分析インサイト
    """
    print("  📊 [Analyst] パフォーマンス分析中...")

    logs = _load_post_logs()
    revenue_data = _load_revenue_data()
    sc_data = _load_search_console_data()

    # Search Consoleからキーワードヒントを抽出
    sc_low_position = [q["query"] for q in sc_data.get("low_position_queries", [])[:5]]
    sc_hi_imp_lo_ctr = [q["query"] for q in sc_data.get("high_impression_low_ctr", [])[:5]]
    if sc_low_position:
        print(f"  🔍 [Analyst] GSC: 2ページ目キーワード {len(sc_low_position)}件検出（リライト候補）")

    # 直近7日の投稿を集計
    recent_posts = []
    for platform, entries in logs.items():
        if isinstance(entries, list):
            recent_posts.extend(entries[-20:])  # 各プラットフォームの直近20件

    # 投稿済みカテゴリを集計
    category_counts: dict[str, int] = {}
    for post in recent_posts:
        cat = post.get("category", post.get("keyword", "unknown"))
        category_counts[cat] = category_counts.get(cat, 0) + 1

    # feedback_insights.json から既存インサイトも参照
    insights_file = BASE_DIR / "feedback_insights.json"
    existing_insights = {}
    if insights_file.exists():
        try:
            existing_insights = json.loads(insights_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Gemini でインサイト生成
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if api_key:
        try:
            client = genai.Client(api_key=api_key)
            sc_summary = {
                "avg_position": sc_data.get("avg_position"),
                "avg_ctr": sc_data.get("avg_ctr"),
                "low_position_queries": sc_low_position,
                "title_improvement_candidates": sc_hi_imp_lo_ctr,
                "recommendations": sc_data.get("recommendations", []),
            } if sc_data else {}

            prompt = f"""あなたはアフィリエイトマーケティングの分析専門家です。

直近の投稿カテゴリ集計: {json.dumps(category_counts, ensure_ascii=False)}
既存インサイト: {json.dumps(existing_insights, ensure_ascii=False)[:500]}
収益データ: {json.dumps(revenue_data, ensure_ascii=False)[:300]}
Google Search Consoleデータ: {json.dumps(sc_summary, ensure_ascii=False)}

以下を日本語でJSONのみ返してください（コードブロック不要）:
{{
  "top_categories": ["最も収益が見込めるカテゴリ1", "カテゴリ2", "カテゴリ3"],
  "avoid_categories": ["飽和しているカテゴリ"],
  "today_strategy": "今日の記事生成戦略を1文で",
  "title_tips": "クリック率を上げるタイトルのコツを1文で",
  "cta_tips": "CV率を上げるCTAのコツを1文で"
}}"""

            resp = client.models.generate_content(
                model="gemini-2.0-flash-lite",
                contents=prompt,
            )
            text = resp.text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            analysis = json.loads(text)
            print(f"  ✅ [Analyst] 推奨カテゴリ: {analysis.get('top_categories', [])}")
            return analysis
        except Exception as e:
            print(f"  ⚠️ [Analyst] Gemini分析スキップ: {e}")

    # フォールバック: ルールベース分析
    # 最近少ない（=飽和していない）カテゴリを優先
    from money_agent.keywords_db import KEYWORD_CATEGORIES
    all_categories = list(KEYWORD_CATEGORIES.keys())
    sorted_cats = sorted(all_categories, key=lambda c: category_counts.get(c, 0))

    return {
        "top_categories": sorted_cats[:3],
        "avoid_categories": sorted_cats[-2:],
        "today_strategy": "投稿数の少ないカテゴリを優先して記事を量産する",
        "title_tips": "数字・具体性・疑問形を組み合わせてクリック率を上げる",
        "cta_tips": "記事末尾に「今すぐ申し込む」ボタンを設置する",
    }
