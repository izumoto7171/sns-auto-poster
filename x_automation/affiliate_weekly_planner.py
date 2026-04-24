"""
週次アフィリエイト投稿プランナー

A8・Amazon・楽天の今週の投稿済み商品と残り在庫を一覧表示する。
各システムのクールダウン状況を集約して「毎週違う商品」が担保されているか確認できる。

使い方:
  python3 affiliate_weekly_planner.py          # 今週のサマリー
  python3 affiliate_weekly_planner.py --week 2026-W18  # 特定週を表示
  python3 affiliate_weekly_planner.py --history        # 過去4週の履歴
"""
from __future__ import annotations

import json
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent
ROOT_DIR = BASE_DIR.parent

sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(BASE_DIR))


# ── ISO週ユーティリティ ───────────────────────────────────────────

def iso_week(dt: datetime | None = None) -> str:
    """datetime → 'YYYY-WXX' 形式の ISO週文字列"""
    d = dt or datetime.now()
    return f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}"


def week_range(week_str: str) -> tuple[datetime, datetime]:
    """'YYYY-WXX' → (月曜日 00:00, 日曜日 23:59) のタプル（ISO週準拠）"""
    year, w = week_str.split("-W")
    monday = datetime.strptime(f"{year}-W{int(w):02d}-1", "%G-W%V-%u")
    sunday = monday + timedelta(days=6, hours=23, minutes=59)
    return monday, sunday


# ── 各ソースから履歴を読み込む ────────────────────────────────────

def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_a8_this_week(week_str: str) -> list[dict]:
    """A8履歴（a8_programs_history.json）から今週投稿された案件を返す"""
    monday, sunday = week_range(week_str)
    mon_iso = monday.isoformat()
    sun_iso = sunday.isoformat()

    history_path = ROOT_DIR / "money_agent" / "a8_programs_history.json"
    data = _load_json(history_path, [])
    if isinstance(data, dict):
        data = data.get("entries", [])

    result = []
    for item in data:
        posted_at = item.get("last_posted_at", "")
        if mon_iso <= posted_at <= sun_iso:
            result.append({
                "name":      item.get("name", ""),
                "reward":    item.get("reward", ""),
                "posted_at": posted_at[:16],
            })
    return sorted(result, key=lambda x: x["posted_at"])


def load_a8_available(cooldown_days: int = 30) -> list[dict]:
    """クールダウン中でない A8 案件を返す"""
    cutoff = (datetime.now() - timedelta(days=cooldown_days)).isoformat()
    history_path = ROOT_DIR / "money_agent" / "a8_programs_history.json"
    data = _load_json(history_path, [])
    if isinstance(data, dict):
        data = data.get("entries", [])

    result = []
    for item in data:
        if (item.get("last_posted_at") or "") < cutoff:
            result.append({
                "name":   item.get("name", ""),
                "reward": item.get("reward", ""),
            })
    return result


def load_amazon_this_week(week_str: str) -> list[dict]:
    """Amazon履歴（product_history.json）から今週投稿された商品を返す"""
    monday, sunday = week_range(week_str)
    mon_iso = monday.isoformat()
    sun_iso = sunday.isoformat()

    data = _load_json(BASE_DIR / "product_history.json", {"entries": []})
    entries = data.get("entries", []) if isinstance(data, dict) else []

    result = []
    for item in entries:
        posted_at = item.get("last_posted_at", "")
        if mon_iso <= posted_at <= sun_iso:
            result.append({
                "title":     item.get("title", item.get("key", "")),
                "posted_at": posted_at[:16],
            })
    return sorted(result, key=lambda x: x["posted_at"])


def load_amazon_available(cooldown_days: int = 14) -> list[dict]:
    """クールダウン中でない Amazon 商品を返す"""
    cutoff = (datetime.now() - timedelta(days=cooldown_days)).isoformat()
    data = _load_json(BASE_DIR / "product_history.json", {"entries": []})
    entries = data.get("entries", []) if isinstance(data, dict) else []
    used_keys = {e["key"] for e in entries if (e.get("last_posted_at") or "") >= cutoff}

    try:
        from fetch_amazon_deals import _STATIC_PRODUCTS
        return [
            {"title": p["title"], "asin": p.get("asin", "")}
            for p in _STATIC_PRODUCTS
            if p.get("asin", "") not in used_keys
        ]
    except Exception:
        return []


def load_rakuten_this_week(week_str: str) -> list[dict]:
    """楽天履歴（rakuten_post_history.json）から今週投稿された商品を返す"""
    monday, sunday = week_range(week_str)
    mon_iso = monday.isoformat()
    sun_iso = sunday.isoformat()

    entries = _load_json(BASE_DIR / "rakuten_post_history.json", [])

    result = []
    for item in entries:
        posted_at = item.get("last_posted_at", "")
        if mon_iso <= posted_at <= sun_iso:
            result.append({
                "name":      item.get("name", ""),
                "category":  item.get("category", ""),
                "posted_at": posted_at[:16],
            })
    return sorted(result, key=lambda x: x["posted_at"])


def load_rakuten_available(cooldown_days: int = 7) -> list[dict]:
    """クールダウン中でない楽天カテゴリを返す"""
    cutoff = (datetime.now() - timedelta(days=cooldown_days)).isoformat()
    entries = _load_json(BASE_DIR / "rakuten_post_history.json", [])
    used_categories = {
        e["category"] for e in entries
        if (e.get("last_posted_at") or "") >= cutoff
    }

    try:
        sys.path.insert(0, str(ROOT_DIR))
        from money_agent.rakuten_product_article import ARTICLE_CATEGORIES
        return [
            {"category": c["name"]}
            for c in ARTICLE_CATEGORIES
            if c["name"] not in used_categories
        ]
    except Exception:
        return []


# ── 週次サマリー表示 ─────────────────────────────────────────────

def print_weekly_summary(week_str: str) -> None:
    monday, sunday = week_range(week_str)
    W = 60
    is_current = week_str == iso_week()
    label = "今週" if is_current else week_str

    print("=" * W)
    print(f"  アフィリエイト週次プラン [{label}]")
    print(f"  {monday.strftime('%Y/%m/%d')} (月) ～ {sunday.strftime('%Y/%m/%d')} (日)")
    print("=" * W)

    # A8
    a8_posted    = load_a8_this_week(week_str)
    a8_available = load_a8_available() if is_current else []
    print(f"\n■ A8アフィリエイト  (クールダウン: 30日)")
    print(f"  今週投稿済み: {len(a8_posted)}件")
    for p in a8_posted:
        print(f"    [{p['posted_at']}] {p['name'][:35]} ({p['reward'][:25]})")
    if is_current and a8_available:
        print(f"  投稿可能: {len(a8_available)}件")
        for p in a8_available[:5]:
            print(f"    ・{p['name'][:35]}")
        if len(a8_available) > 5:
            print(f"    ...他 {len(a8_available) - 5}件")

    # Amazon
    amz_posted    = load_amazon_this_week(week_str)
    amz_available = load_amazon_available() if is_current else []
    print(f"\n■ Amazon商品  (クールダウン: 14日)")
    print(f"  今週投稿済み: {len(amz_posted)}件")
    for p in amz_posted:
        print(f"    [{p['posted_at']}] {p['title'][:40]}")
    if is_current and amz_available:
        print(f"  投稿可能: {len(amz_available)}件")
        for p in amz_available[:5]:
            print(f"    ・{p['title'][:40]}")

    # 楽天
    raku_posted    = load_rakuten_this_week(week_str)
    raku_available = load_rakuten_available() if is_current else []
    print(f"\n■ 楽天市場  (クールダウン: 7日)")
    print(f"  今週投稿済み: {len(raku_posted)}件")
    for p in raku_posted:
        print(f"    [{p['posted_at']}] {p['name'][:35]} [{p['category']}]")
    if is_current and raku_available:
        print(f"  投稿可能カテゴリ: {len(raku_available)}件")
        for c in raku_available:
            print(f"    ・{c['category']}")

    total_posted = len(a8_posted) + len(amz_posted) + len(raku_posted)
    print(f"\n  合計投稿済み: {total_posted}件  "
          f"(A8:{len(a8_posted)} / Amazon:{len(amz_posted)} / 楽天:{len(raku_posted)})")
    print("=" * W)


def print_history(weeks: int = 4) -> None:
    """過去N週の投稿履歴を表示"""
    print(f"\n過去 {weeks} 週間のアフィリエイト投稿履歴\n")
    for i in range(weeks - 1, -1, -1):
        dt = datetime.now() - timedelta(weeks=i)
        wk = iso_week(dt)
        a8   = load_a8_this_week(wk)
        amz  = load_amazon_this_week(wk)
        raku = load_rakuten_this_week(wk)
        label = "← 今週" if i == 0 else ""
        print(f"  [{wk}] A8:{len(a8)}件 / Amazon:{len(amz)}件 / 楽天:{len(raku)}件  {label}")
        for p in a8:
            print(f"          A8    {p['name'][:30]}")
        for p in amz:
            print(f"          Amazon {p['title'][:30]}")
        for p in raku:
            print(f"          楽天  {p['name'][:30]} [{p['category']}]")
    print()


# ── CLI ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="週次アフィリエイト投稿プランナー")
    parser.add_argument("--week",    default=None, help="対象週 (例: 2026-W18)")
    parser.add_argument("--history", action="store_true", help="過去4週の履歴を表示")
    parser.add_argument("--weeks",   type=int, default=4, help="--history で表示する週数")
    args = parser.parse_args()

    if args.history:
        print_history(weeks=args.weeks)
    else:
        week_str = args.week or iso_week()
        print_weekly_summary(week_str)


if __name__ == "__main__":
    main()
