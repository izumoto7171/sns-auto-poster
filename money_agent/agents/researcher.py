"""
リサーチャーエージェント
CEOの戦略に基づき、今日狙うべきキーワードを選定する
"""
import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent


def _load_used_keywords() -> list:
    f = BASE_DIR / "data" / "used_keywords.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def run(state: dict, slot: int = 0) -> dict:
    """
    リサーチャー実行
    slot: 0=メイン記事, 1=サブ記事A, 2=サブ記事B

    Returns: {"keyword": ..., "category": ..., "affiliates": [...]}
    """
    print(f"  🔍 [Researcher-{slot}] キーワード選定中...")

    from money_agent.keywords_db import get_next_keyword, get_affiliates_for_category

    analyst_report = state.get("analyst_report", {})
    top_categories = analyst_report.get("top_categories", [])
    avoid_categories = analyst_report.get("avoid_categories", [])

    used_keywords = _load_used_keywords()

    # スロットごとに異なるカテゴリを優先
    preferred_category = None
    if top_categories:
        # slot 0 → top_categories[0], slot 1 → top_categories[1], etc.
        idx = slot % len(top_categories)
        preferred_category = top_categories[idx]

    kw_data = get_next_keyword(
        used_keywords=used_keywords,
        preferred_category=preferred_category,
    )

    affiliates = get_affiliates_for_category(kw_data["category"])

    print(f"  ✅ [Researcher-{slot}] 「{kw_data['keyword']}」(カテゴリ: {kw_data['category']})")

    return {
        "slot": slot,
        "keyword": kw_data["keyword"],
        "category": kw_data["category"],
        "intent": kw_data.get("intent", ""),
        "affiliates": affiliates,
    }
