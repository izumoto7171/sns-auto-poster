"""
収益トラッカー
- 日別・月別の投稿数・推定PV数・推定収益を管理
- 10万円達成までの進捗を可視化
"""

import os
import json
from datetime import datetime, timedelta

TRACKER_FILE = os.path.join(os.path.dirname(__file__), "revenue_log.json")
TARGET_MONTHLY = 100000  # 月10万円


def load_log() -> dict:
    if os.path.exists(TRACKER_FILE):
        with open(TRACKER_FILE) as f:
            return json.load(f)
    return {"posts": [], "monthly_summary": {}}


def save_log(data: dict):
    with open(TRACKER_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def record_post(platform: str, title: str, keyword: str, category: str,
                affiliate_count: int = 0, url: str = ""):
    """投稿を記録"""
    log = load_log()
    entry = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "time": datetime.now().strftime("%H:%M"),
        "platform": platform,
        "title": title,
        "keyword": keyword,
        "category": category,
        "affiliate_count": affiliate_count,
        "url": url,
        # 推定値（実績データがたまれば更新）
        "estimated_pv_30days": estimate_pv(platform, category),
        "estimated_revenue_30days": estimate_revenue(platform, category, affiliate_count),
    }
    log["posts"].append(entry)
    save_log(log)
    return entry


def estimate_pv(platform: str, category: str) -> int:
    """30日間の推定PV数"""
    base_pv = {
        "hatena": {"investment_savings": 300, "side_hustle": 200, "ai_tools": 150, "productivity": 100},
        "note": {"investment_savings": 100, "side_hustle": 80, "ai_tools": 60, "productivity": 40},
        "x": {"investment_savings": 50, "side_hustle": 80, "ai_tools": 100, "productivity": 60},
        "bluesky": {"investment_savings": 20, "side_hustle": 30, "ai_tools": 40, "productivity": 25},
    }
    return base_pv.get(platform, {}).get(category, 50)


def estimate_revenue(platform: str, category: str, affiliate_count: int) -> int:
    """30日間の推定収益（円）"""
    pv = estimate_pv(platform, category)

    # カテゴリ別のコンバージョン率と単価
    conversion_data = {
        "investment_savings": {"rate": 0.008, "unit_price": 8000},  # 証券口座・クレカ高単価
        "side_hustle": {"rate": 0.015, "unit_price": 2000},
        "ai_tools": {"rate": 0.02, "unit_price": 1500},
        "productivity": {"rate": 0.018, "unit_price": 1200},
    }

    data = conversion_data.get(category, {"rate": 0.01, "unit_price": 1000})
    base_revenue = pv * data["rate"] * data["unit_price"]

    # アフィリエイトリンク数で補正（多いほど良い、ただし最大3倍）
    af_multiplier = min(1 + (affiliate_count - 1) * 0.3, 3.0) if affiliate_count > 0 else 0
    return int(base_revenue * af_multiplier)


def get_monthly_summary() -> dict:
    """今月の収益サマリー"""
    log = load_log()
    now = datetime.now()
    month_str = now.strftime("%Y-%m")

    posts_this_month = [p for p in log["posts"] if p["date"].startswith(month_str)]

    total_estimated_revenue = sum(p.get("estimated_revenue_30days", 0) for p in posts_this_month)
    total_posts = len(posts_this_month)
    total_pv = sum(p.get("estimated_pv_30days", 0) for p in posts_this_month)

    platform_breakdown = {}
    for p in posts_this_month:
        pl = p["platform"]
        if pl not in platform_breakdown:
            platform_breakdown[pl] = {"posts": 0, "revenue": 0}
        platform_breakdown[pl]["posts"] += 1
        platform_breakdown[pl]["revenue"] += p.get("estimated_revenue_30days", 0)

    progress_pct = min(total_estimated_revenue / TARGET_MONTHLY * 100, 100)

    return {
        "month": month_str,
        "total_posts": total_posts,
        "total_estimated_pv": total_pv,
        "total_estimated_revenue": total_estimated_revenue,
        "target": TARGET_MONTHLY,
        "progress_pct": round(progress_pct, 1),
        "remaining": max(TARGET_MONTHLY - total_estimated_revenue, 0),
        "platform_breakdown": platform_breakdown,
        "days_in_month": now.day,
        "daily_average": total_estimated_revenue // max(now.day, 1),
        "projected_monthly": (total_estimated_revenue // max(now.day, 1)) * 30,
    }


def print_dashboard():
    """収益ダッシュボードを表示"""
    summary = get_monthly_summary()

    print("\n" + "="*60)
    print(f"  💰 月10万円チャレンジ ダッシュボード")
    print(f"  📅 {summary['month']}")
    print("="*60)

    # プログレスバー
    bar_len = 40
    filled = int(bar_len * summary['progress_pct'] / 100)
    bar = "█" * filled + "░" * (bar_len - filled)
    print(f"\n  進捗: [{bar}] {summary['progress_pct']}%")
    print(f"  推定収益: ¥{summary['total_estimated_revenue']:,} / ¥{summary['target']:,}")
    print(f"  残り: ¥{summary['remaining']:,}")

    print(f"\n  📊 今月の実績")
    print(f"  投稿数: {summary['total_posts']}件")
    print(f"  推定PV: {summary['total_estimated_pv']:,}")
    print(f"  日次平均収益: ¥{summary['daily_average']:,}")
    print(f"  月末予測: ¥{summary['projected_monthly']:,}")

    print(f"\n  📱 プラットフォーム別")
    for pl, data in summary['platform_breakdown'].items():
        print(f"  {pl}: {data['posts']}投稿 / 推定¥{data['revenue']:,}")

    # アドバイス
    print(f"\n  💡 アドバイス")
    if summary['progress_pct'] < 30:
        print("  → SEO記事の投稿頻度を上げましょう")
        print("  → 高単価カテゴリ（投資・証券）の記事を増やしましょう")
    elif summary['progress_pct'] < 70:
        print("  → 順調です！アフィリエイトリンクの最適化を試みましょう")
        print("  → note有料記事の販売も始めてみましょう")
    else:
        print("  → 目標達成まであと少し！継続しましょう")

    print("="*60 + "\n")


if __name__ == "__main__":
    print_dashboard()
