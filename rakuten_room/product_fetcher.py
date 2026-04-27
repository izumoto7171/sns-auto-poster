"""
楽天商品API — 女性ウケカテゴリの商品を取得
"""

import os
import json
import random
import requests
from datetime import datetime

RAKUTEN_APP_ID       = os.environ.get("RAKUTEN_APP_ID", "")
RAKUTEN_ACCESS_KEY   = os.environ.get("RAKUTEN_ACCESS_KEY", "")
RAKUTEN_AFFILIATE_ID = os.environ.get("RAKUTEN_AFFILIATE_ID", "")
# RAKUTEN_ORIGIN 未設定時はブログURLをデフォルト値として使用
RAKUTEN_ORIGIN       = os.environ.get("RAKUTEN_ORIGIN", "https://smart-earn-life.hateblo.jp")

# 一人暮らし男性向けカテゴリ（楽天ジャンルID）
MALE_SOLO_CATEGORIES = [
    {"name": "キッチン用品・調理器具",     "genre_id": "100804",  "tag": "キッチン"},
    {"name": "家電・生活家電",             "genre_id": "215783",  "tag": "家電"},
    {"name": "日用品・消耗品",             "genre_id": "551167",  "tag": "日用品"},
    {"name": "インスタント・レトルト食品", "genre_id": "116631",  "tag": "時短飯"},
    {"name": "コーヒー・飲料",             "genre_id": "400395",  "tag": "コーヒー"},
    {"name": "健康食品・プロテイン",       "genre_id": "100227",  "tag": "プロテイン"},
    {"name": "収納・インテリア雑貨",       "genre_id": "101164",  "tag": "収納"},
    {"name": "スイーツ・お菓子",           "genre_id": "408100",  "tag": "おやつ"},
]

# 1商品あたりの価格帯 (円)
PRICE_MIN = 500
PRICE_MAX = 8000


def fetch_products(count: int = 5) -> list[dict]:
    """
    ランダムカテゴリから一人暮らし男性向け商品を取得する。
    RAKUTEN_APP_ID が未設定の場合はモックデータを返す。
    """
    if not RAKUTEN_APP_ID:
        print("[product_fetcher] RAKUTEN_APP_ID 未設定 → モックデータを使用")
        return _mock_products(count)

    category = random.choice(MALE_SOLO_CATEGORIES)
    params = {
        "applicationId": RAKUTEN_APP_ID,
        "genreId":       category["genre_id"],
        "minPrice":      PRICE_MIN,
        "maxPrice":      PRICE_MAX,
        "sort":          "-reviewCount",
        "hits":          30,
        "imageFlag":     1,
        "format":        "json",
    }
    if RAKUTEN_ACCESS_KEY:
        params["accessKey"] = RAKUTEN_ACCESS_KEY
    if RAKUTEN_AFFILIATE_ID:
        params["affiliateId"] = RAKUTEN_AFFILIATE_ID

    try:
        res = requests.get(
            "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20220601",
            params=params,
            headers={"Origin": RAKUTEN_ORIGIN, "Referer": RAKUTEN_ORIGIN + "/"},
            timeout=10,
        )
        res.raise_for_status()
        items_raw = res.json().get("Items", [])
    except Exception as e:
        print(f"[product_fetcher] 楽天API エラー: {e}")
        return _mock_products(count)

    products = []
    for item_wrap in items_raw[:count]:
        item = item_wrap.get("Item", item_wrap)
        products.append({
            "name":          item.get("itemName", ""),
            "price":         item.get("itemPrice", 0),
            "url":           item.get("affiliateUrl") or item.get("itemUrl", ""),
            "shop":          item.get("shopName", ""),
            "review_count":  item.get("reviewCount", 0),
            "review_avg":    item.get("reviewAverage", 0.0),
            "image_url":     (item.get("mediumImageUrls") or [{"imageUrl": ""}])[0].get("imageUrl", ""),
            "category_name": category["name"],
            "category_tag":  category["tag"],
        })

    print(f"[product_fetcher] {category['name']} から {len(products)} 件取得")
    return products


def _mock_products(count: int) -> list[dict]:
    """APIキー未設定時のモック商品データ"""
    mocks = [
        {
            "name": "KOSE クリアターン ホワイト マスク (コラーゲン) 7枚",
            "price": 580,
            "url": "https://item.rakuten.co.jp/sample/mock001/",
            "shop": "コーセー公式",
            "review_count": 3200,
            "review_avg": 4.3,
            "image_url": "",
            "category_name": "スキンケア・基礎化粧品",
            "category_tag": "美容",
        },
        {
            "name": "バブ 薬用入浴剤 にごり浴 12錠入",
            "price": 780,
            "url": "https://item.rakuten.co.jp/sample/mock002/",
            "shop": "花王公式",
            "review_count": 5100,
            "review_avg": 4.5,
            "image_url": "",
            "category_name": "ボディケア・バスグッズ",
            "category_tag": "バス",
        },
        {
            "name": "uka ネイルオイル 13時間 5ml",
            "price": 1980,
            "url": "https://item.rakuten.co.jp/sample/mock003/",
            "shop": "uka公式",
            "review_count": 1800,
            "review_avg": 4.4,
            "image_url": "",
            "category_name": "コスメ・ネイル",
            "category_tag": "コスメ",
        },
    ]
    return mocks[:count]
