"""
楽天市場 API クローラー（24時間 JSON キャッシュ付き）

提供する公開 API:
  fetch_products(genre_id, hits=10) -> list

キャッシュ先: money_agent/rakuten_product_cache.json（KV モード、TTL 24h）
"""
from __future__ import annotations

import os
import sys
import requests
from pathlib import Path

_ROOT_DIR   = Path(__file__).parent.parent
_CACHE_PATH = _ROOT_DIR / "money_agent" / "rakuten_product_cache.json"
_CACHE_TTL  = 60 * 60 * 24  # 24時間（秒）

sys.path.insert(0, str(_ROOT_DIR))
from crawlers.cache_manager import CacheManager

_cache = CacheManager(_CACHE_PATH, ttl=_CACHE_TTL)

RAKUTEN_APP_ID       = os.environ.get("RAKUTEN_APP_ID", "")
RAKUTEN_ACCESS_KEY   = os.environ.get("RAKUTEN_ACCESS_KEY", "")
RAKUTEN_AFFILIATE_ID = os.environ.get("RAKUTEN_AFFILIATE_ID", "")
RAKUTEN_SEARCH_URL   = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20220601"
# RAKUTEN_ORIGIN 未設定時はブログURLをデフォルト値として使用（アプリ登録済みOrigin）
# 楽天OpenAPIはリファラー制限を Origin + Referer 両ヘッダーで検証する
RAKUTEN_ORIGIN       = os.environ.get("RAKUTEN_ORIGIN", "") or "https://smart-earn-life.hateblo.jp"


def fetch_products(genre_id: str, hits: int = 10) -> list:
    """
    楽天市場 API で人気商品を取得する。24時間 JSON キャッシュ付き。

    Returns:
        商品 dict のリスト。各要素のキー:
          name, price, url, shop, review_count, review_avg, image_url, catchcopy
    """
    cache_key = f"{genre_id}_{hits}"

    # キャッシュヒット判定
    cached = _cache.kv_get(cache_key)
    if cached is not None:
        print(f"[rakuten] キャッシュヒット (genre_id={genre_id})")
        return cached

    if not RAKUTEN_APP_ID:
        print("[rakuten] RAKUTEN_APP_ID 未設定")
        # 期限切れでもキャッシュがあれば代替として返す
        raw_entry = _cache.kv_get_raw(cache_key)
        if raw_entry:
            return raw_entry.get("value", [])
        return []

    params: dict = {
        "applicationId": RAKUTEN_APP_ID,
        "accessKey":     RAKUTEN_ACCESS_KEY,
        "genreId":       genre_id,
        "sort":          "-reviewCount",
        "hits":          hits,
        "imageFlag":     1,
        "format":        "json",
    }
    if RAKUTEN_AFFILIATE_ID:
        params["affiliateId"] = RAKUTEN_AFFILIATE_ID

    try:
        res = requests.get(
            RAKUTEN_SEARCH_URL,
            params=params,
            headers={"Origin": RAKUTEN_ORIGIN, "Referer": RAKUTEN_ORIGIN.rstrip("/") + "/"},
            timeout=15,
        )
        res.raise_for_status()
        items_raw = res.json().get("Items", [])
    except Exception as e:
        print(f"[rakuten] 商品取得エラー: {e}")
        # エラー時は期限切れキャッシュで代替
        raw_entry = _cache.kv_get_raw(cache_key)
        if raw_entry:
            return raw_entry.get("value", [])
        return []

    products = []
    for item_wrap in items_raw:
        item = item_wrap.get("Item", item_wrap)
        url  = item.get("affiliateUrl") or item.get("itemUrl", "")
        products.append({
            "name":         item.get("itemName", "")[:60],
            "price":        item.get("itemPrice", 0),
            "url":          url,
            "shop":         item.get("shopName", ""),
            "review_count": item.get("reviewCount", 0),
            "review_avg":   item.get("reviewAverage", 0.0),
            "image_url":    (item.get("mediumImageUrls") or [{"imageUrl": ""}])[0].get("imageUrl", ""),
            "catchcopy":    item.get("catchcopy", ""),
        })

    print(f"[rakuten] {len(products)}件取得 (genre_id={genre_id})")

    try:
        _cache.kv_set(cache_key, products)
    except Exception as e:
        print(f"[rakuten] キャッシュ保存失敗: {e}")

    return products


def fetch_products_by_keyword(keyword: str, hits: int = 10) -> list:
    """
    楽天市場 API でキーワード検索する（ジャンルIDなし）。
    weekly_trend_hunter が生成したキーワードで呼び出す用途。
    """
    cache_key = f"kw_{keyword}_{hits}"

    cached = _cache.kv_get(cache_key)
    if cached is not None:
        print(f"[rakuten] キャッシュヒット (keyword={keyword})")
        return cached

    if not RAKUTEN_APP_ID:
        print("[rakuten] RAKUTEN_APP_ID 未設定（キーワード検索スキップ）")
        return []

    params: dict = {
        "applicationId": RAKUTEN_APP_ID,
        "accessKey":     RAKUTEN_ACCESS_KEY,
        "keyword":       keyword,
        "sort":          "-reviewCount",
        "hits":          hits,
        "imageFlag":     1,
        "format":        "json",
    }
    if RAKUTEN_AFFILIATE_ID:
        params["affiliateId"] = RAKUTEN_AFFILIATE_ID

    try:
        res = requests.get(
            RAKUTEN_SEARCH_URL,
            params=params,
            headers={"Origin": RAKUTEN_ORIGIN, "Referer": RAKUTEN_ORIGIN.rstrip("/") + "/"},
            timeout=15,
        )
        res.raise_for_status()
        items_raw = res.json().get("Items", [])
    except Exception as e:
        print(f"[rakuten] キーワード検索エラー ({keyword}): {e}")
        return []

    products = []
    for item_wrap in items_raw:
        item = item_wrap.get("Item", item_wrap)
        url  = item.get("affiliateUrl") or item.get("itemUrl", "")
        products.append({
            "name":         item.get("itemName", "")[:60],
            "price":        item.get("itemPrice", 0),
            "url":          url,
            "shop":         item.get("shopName", ""),
            "review_count": item.get("reviewCount", 0),
            "review_avg":   item.get("reviewAverage", 0.0),
            "image_url":    (item.get("mediumImageUrls") or [{"imageUrl": ""}])[0].get("imageUrl", ""),
            "catchcopy":    item.get("catchcopy", ""),
            "search_keyword": keyword,
        })

    print(f"[rakuten] {len(products)}件取得 (keyword={keyword})")

    try:
        _cache.kv_set(cache_key, products)
    except Exception as e:
        print(f"[rakuten] キャッシュ保存失敗: {e}")

    return products
