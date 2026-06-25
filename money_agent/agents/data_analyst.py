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

# デフォルトのCVR推定係数（実績データがない場合のフォールバック）
_DEFAULT_CVR: dict[str, float] = {
    "証券口座":           3.0,
    "AIツール・SaaS":     2.5,
    "DX・業務効率化ツール": 2.0,
    "米国株・ETF投資":    2.0,
    "クレジットカード":   1.5,
    "副業・在宅ワーク":   1.2,
    "FX口座":             1.0,
    # keywords_db.py のカテゴリ名にも対応
    "investment_savings":  3.0,
    "ai_saas":             2.5,
    "ai_tools":            2.0,
    "dx_tools":            2.0,
    "savings_lifestyle":   1.5,
    "side_hustle":         1.2,
    "high_value":          2.5,
    "productivity":        1.0,
}


def _load_actual_cvr() -> dict[str, float]:
    """
    conversion_tracker.py が算出した実績CVRを読み込む。
    なければデフォルト値にフォールバック。
    """
    cvr_file = BASE_DIR / "data" / "actual_cvr.json"
    if cvr_file.exists():
        try:
            data = json.loads(cvr_file.read_text(encoding="utf-8"))
            categories = data.get("categories", {})
            actual = {}
            for cat, info in categories.items():
                coeff = info.get("cvr_coefficient", 0)
                if coeff > 0:
                    actual[cat] = coeff
            if actual:
                print(f"  [DataAnalyst] 実績CVR読み込み: {len(actual)}カテゴリ")
                return {**_DEFAULT_CVR, **actual}
        except Exception as e:
            print(f"  [DataAnalyst] 実績CVR読み込みエラー: {e}")
    return _DEFAULT_CVR


# 実績データがあればそちらを使い、なければデフォルト
_CVR_BY_CATEGORY: dict[str, float] = _load_actual_cvr()


def _calc_cvr_score(post: dict) -> float:
    """記事の推定CVRスコアを算出（高いほど良い）"""
    score = 1.0

    # カテゴリ別係数（実績データ優先）
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

    # GEO KPI: カテゴリ別オファークリック率推定（推定収益/推定PV）
    geo_kpi = _calc_geo_kpi(posts, category_distribution)

    result = {
        "rewrite_queue":         rewrite_queue,
        "skip_genres":           gemini_result.get("skip_genres", []),
        "best_genre":            gemini_result.get("best_genre", "") or geo_kpi.get("top_offer_category", ""),
        "kpi_summary":           gemini_result.get("kpi_summary", ""),
        "action_needed":         len(high_items) > 0,
        "category_distribution": category_distribution,
        "total_articles":        total,
        "geo_kpi":               geo_kpi,
    }

    # 推奨アクションを人間承認キューに保存（初期は常に要承認）
    _save_pending_recommendations(result, geo_kpi)

    # JSON にキャッシュ保存（analyst.py / CEO がファイル参照する場合のため）
    output_file = BASE_DIR / "data" / "data_analysis.json"
    output_file.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        f"  [DataAnalyst] 完了: {total}記事分析 / "
        f"リライト候補: {len(high_items)}件 / "
        f"おすすめジャンル: {result['best_genre'] or '未判定'}"
    )
    if geo_kpi.get("top_offer_category"):
        print(
            f"  [DataAnalyst/GEO] オファークリック率トップ: {geo_kpi['top_offer_category']} "
            f"(推定 {geo_kpi.get('top_offer_ctr', 0):.2%})"
        )
    return result


def _save_pending_recommendations(result: dict, geo_kpi: dict):
    """
    DataAnalystの推奨アクションを「承認待ちキュー」に保存する。
    人間が data/pending_recommendations.json を確認・承認してから
    CEO が自動実行するフロー。
    """
    pending_file = BASE_DIR / "data" / "pending_recommendations.json"

    # 既存の承認待ちを読み込み
    existing = []
    if pending_file.exists():
        try:
            existing = json.loads(pending_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    # 承認済み（approved=True）はそのまま残す。新規のみ追加
    approved_ids = {r["id"] for r in existing if r.get("approved")}

    new_entry = {
        "id": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "generated_at": datetime.now().isoformat(),
        "approved": False,
        "applied": False,
        "recommendations": {
            "best_genre":   result.get("best_genre", ""),
            "skip_genres":  result.get("skip_genres", []),
            "kpi_summary":  result.get("kpi_summary", ""),
            "geo_recommendation": geo_kpi.get("recommendation", ""),
            "top_offer_category": geo_kpi.get("top_offer_category", ""),
            "high_priority_rewrites": [
                {"title": r["title"], "instruction": r["rewrite_instruction"]}
                for r in result.get("rewrite_queue", [])
                if r.get("rewrite_priority") == "HIGH"
            ][:3],  # 上位3件のみ表示
        },
        "auto_approve_threshold": 3,  # 同じ推奨が3回連続で出たら自動承認
    }

    # 同じbest_genreが連続して出た回数を数えて自動承認判定
    same_genre_count = sum(
        1 for r in existing
        if r.get("recommendations", {}).get("best_genre") == new_entry["recommendations"]["best_genre"]
        and not r.get("approved")
    )
    if same_genre_count >= new_entry["auto_approve_threshold"] - 1:
        new_entry["approved"] = True
        new_entry["auto_approved"] = True
        print(f"  [DataAnalyst] 自動承認: 「{new_entry['recommendations']['best_genre']}」が"
              f"{same_genre_count + 1}回連続で推奨されました")

    existing.append(new_entry)
    # 直近20件のみ保持
    existing = existing[-20:]

    pending_file.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")

    if not new_entry["approved"]:
        print(
            f"  [DataAnalyst] 推奨アクションを承認待ちキューに保存しました\n"
            f"    → data/pending_recommendations.json を確認して承認してください\n"
            f"    推奨: {new_entry['recommendations']['best_genre'] or '判定中'} / "
            f"GEO: {geo_kpi.get('recommendation', '')[:50]}"
        )


def _calc_geo_kpi(posts: list[dict], category_dist: dict) -> dict:
    """
    GEO の3つの KPI を推定する。
      - 回答引用率: ローカルの geo_citations.jsonl から算出
      - CTR (クリック率): 推定 impression / estimated_pv の比
      - オファークリック率: 推定収益 / (推定PV × 単価) で逆算
    """
    # カテゴリ別の推定収益・PVを集計
    cat_revenue: dict[str, int] = {}
    cat_pv: dict[str, int] = {}
    for p in posts:
        cat = p.get("category", p.get("post_type", "unknown"))
        cat_revenue[cat] = cat_revenue.get(cat, 0) + p.get("estimated_revenue_30days", 0)
        cat_pv[cat] = cat_pv.get(cat, 0) + p.get("estimated_pv_30days", 0)

    # オファークリック率 = 推定収益 / (推定PV × カテゴリ平均単価)
    _unit_prices = {
        "investment_savings": 8000,
        "ai_saas":            1500,
        "dx_tools":           3000,
        "side_hustle":        2000,
        "ai_tools":           1200,
        "productivity":       1000,
    }
    offer_ctrs: dict[str, float] = {}
    for cat, rev in cat_revenue.items():
        pv = cat_pv.get(cat, 1)
        price = _unit_prices.get(cat, 1000)
        if pv > 0 and price > 0:
            offer_ctrs[cat] = rev / (pv * price)

    top_category = max(offer_ctrs, key=offer_ctrs.get) if offer_ctrs else ""

    # 引用率はローカルログから
    citation_rate = 0.0
    try:
        geo_log = BASE_DIR / "data" / "geo_citations.jsonl"
        if geo_log.exists():
            lines = [l for l in geo_log.read_text(encoding="utf-8").splitlines() if l.strip()]
            if lines:
                records = [json.loads(l) for l in lines]
                citation_rate = sum(1 for r in records if r.get("cited_anywhere")) / len(records)
    except Exception:
        pass

    return {
        "top_offer_category": top_category,
        "top_offer_ctr":      offer_ctrs.get(top_category, 0.0),
        "offer_ctrs_by_cat":  offer_ctrs,
        "citation_rate":      citation_rate,
        "recommendation":     _geo_recommendation(top_category, citation_rate),
    }


def _geo_recommendation(top_category: str, citation_rate: float) -> str:
    """GEO KPIに基づく次のアクション推奨"""
    lines = []
    if citation_rate < 0.1:
        lines.append("引用率が低い：結論ファーストブロックとJSON-LDの配置を再確認してください")
    elif citation_rate < 0.3:
        lines.append(f"引用率改善中：懸念点セクションを `geo_verifier.py tune-concerns` で調整してください")
    else:
        lines.append("引用率良好：現在の構成を維持してください")

    if top_category:
        lines.append(f"オファークリック率が最も高いジャンル「{top_category}」への記事集中を推奨")

    return " / ".join(lines)
