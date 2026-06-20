"""
Amazonアソシエイト商品プール

静的マスターデータ + static_products.json（ランキング自動収集分）を統合して
PRODUCT_POOL として公開する。
"""

import json
import os
from pathlib import Path

_ROOT_DIR = Path(__file__).parent.parent
_env_path = _ROOT_DIR / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

_TAG = os.getenv("AMAZON_ASSOCIATE_TAG", "smartearn22-22")

_STATIC_PRODUCTS = [
    {
        "asin": "B000P4D5HG",
        "name": "Hario V60 コーヒードリッパー 02 透明 VD-02T",
        "url": f"https://www.amazon.co.jp/dp/B000P4D5HG?tag={_TAG}",
        "keywords": ["コーヒー", "ドリッパー", "在宅ワーク", "カフェ"],
    },
    {
        "asin": "B01C4ZHXQ2",
        "name": "Kalita ウェーブドリッパー WDS-185 ステンレス製 燕職人手作り 2〜4人用",
        "url": f"https://www.amazon.co.jp/dp/B01C4ZHXQ2?tag={_TAG}",
        "keywords": ["コーヒー", "ドリッパー", "ステンレス", "日本製"],
    },
    {
        "asin": "B0000AN3QI",
        "name": "Bialetti ビアレッティ モカエキスプレス 直火式コーヒーメーカー 3カップ",
        "url": f"https://www.amazon.co.jp/dp/B0000AN3QI?tag={_TAG}",
        "keywords": ["コーヒー", "直火式", "エスプレッソ", "イタリア"],
    },
    {
        "asin": "B075K39RTZ",
        "name": "ネスプレッソ エッセンサ ミニ C30-BK-W カプセル式コーヒーメーカー",
        "url": f"https://www.amazon.co.jp/dp/B075K39RTZ?tag={_TAG}",
        "keywords": ["コーヒー", "カプセル式", "時短", "一人暮らし"],
    },
    {
        "asin": "B082L3B1NB",
        "name": "ポーレックス コーヒーミル2 セラミック 手挽き 日本製",
        "url": f"https://www.amazon.co.jp/dp/B082L3B1NB?tag={_TAG}",
        "keywords": ["コーヒー", "ミル", "手挽き", "日本製"],
    },
    {
        "asin": "B0051OOM68",
        "name": "BODUM ボダム CHAMBORD フレンチプレス コーヒーメーカー 350ml",
        "url": f"https://www.amazon.co.jp/dp/B0051OOM68?tag={_TAG}",
        "keywords": ["コーヒー", "フレンチプレス", "簡単", "一人暮らし"],
    },
]


def _load_dynamic_products() -> list:
    """static_products.json からランキング収集済み商品を読み込む"""
    json_paths = [
        Path(__file__).parent / "static_products.json",
        _ROOT_DIR / "data" / "static_products.json",
    ]
    for jp in json_paths:
        if jp.exists():
            try:
                with open(jp, encoding="utf-8") as f:
                    data = json.load(f)
                products = []
                for p in data:
                    asin = p.get("asin", "")
                    if not asin:
                        continue
                    products.append({
                        "asin": asin,
                        "name": p.get("title", p.get("name", "")),
                        "url": p.get("amazon_url", f"https://www.amazon.co.jp/dp/{asin}?tag={_TAG}"),
                        "keywords": p.get("keywords", []),
                        "discount_rate": p.get("discount_rate", 0),
                        "image_url": p.get("image_url", ""),
                    })
                return products
            except Exception:
                continue
    return []


# 静的 + 動的を統合（ASIN重複は静的を優先）
_dynamic = _load_dynamic_products()
_static_asins = {p["asin"] for p in _STATIC_PRODUCTS}
PRODUCT_POOL = _STATIC_PRODUCTS + [p for p in _dynamic if p["asin"] not in _static_asins]
