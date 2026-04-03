"""
データ分析エージェント
成約率（CVR）を計算し、どの記事をリライトすべきか優先順位をつける
"""
import json
import os
from pathlib import Path
from datetime import datetime, timedelta
from google import genai

BASE_DIR = Path(__file__).parent.parent
ROOT_DIR = BASE_DIR.parent


def _load_all_post_logs() -> list:
    """全プラットフォームの投稿ログを統合"""
    posts = []
    log_files = [
        ROOT_DIR / "hatena_automation" / "hatena_post_log.json",
        ROOT_DIR / "note_automation" / "note_post_log.json",
    ]
    for f in log_files:
        if f.exists():
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    posts.extend(data)
            except Exception:
                pass
    return posts


def _load_agent_state() -> dict:
    f = BASE_DIR / "agent_state.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _calc_cvr_score(post: dict) -> float:
    """
    記事の推定CVRスコアを算出
    （実際のクリックデータがない場合はキーワード・カテゴリから推定）
    """
    score = 1.0

    # カテゴリ別CVR推定
    category = post.get("category", "")
    cvr_by_category = {
        "証券口座": 3.0,
        "AIツール・SaaS": 2.5,
        "DX・業務効率化ツール": 2.0,
        "米国株・ETF投資": 2.0,
        "クレジットカード": 1.5,
        "副業・在宅ワーク": 1.2,
        "FX口座": 1.0,
    }
    score *= cvr_by_category.get(category, 1.0)

    # 記事の古さペナルティ（3ヶ月以上前は陳腐化リスク）
    posted_at = post.get("posted_at", post.get("created_at", ""))
    if posted_at:
        try:
            dt = datetime.fromisoformat(posted_at[:19])
            age_days = (datetime.now() - dt).days
            if age_days > 90:
                score *= 0.7   # 古い記事はリライト候補
            elif age_days > 180:
                score *= 0.4
        except Exception:
            pass

    # タイトルの質スコア（数字・具体性）
    title = post.get("title", "")
    if any(str(n) in title for n in range(1, 20)):
        score *= 1.2   # 数字あり
    if "方法" in title or "やり方" in title or "手順" in title:
        score *= 1.1
    if "初心者" in title or "完全" in title:
        score *= 1.1

    return round(score, 3)


def run(state: dict) -> dict:
    """
    データ分析エージェント実行
    Returns: リライト優先順位リストと改善提案
    """
    print("  📈 [DataAnalyst] CVR分析・リライト優先順位付け中...")

    posts = _load_all_post_logs()
    agent_state = _load_agent_state()

    if not posts:
        print("  ⚠️ [DataAnalyst] 投稿ログなし。スキップ。")
        return {"rewrite_queue": [], "insights": {}}

    # 各記事にCVRスコアを付与
    scored_posts = []
    for post in posts[-50:]:  # 直近50件を分析
        score = _calc_cvr_score(post)
        scored_posts.append({
            **post,
            "cvr_score": score,
            "rewrite_priority": "HIGH" if score < 0.8 else ("MED" if score < 1.5 else "LOW"),
        })

    scored_posts.sort(key=lambda x: x["cvr_score"])  # スコアが低い順 = リライト優先

    # 統計
    total = len(scored_posts)
    high_priority = [p for p in scored_posts if p["rewrite_priority"] == "HIGH"]
    categories = {}
    for p in scored_posts:
        cat = p.get("category", "unknown")
        categories[cat] = categories.get(cat, 0) + 1

    # Gemini で改善提案生成
    api_key = os.environ.get("GEMINI_API_KEY", "")
    gemini_insights = {}
    if api_key and scored_posts:
        try:
            client = genai.Client(api_key=api_key)
            low_score_samples = [
                {"title": p.get("title", "")[:40], "category": p.get("category", ""), "score": p["cvr_score"]}
                for p in scored_posts[:5]
            ]
            prompt = f"""アフィリエイトブログのSEO分析専門家として分析してください。

CVRスコアが低い記事（リライト候補）:
{json.dumps(low_score_samples, ensure_ascii=False)}

カテゴリ別投稿数: {json.dumps(categories, ensure_ascii=False)}
総記事数: {total}

以下をJSONのみで返してください:
{{
  "rewrite_reason": "なぜこれらの記事がCVRが低いか（1文）",
  "rewrite_tips": ["改善方法1", "改善方法2", "改善方法3"],
  "best_category": "最も伸ばすべきカテゴリ",
  "kpi_summary": "現在のKPIサマリー（2文）"
}}"""
            resp = client.models.generate_content(
                model="gemini-2.0-flash-lite",
                contents=prompt,
            )
            text = resp.text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            gemini_insights = json.loads(text)
        except Exception as e:
            print(f"  ⚠️ [DataAnalyst] Gemini分析スキップ: {e}")

    result = {
        "total_articles": total,
        "rewrite_queue": [
            {"title": p.get("title", "")[:50], "category": p.get("category", ""), "score": p["cvr_score"]}
            for p in high_priority[:10]
        ],
        "category_distribution": categories,
        "insights": gemini_insights,
    }

    # 結果保存
    output_file = BASE_DIR / "data_analysis.json"
    output_file.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"  ✅ [DataAnalyst] 分析完了: {total}記事 / リライト候補: {len(high_priority)}件")
    return result
