"""
ジャンル別収益分析エンジン
Supabaseの投稿データ + Bitlyクリックデータ + Search Console流入を統合し、
「どのジャンルが一番儲かっているか」を自動判定する。

特化ブログ展開の判断材料として週次レポートを自動生成する。

実行:
  python3 money_agent/genre_analyzer.py              # 分析レポート表示
  python3 money_agent/genre_analyzer.py --json        # JSON出力
  python3 money_agent/genre_analyzer.py --recommend   # 特化ブログ推奨ジャンル
"""
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from db_client import db

DATA_DIR = Path(__file__).parent / "data"
SC_ANALYSIS = DATA_DIR / "search_console_analysis.json"
REPORT_FILE = DATA_DIR / "genre_analysis_report.json"


# カテゴリ別の報酬単価（keywords_db.py と同期）
CATEGORY_UNIT_PRICE = {
    "dx_tools": 1500,
    "ai_tools": 3000,
    "ai_saas": 3000,
    "side_hustle": 3000,
    "investment_savings": 8000,
    "savings_lifestyle": 5000,
    "high_value": 15000,
    "productivity": 2000,
}

# カテゴリ別の推定CVR（Bitlyクリック→成約）
DEFAULT_CVR = {
    "dx_tools": 0.02,
    "ai_tools": 0.015,
    "ai_saas": 0.015,
    "side_hustle": 0.01,
    "investment_savings": 0.008,
    "savings_lifestyle": 0.012,
    "high_value": 0.005,
    "productivity": 0.01,
}


def _load_env():
    env_path = ROOT_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def get_post_stats_by_category() -> dict:
    """Supabaseから投稿データをカテゴリ別に集計"""
    try:
        records = db.get_revenue_records(
            year=datetime.now().year,
            month=datetime.now().month,
        )
    except Exception:
        records = []

    stats = defaultdict(lambda: {
        "post_count": 0,
        "total_pv": 0,
        "total_estimated_revenue": 0,
        "platforms": defaultdict(int),
        "keywords": [],
    })

    for r in records:
        cat = r.get("category", "unknown")
        stats[cat]["post_count"] += 1
        stats[cat]["total_pv"] += r.get("estimated_pv_30days", 0)
        stats[cat]["total_estimated_revenue"] += r.get("estimated_revenue_30days", 0)
        stats[cat]["platforms"][r.get("platform", "unknown")] += 1
        kw = r.get("keyword", "")
        if kw and kw not in stats[cat]["keywords"]:
            stats[cat]["keywords"].append(kw)

    return dict(stats)


def get_click_stats_by_campaign() -> dict:
    """Bitlyクリックデータをキャンペーン（カテゴリ）別に集計"""
    try:
        from money_agent.affiliate_tracker import get_top_performers
        top = get_top_performers(limit=50, cooldown=False)
    except Exception:
        top = []

    stats = defaultdict(lambda: {"total_clicks": 0, "links": 0})
    for link in top:
        campaign = link.get("campaign_id", "unknown")
        # campaign_idからカテゴリを推定
        cat = _campaign_to_category(campaign)
        stats[cat]["total_clicks"] += link.get("click_count", 0)
        stats[cat]["links"] += 1

    return dict(stats)


def _campaign_to_category(campaign_id: str) -> str:
    """campaign_idからカテゴリを推定"""
    if not campaign_id:
        return "unknown"
    campaign_lower = campaign_id.lower()
    mapping = {
        "dx": "dx_tools", "freee": "dx_tools", "moneyforward": "dx_tools",
        "chatwork": "dx_tools", "mf_": "dx_tools",
        "ai": "ai_tools", "chatgpt": "ai_tools", "gemini": "ai_tools",
        "side": "side_hustle", "副業": "side_hustle",
        "invest": "investment_savings", "nisa": "investment_savings",
        "ideco": "investment_savings", "証券": "investment_savings",
        "sim": "savings_lifestyle", "電気": "savings_lifestyle",
        "credit": "savings_lifestyle", "カード": "savings_lifestyle",
        "program": "high_value", "転職": "high_value", "fx": "high_value",
        "prod": "productivity", "notion": "productivity",
    }
    for key, cat in mapping.items():
        if key in campaign_lower:
            return cat
    return "unknown"


def get_search_console_stats() -> dict:
    """Search Console分析データをカテゴリ別に集計"""
    if not SC_ANALYSIS.exists():
        return {}

    try:
        data = json.loads(SC_ANALYSIS.read_text(encoding="utf-8"))
    except Exception:
        return {}

    queries = data if isinstance(data, list) else data.get("queries", [])

    stats = defaultdict(lambda: {
        "total_clicks": 0,
        "total_impressions": 0,
        "avg_position": 0,
        "query_count": 0,
        "top_queries": [],
    })

    for q in queries:
        query_text = q.get("query", "")
        cat = _query_to_category(query_text)
        clicks = q.get("clicks", 0)
        impressions = q.get("impressions", 0)
        position = q.get("position", 50)

        stats[cat]["total_clicks"] += clicks
        stats[cat]["total_impressions"] += impressions
        stats[cat]["avg_position"] += position
        stats[cat]["query_count"] += 1
        if clicks > 0:
            stats[cat]["top_queries"].append({
                "query": query_text,
                "clicks": clicks,
                "position": position,
            })

    # 平均順位計算
    for cat in stats:
        if stats[cat]["query_count"] > 0:
            stats[cat]["avg_position"] /= stats[cat]["query_count"]
            stats[cat]["avg_position"] = round(stats[cat]["avg_position"], 1)
        stats[cat]["top_queries"].sort(key=lambda x: -x["clicks"])
        stats[cat]["top_queries"] = stats[cat]["top_queries"][:5]

    return dict(stats)


def _query_to_category(query: str) -> str:
    """検索クエリからカテゴリを推定"""
    q = query.lower()
    if any(w in q for w in ["freee", "マネーフォワード", "クラウド会計", "バックオフィス", "chatwork", "dx"]):
        return "dx_tools"
    if any(w in q for w in ["ai", "chatgpt", "gemini", "画像生成", "動画生成"]):
        return "ai_tools"
    if any(w in q for w in ["副業", "せどり", "クラウドワークス", "ランサーズ", "アフィリエイト"]):
        return "side_hustle"
    if any(w in q for w in ["nisa", "ideco", "証券", "投資", "fx"]):
        return "investment_savings"
    if any(w in q for w in ["格安sim", "電気代", "節約", "クレジットカード", "電力"]):
        return "savings_lifestyle"
    if any(w in q for w in ["プログラミング", "スクール", "転職", "英会話"]):
        return "high_value"
    if any(w in q for w in ["notion", "タスク管理", "生産性", "時短"]):
        return "productivity"
    return "unknown"


def calculate_genre_scores() -> list:
    """全カテゴリの収益スコアを計算し、ランキングで返す"""
    post_stats = get_post_stats_by_category()
    click_stats = get_click_stats_by_campaign()
    sc_stats = get_search_console_stats()

    all_categories = set(
        list(post_stats.keys()) +
        list(click_stats.keys()) +
        list(sc_stats.keys()) +
        list(CATEGORY_UNIT_PRICE.keys())
    )
    all_categories.discard("unknown")

    scores = []
    for cat in sorted(all_categories):
        posts = post_stats.get(cat, {})
        clicks = click_stats.get(cat, {})
        sc = sc_stats.get(cat, {})

        post_count = posts.get("post_count", 0)
        bitly_clicks = clicks.get("total_clicks", 0)
        sc_clicks = sc.get("total_clicks", 0)
        sc_impressions = sc.get("total_impressions", 0)
        avg_position = sc.get("avg_position", 50)
        unit_price = CATEGORY_UNIT_PRICE.get(cat, 1000)
        cvr = DEFAULT_CVR.get(cat, 0.01)

        # 推定月間収益 = (Bitlyクリック + SC流入) × CVR × 単価
        total_traffic = bitly_clicks + sc_clicks
        estimated_monthly_revenue = total_traffic * cvr * unit_price

        # ポテンシャルスコア = 単価 × (1/競合度) × トラフィック成長可能性
        position_bonus = max(0, (30 - avg_position) / 30) if avg_position < 30 else 0
        potential_score = unit_price * (1 + position_bonus) * max(1, sc_impressions / 100)

        # 総合スコア = 実績ベース収益 + ポテンシャル
        total_score = estimated_monthly_revenue + potential_score * 0.1

        scores.append({
            "category": cat,
            "label": _category_label(cat),
            "post_count": post_count,
            "bitly_clicks": bitly_clicks,
            "sc_clicks": sc_clicks,
            "sc_impressions": sc_impressions,
            "avg_position": avg_position,
            "unit_price": unit_price,
            "cvr": cvr,
            "estimated_monthly_revenue": round(estimated_monthly_revenue),
            "potential_score": round(potential_score),
            "total_score": round(total_score),
            "top_queries": sc.get("top_queries", []),
            "keywords_used": posts.get("keywords", [])[:5],
        })

    scores.sort(key=lambda x: -x["total_score"])
    return scores


def _category_label(cat: str) -> str:
    labels = {
        "dx_tools": "DX・業務効率化",
        "ai_tools": "AIツール",
        "ai_saas": "AI SaaS",
        "side_hustle": "副業・稼ぎ方",
        "investment_savings": "投資・資産形成",
        "savings_lifestyle": "節約・生活費削減",
        "high_value": "高単価案件",
        "productivity": "生産性向上",
    }
    return labels.get(cat, cat)


def recommend_specialized_blog(scores: list) -> dict:
    """特化ブログ展開の推奨ジャンルを判定"""
    if not scores:
        return {"recommendation": "データ不足", "reason": "分析に十分なデータがない"}

    top = scores[0]
    second = scores[1] if len(scores) > 1 else None

    # 判定基準
    has_traffic = top["sc_clicks"] > 10 or top["bitly_clicks"] > 5
    has_revenue = top["estimated_monthly_revenue"] > 0
    good_position = top["avg_position"] < 15
    high_unit = top["unit_price"] >= 3000

    reasons = []
    if has_traffic:
        reasons.append(f"検索流入あり（SC: {top['sc_clicks']}クリック）")
    if has_revenue:
        reasons.append(f"推定月収: {top['estimated_monthly_revenue']:,}円")
    if good_position:
        reasons.append(f"検索順位が良好（平均{top['avg_position']}位）")
    if high_unit:
        reasons.append(f"高単価（{top['unit_price']:,}円/件）")

    # 特化ブログ推奨条件: 3つ以上の条件を満たす
    ready = sum([has_traffic, has_revenue, good_position, high_unit]) >= 2

    return {
        "recommendation": top["category"] if ready else "まだ早い",
        "label": top["label"],
        "ready": ready,
        "reasons": reasons,
        "top_queries": top["top_queries"],
        "action": (
            f"「{top['label']}」特化ブログを新規開設し、"
            f"既存の上位記事を移植 → 内部リンク強化 → 月{top['unit_price'] * 10:,}円を目指す"
            if ready else
            "もう2-4週間データを蓄積してから判断"
        ),
        "second_candidate": second["label"] if second else None,
    }


def generate_report() -> dict:
    """週次分析レポートを生成"""
    scores = calculate_genre_scores()
    recommendation = recommend_specialized_blog(scores)

    report = {
        "generated_at": datetime.now().isoformat(),
        "genre_ranking": scores,
        "specialized_blog_recommendation": recommendation,
        "summary": {
            "total_categories": len(scores),
            "top_category": scores[0]["label"] if scores else "なし",
            "total_estimated_revenue": sum(s["estimated_monthly_revenue"] for s in scores),
        },
    }

    # レポートをファイルに保存
    REPORT_FILE.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return report


def print_report():
    """レポートをCLI表示"""
    report = generate_report()
    scores = report["genre_ranking"]
    rec = report["specialized_blog_recommendation"]

    print(f"\n{'='*60}")
    print(f"  ジャンル別収益分析レポート")
    print(f"  生成日時: {report['generated_at'][:16]}")
    print(f"{'='*60}")

    print(f"\n  推定月間総収益: {report['summary']['total_estimated_revenue']:,}円")

    print(f"\n  {'ランク':<4} {'ジャンル':<16} {'投稿':<4} {'SCクリック':<8} {'順位':<6} {'推定収益':<10} {'スコア':<8}")
    print(f"  {'-'*56}")
    for i, s in enumerate(scores, 1):
        print(
            f"  {i:<4} {s['label']:<16} {s['post_count']:<4} "
            f"{s['sc_clicks']:<8} {s['avg_position']:<6.1f} "
            f"{s['estimated_monthly_revenue']:>8,}円 {s['total_score']:>6,}"
        )

    print(f"\n{'='*60}")
    print(f"  特化ブログ推奨")
    print(f"{'='*60}")
    if rec["ready"]:
        print(f"\n  推奨ジャンル: {rec['label']}")
        for r in rec["reasons"]:
            print(f"    - {r}")
        print(f"\n  アクション: {rec['action']}")
        if rec.get("second_candidate"):
            print(f"  次点候補: {rec['second_candidate']}")
    else:
        print(f"\n  判定: {rec['recommendation']}")
        print(f"  理由: {rec['action']}")
        if rec.get("reasons"):
            print(f"  現状:")
            for r in rec["reasons"]:
                print(f"    - {r}")

    if scores and scores[0].get("top_queries"):
        print(f"\n  上位検索クエリ（{scores[0]['label']}）:")
        for q in scores[0]["top_queries"][:3]:
            print(f"    \"{q['query']}\" ({q['clicks']}クリック, {q['position']:.1f}位)")

    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    _load_env()

    if "--json" in sys.argv:
        report = generate_report()
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif "--recommend" in sys.argv:
        scores = calculate_genre_scores()
        rec = recommend_specialized_blog(scores)
        print(json.dumps(rec, ensure_ascii=False, indent=2))
    else:
        print_report()
