"""
楽天商品API — 女性ウケカテゴリの商品を取得
"""

import os
import json
import random
import requests
from datetime import datetime

RAKUTEN_APP_ID       = os.environ.get("RAKUTEN_APP_ID", "")        # アプリケーションID (UUID)
RAKUTEN_ACCESS_KEY   = os.environ.get("RAKUTEN_ACCESS_KEY", "")    # アクセスキー (pk_...)
RAKUTEN_AFFILIATE_ID = os.environ.get("RAKUTEN_AFFILIATE_ID", "")  # アフィリエイトID

# 女性ウケカテゴリ（楽天ジャンルID）
FEMALE_CATEGORIES = [
    {"name": "スキンケア・基礎化粧品", "genre_id": "558885",  "tag": "美容"},
    {"name": "ボディケア・バスグッズ",  "genre_id": "558887",  "tag": "バス"},
    {"name": "コスメ・ネイル",          "genre_id": "558886",  "tag": "コスメ"},
    {"name": "ルームフレグランス",       "genre_id": "512830",  "tag": "香り"},
    {"name": "ヘアケア",               "genre_id": "558888",  "tag": "ヘア"},
    {"name": "おしゃれ小物・雑貨",      "genre_id": "101164",  "tag": "雑貨"},
    {"name": "スイーツ・お菓子",        "genre_id": "408100",  "tag": "スイーツ"},
    {"name": "キッチン用品",            "genre_id": "100804",  "tag": "キッチン"},
]

# 1商品あたりの価格帯 (円)
PRICE_MIN = 500
PRICE_MAX = 8000


def fetch_products(count: int = 5) -> list[dict]:
    """
    ランダムカテゴリから女性ウケ商品を取得する。
    RAKUTEN_APP_ID が未設定の場合はモックデータを返す。
    """
    if not RAKUTEN_APP_ID:
        print("[product_fetcher] RAKUTEN_APP_ID 未設定 → モックデータを使用")
        return _mock_products(count)

    category = random.choice(FEMALE_CATEGORIES)
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
            "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20170706",
            params=params,
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
