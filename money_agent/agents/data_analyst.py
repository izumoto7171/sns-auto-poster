"""
DataAnalyst — 投稿データのCVRスコアリングとリライト計画を返す

【出力: RewritePlan】
  {
    "rewrite_queue": [
      {
        "title": "記事タイトル",
        "category": "カテゴリ",
        "score": 0.45,
        "rewrite_priority": "HIGH",
        "rewrite_instruction": "具体的なリライト指示"
      },
      ...
    ],
    "skip_genres": ["CVRが低く避けるべきジャンル"],
    "best_genre": "最も伸ばすべきジャンル",
    "kpi_summary": "現在のKPI状況（2文）",
    "action_needed": True,          # HIGH優先リライトが1件以上あれば True
    "category_distribution": {...},
    "total_articles": 50
  }

Analyst.run() はこの結果を data_analysis 引数として受け取り、
ActionPlan 生成に使用する。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent.parent
ROOT_DIR = BASE_DIR.parent
sys.path.insert(0, str(ROOT_DIR))
from db_client import db

sys.path.insert(0, str(BASE_DIR))
from gemini_client import generate as gemini_generate, strip_code_block


# ── CVRスコア算出 ─────────────────────────────────────────────

# カテゴリ別CVR推定係数（単価×成約率で正規化）
_CVR_BY_CATEGORY: dict[str, float] = {
    "証券口座":           3.0,
    "AIツール・SaaS":     2.5,
    "DX・業務効率化ツール": 2.0,
    "米国株・ETF投資":    2.0,
    "クレジットカード":   1.5,
    "副業・在宅ワーク":   1.2,
    "FX口座":             1.0,
}


def _calc_cvr_score(post: dict) -> float:
    """記事の推定CVRスコアを算出（高いほど良い）"""
    score = 1.0

    # カテゴリ別係数
    category = post.get("category", post.get("post_type", ""))
    score *= _CVR_BY_CATEGORY.get(category, 1.0)

    # 記事の古さペナルティ
    posted_at = post.get("posted_at", post.get("created_at", ""))
    if posted_at:
        try:
            dt = datetime.fromisoformat(posted_at[:19])
            age_days = (datetime.now() - dt).days
            if age_days > 180:
                score *= 0.4   # 半年以上 — リライト最優先
            elif age_days > 90:
                score *= 0.7   # 3ヶ月以上 — リライト候補
        except Exception:
            pass

    # タイトルの質スコア
    title = post.get("title", post.get("text", ""))
    if any(str(n) in title for n in range(1, 20)):
        score *= 1.2   # 数字あり
    if any(kw in title for kw in ("方法", "やり方", "手順", "コツ")):
        score *= 1.1
    if any(kw in title for kw in ("初心者", "完全", "徹底")):
        score *= 1.1

    return round(score, 3)


def _priority_label(score: float) -> str:
    if score < 0.8:
        return "HIGH"
    if score < 1.5:
        return "MED"
    return "LOW"


# ── データ収集 ────────────────────────────────────────────────

def _load_posts() -> list[dict]:
    try:
        return db.get_posts(limit=200)
    except Exception as e:
        print(f"  [DataAnalyst] 投稿ログDB読み込み失敗: {e}")
        return []


# ── Gemini でリライト指示を生成 ───────────────────────────────

def _gemini_rewrite_plan(
    scored_posts: list[dict],
    category_distribution: dict,
    total: int,
) -> dict:
    """
    Gemini にリライト候補を渡し、具体的なリライト指示と
    ジャンル判定を生成させる。
    """
    high_items = [p for p in scored_posts if p["rewrite_priority"] == "HIGH"][:10]
    samples = [
        {
            "title":    p.get("title", p.get("text", ""))[:50],
            "category": p.get("category", p.get("post_type", "")),
            "score":    p["cvr_score"],
            "age_days": (
                (datetime.now() - datetime.fromisoformat(
                    p.get("posted_at", p.get("created_at", datetime.now().isoformat()))[:19]
                )).days
            ) if p.get("posted_at") or p.get("created_at") else 0,
        }
        for p in high_items
    ]

    prompt = f"""あなたはアフィリエイトSEO専門家です。以下の投稿データを分析し、
具体的なリライト計画とジャンル戦略を JSON のみで返してください。

【CVRスコアが低い記事（リライト候補）】
{json.dumps(samples, ensure_ascii=False)}

【カテゴリ別投稿数】
{json.dumps(category_distribution, ensure_ascii=False)}
総記事数: {total}

各リライト候補には「rewrite_instruction」（具体的な改善指示、1文）を必ず付けてください。
タイトル改善・導入文・内部リンク・CTA・キーワード密度など、具体策を書くこと。

以下の JSON 形式のみで出力（コードブロック不要）:
{{
  "rewrite_items": [
    {{
      "title": "記事タイトル",
      "category": "カテゴリ",
      "rewrite_instruction": "具体的なリライト指示1文"
    }}
  ],
  "skip_genres": ["CVRが低く今は避けるべきジャンル"],
  "best_genre": "最も伸ばすべきジャンル名",
  "kpi_summary": "現在のKPI状況（2文）"
}}"""

    raw = gemini_generate(prompt, use_cache=False)
    if not raw:
        return {}

    try:
        return json.loads(strip_code_block(raw))
    except Exception as e:
        print(f"  [DataAnalyst] JSONパース失敗: {e}")
        return {}


# ── メイン ────────────────────────────────────────────────────

def run(state: dict) -> dict:
    """
    DataAnalyst 実行 → RewritePlan を返す

    Parameters
    ----------
    state : CEO から渡された共有ステート（参照のみ）
    """
    print("  [DataAnalyst] CVR分析・リライト計画生成中...")

    posts = _load_posts()

    if not posts:
        print("  [DataAnalyst] 投稿ログなし。スキップ。")
        return {
            "rewrite_queue":          [],
            "skip_genres":            [],
            "best_genre":             "",
            "kpi_summary":            "投稿データなし",
            "action_needed":          False,
            "category_distribution":  {},
            "total_articles":         0,
        }

    # CVRスコアリング（直近50件）
    scored_posts = []
    for post in posts[-50:]:
        score = _calc_cvr_score(post)
        scored_posts.append({
            **post,
            "cvr_score":        score,
            "rewrite_priority": _priority_label(score),
        })
    scored_posts.sort(key=lambda x: x["cvr_score"])  # スコア低い順

    # カテゴリ分布
    category_distribution: dict[str, int] = {}
    for p in scored_posts:
        cat = p.get("category", p.get("post_type", "unknown"))
        category_distribution[cat] = category_distribution.get(cat, 0) + 1

    total      = len(scored_posts)
    high_items = [p for p in scored_posts if p["rewrite_priority"] == "HIGH"]

    # Gemini でリライト指示を生成
    gemini_result = _gemini_rewrite_plan(scored_posts, category_distribution, total)

    # Gemini の rewrite_items をスコア情報とマージ
    rewrite_queue: list[dict] = []
    if gemini_result.get("rewrite_items"):
        # Gemini が返した件数で instructions を生成
        for item in gemini_result["rewrite_items"]:
            # scored_posts からスコアを逆引き
            matched = next(
                (p for p in scored_posts
                 if p.get("title", p.get("text", ""))[:40] == item.get("title", "")[:40]),
                None,
            )
            rewrite_queue.append({
                "title":               item.get("title", ""),
                "category":            item.get("category", ""),
                "score":               matched["cvr_score"] if matched else 0.5,
                "rewrite_priority":    matched["rewrite_priority"] if matched else "HIGH",
                "rewrite_instruction": item.get("rewrite_instruction", ""),
            })
    else:
        # Gemini 失敗時はスコアのみで返す
        for p in high_items[:10]:
            rewrite_queue.append({
                "title":               p.get("title", p.get("text", ""))[:50],
                "category":            p.get("category", p.get("post_type", "")),
                "score":               p["cvr_score"],
                "rewrite_priority":    "HIGH",
                "rewrite_instruction": "タイトルに数字を入れ、導入部でSEOキーワードを強化する",
            })

    result = {
        "rewrite_queue":         rewrite_queue,
        "skip_genres":           gemini_result.get("skip_genres", []),
        "best_genre":            gemini_result.get("best_genre", ""),
        "kpi_summary":           gemini_result.get("kpi_summary", ""),
        "action_needed":         len(high_items) > 0,
        "category_distribution": category_distribution,
        "total_articles":        total,
    }

    # JSON にキャッシュ保存（analyst.py / CEO がファイル参照する場合のため）
    output_file = BASE_DIR / "data_analysis.json"
    output_file.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        f"  [DataAnalyst] 完了: {total}記事分析 / "
        f"リライト候補: {len(high_items)}件 / "
        f"おすすめジャンル: {result['best_genre'] or '未判定'}"
    )
    return result
