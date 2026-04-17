"""
Amazon クローラー（PA-API → Gemini fallback → 静的データ fallback）

提供する公開 API:
  fetch_deals(category="gadget", count=5, force_refresh=False) -> list

キャッシュ: Supabase DB（x_automation/fetch_amazon_deals.py の load_cache / save_cache を使用）
           JSON キャッシュは使用しない（DBが単一の信頼できるソース）

カテゴリキー: gadget / audio / charging / camera / pc / smart_home / all
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT_DIR))
sys.path.insert(0, str(_ROOT_DIR / "x_automation"))

# fetch_amazon_deals.py の公開 API をそのまま再エクスポートする
from fetch_amazon_deals import (  # noqa: F401
    fetch_deals,
    fetch_via_paapi,
    fetch_via_gemini,
    load_cache,
    save_cache,
    CATEGORIES,
    ASSOCIATE_TAG,
)
