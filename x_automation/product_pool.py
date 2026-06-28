"""
Amazonアソシエイト商品プール

DB（amazon_products）+ static_products.json + amazon_deals.json を統合して
PRODUCT_POOL として公開する。
ハードコード商品は廃止し、product_rotator.py が毎日生成する商品を使う。
"""

import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

_ROOT_DIR = Path(__file__).parent.parent
_env_path = _ROOT_DIR / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

_TAG = os.getenv("AMAZON_ASSOCIATE_TAG", "smartearn22-22")


def _make_url(p: dict) -> str:
    """ASIN直リンクまたは検索URLを返す"""
    asin = p.get("asin", "").strip()
    if asin and len(asin) == 10:
        return f"https://www.amazon.co.jp/dp/{asin}?tag={_TAG}"
    url = p.get("amazon_url", "")
    if url:
        return url
    keyword = p.get("search_keyword", p.get("name", p.get("title", "")))
    if keyword:
        return f"https://www.amazon.co.jp/s?k={quote(keyword)}&tag={_TAG}"
    return ""


def _normalize(p: dict) -> dict:
    """各ソースの商品データを統一フォーマットに変換"""
    return {
        "asin": p.get("asin", "").strip(),
        "name": p.get("title", p.get("name", "")),
        "url": _make_url(p),
        "keywords": p.get("keywords", []),
        "search_keyword": p.get("search_keyword", ""),
        "discount_rate": p.get("discount_rate", 0),
        "image_url": p.get("image_url", ""),
        "category": p.get("category", ""),
        "why_viral": p.get("why_viral", ""),
        "story_hook": p.get("story_hook", ""),
    }


def _dedup_key(p: dict) -> str:
    """重複排除用キー（ASIN優先、なければ search_keyword / name）"""
    asin = p.get("asin", "").strip()
    if asin:
        return f"asin:{asin}"
    return f"kw:{p.get('search_keyword', '') or p.get('name', '')}"


def _load_from_db() -> list:
    """Supabase amazon_products テーブルから読み込む"""
    try:
        sys.path.insert(0, str(_ROOT_DIR))
        from db_client import db
        rows = db.get_amazon_deals(max_age_hours=24 * 30)
        if rows:
            return [_normalize(r) for r in rows]
    except Exception:
        pass
    return []


def _load_from_json() -> list:
    """static_products.json / amazon_deals.json からフォールバック読み込み"""
    json_paths = [
        Path(__file__).parent / "static_products.json",
        _ROOT_DIR / "data" / "static_products.json",
        Path(__file__).parent / "amazon_deals.json",
        _ROOT_DIR / "data" / "amazon_deals.json",
    ]
    products = []
    seen = set()
    for jp in json_paths:
        if not jp.exists():
            continue
        try:
            with open(jp, encoding="utf-8") as f:
                data = json.load(f)
            for p in data:
                norm = _normalize(p)
                key = _dedup_key(norm)
                if key not in seen and norm["url"]:
                    seen.add(key)
                    products.append(norm)
        except Exception:
            continue
    return products


def _build_pool() -> list:
    """DB → JSON の順で商品を収集し、重複排除して返す"""
    pool = []
    seen = set()

    for source_fn in (_load_from_db, _load_from_json):
        for p in source_fn():
            key = _dedup_key(p)
            if key not in seen and p["url"]:
                seen.add(key)
                pool.append(p)

    return pool


PRODUCT_POOL = _build_pool()
