"""
Amazonタイムセール・おすすめ商品の取得
PA-API が使えるときは PA-API を使用、なければ Gemini で代替生成

使い方:
  python3.11 x_automation/fetch_amazon_deals.py                   # ガジェット5件
  python3.11 x_automation/fetch_amazon_deals.py --category all    # 全カテゴリ
  python3.11 x_automation/fetch_amazon_deals.py --count 10        # 10件取得

出力: x_automation/amazon_deals.json
"""

import os
import re
import sys
import json
import time
import argparse
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR  = Path(__file__).parent
ROOT_DIR  = BASE_DIR.parent

# .env 読み込み
env_path = ROOT_DIR / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

# Supabase クライアント
sys.path.insert(0, str(ROOT_DIR))
from db_client import db

ASSOCIATE_TAG = os.getenv("AMAZON_ASSOCIATE_TAG", "smartearn22-22")

# バリデーション結果キャッシュ（ASIN → last_validated_at）
_VALIDATION_CACHE_PATH = BASE_DIR / "validation_cache.json"
_VALIDATION_TTL_HOURS  = 24


def _load_validation_cache() -> dict:
    """バリデーションキャッシュを読み込む。失敗時は空dictを返す。"""
    try:
        if _VALIDATION_CACHE_PATH.exists():
            return json.loads(_VALIDATION_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  ⚠️  バリデーションキャッシュ読み込み失敗（無視して続行）: {e}")
    return {}


def _save_validation_cache(cache: dict) -> None:
    """バリデーションキャッシュを保存する。失敗時は警告のみ。"""
    try:
        _VALIDATION_CACHE_PATH.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        print(f"  ⚠️  バリデーションキャッシュ書き込み失敗（無視して続行）: {e}")


def _is_validation_fresh(asin: str, cache: dict) -> bool:
    """指定ASINが TTL 以内に検証済みか確認する。"""
    if not asin or asin not in cache:
        return False
    try:
        last = datetime.fromisoformat(cache[asin])
        return datetime.now() - last < timedelta(hours=_VALIDATION_TTL_HOURS)
    except Exception:
        return False


def _mark_validated(asin: str, cache: dict) -> None:
    """ASINの検証日時をキャッシュに記録する（dict を in-place 更新）。"""
    if asin:
        cache[asin] = datetime.now().isoformat()


def _make_search_url(keyword: str) -> str:
    """Amazon検索URL生成（urllib.parse.urlencode でクエリを安全に構築）"""
    from urllib.parse import urlencode, urlunparse
    query = urlencode({"k": keyword, "tag": ASSOCIATE_TAG})
    return urlunparse(("https", "www.amazon.co.jp", "/s", "", query, ""))


def _make_dp_url(asin: str) -> str:
    """ASIN から商品直リンクURLを安全に生成する"""
    from urllib.parse import urlencode, urlunparse
    query = urlencode({"tag": ASSOCIATE_TAG})
    return urlunparse(("https", "www.amazon.co.jp", f"/dp/{asin}", "", query, ""))


def _resolve_asin(keyword: str) -> str:
    """
    Amazon検索結果から最初の商品のASINを取得する。
    取得できた場合は商品直リンクURLを返し、失敗時は検索URLを返す。
    """
    import re
    import urllib.request
    from urllib.parse import urlencode, urlunparse

    # 検索URL は urlencode で安全に構築（スペース等を正しくエンコード）
    search_url = urlunparse(("https", "www.amazon.co.jp", "/s", "",
                              urlencode({"k": keyword}), ""))
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ja-JP,ja;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        req = urllib.request.Request(search_url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        # data-asin 属性から10桁のASINを取得（広告除く：最初の非空ASINを使用）
        asins = re.findall(r'data-asin="([A-Z0-9]{10})"', html)
        for asin in asins:
            if asin:
                # ASIN ベースのURLを urllib.parse で安全に生成
                return _make_dp_url(asin)
    except Exception as e:
        print(f"  ⚠️  ASIN解決失敗 ({keyword[:20]}): {e}")

    # 失敗時は検索URLにフォールバック
    return _make_search_url(keyword)


def check_amazon_url_alive(url: str) -> bool:
    """
    Amazon商品URLが生存しているか確認する（投稿直前チェック用）。

    requests.get() で実際にアクセスし、以下の条件で判定する:
    - 404 → False（商品ページが削除済み）
    - RequestException（タイムアウト・接続失敗）→ False
    - 503 / 429（Bot判定によるブロック）→ True（商品は存在する可能性が高い）
    - その他 2xx / 3xx → True

    Args:
        url: チェック対象のAmazon商品URL

    Returns:
        True=有効（投稿続行）、False=無効（スキップ対象）
    """
    if not url:
        return False
    if "/s?" in url:  # 検索URLは常に有効（ASINなしのfallback）
        return True

    try:
        import requests
        from requests.exceptions import RequestException

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "ja-JP,ja;q=0.9",
        }
        resp = requests.get(url, headers=headers, timeout=5, allow_redirects=True)
        resp.close()

        if resp.status_code == 404:
            return False
        # 503/429 はBot判定によるブロック → 商品は存在する可能性が高い
        return True

    except Exception:
        return False


_ERROR_TITLES = (
    "ページが見つかりません",
    "page not found",
    "sorry, we just need to make sure",
    "robot check",
    "access denied",
    "404",
)

def _validate_amazon_url(url: str) -> tuple[bool, str]:
    """
    Amazon商品URLが実際にアクセス可能か確認する。

    Amazon は HEAD を 405 で拒否するため GET + stream を使用し、
    レスポンスの先頭 4KB だけ読んでタイトルを確認する。

    Returns:
        (is_valid: bool, asin: str)
        - is_valid: True=有効, False=無効（スキップ対象）
        - asin: URLから抽出した ASIN（再解決用）
    """
    import re

    if not url:
        return False, ""

    # 検索URLは常に有効（ASINなしのfallback）
    if "/s?" in url:
        return True, ""

    # ASINを抽出
    m = re.search(r"/dp/([A-Z0-9]{10})", url)
    asin = m.group(1) if m else ""

    try:
        import requests
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "ja-JP,ja;q=0.9",
            # 圧縮を無効にして生のHTMLを受け取る
            "Accept-Encoding": "identity",
        }
        resp = requests.get(
            url, headers=headers, allow_redirects=True, timeout=8, stream=True
        )

        # 503/429 はbot判定によるブロックで商品は存在する可能性が高い → 通す
        if resp.status_code in (503, 429):
            resp.close()
            return True, asin

        # 明確な404はスキップ
        if resp.status_code == 404:
            resp.close()
            return False, asin

        # 先頭8KBだけ読んでタイトルを確認（全body取得を避ける）
        chunk = next(resp.iter_content(chunk_size=8192), b"").decode("utf-8", errors="ignore")
        resp.close()

        title_m = re.search(r"<title>(.*?)</title>", chunk, re.IGNORECASE)
        title = title_m.group(1).lower() if title_m else ""

        if any(t in title for t in _ERROR_TITLES):
            return False, asin

        return True, asin

    except Exception:
        # タイムアウト等は通す（投稿機会損失を防ぐ）
        return True, asin


# ─────────────────────────────────────────
# 購買意欲（インテント）スコアリング
# 0.5%の成約率を超えるために「今すぐ買う層」に届くキーワードを優先する
#
# 【高インテントキーワードとは】
# - 比較/ランキング系: 「おすすめ」「比較」「最強」→ 購入検討中
# - 問題解決系: 「ノイズキャンセリング 電車」→ 具体的な用途で探している
# - 期間限定系: 「セール」「タイムセール」「値下がり」→ 購買トリガーが強い
# - スペック指定系: 「USB-C 65W」「Bluetooth5.3」→ 仕様比較フェーズ
# ─────────────────────────────────────────
HIGH_INTENT_KEYWORDS = {
    # 比較・ランキング（スコア高）
    "おすすめ": 3, "ランキング": 3, "比較": 3, "最強": 2, "コスパ": 3, "選び方": 2,
    "口コミ": 2, "レビュー": 2, "評判": 2, "人気": 2,
    # 期間限定・価格（購買トリガー）
    "セール": 3, "タイムセール": 3, "値下がり": 3, "割引": 3, "安い": 2, "お得": 2,
    "限定": 2, "特価": 3,
    # 問題解決系（具体的なニーズ）
    "充電できない": 2, "バッテリー 持ち": 2, "ノイズキャンセリング": 2,
    "軽量": 2, "防水": 2, "コンパクト": 2, "小型": 2,
    # スペック指定（購入直前フェーズ）
    "USB-C": 2, "Bluetooth": 1, "MagSafe": 2, "ワイヤレス": 1, "急速充電": 2,
    "GaN": 3, "4K": 2, "HDR": 1,
}

LOW_INTENT_KEYWORDS = {
    # 情報収集フェーズ（購入意図が低い）
    "とは": -1, "仕組み": -1, "歴史": -2, "なぜ": -1,
}


def score_purchase_intent(product: dict) -> int:
    """
    商品の購買意欲スコアを算出する（高いほど成約率が高い層に刺さる）

    スコア計算:
    - タイトル・特徴のキーワードマッチ
    - 割引率（10%以上で+加点）
    - 価格帯（2,000〜15,000円が最も衝動買いされやすい）

    Returns:
        int: スコア（0〜100）
    """
    score = 50  # ベーススコア

    text = " ".join([
        product.get("title", ""),
        product.get("brand", ""),
        product.get("why_viral", ""),
        product.get("story_hook", ""),
        " ".join(product.get("features", [])),
        product.get("keyword", ""),
    ]).lower()

    for kw, pts in HIGH_INTENT_KEYWORDS.items():
        if kw.lower() in text:
            score += pts

    for kw, pts in LOW_INTENT_KEYWORDS.items():
        if kw.lower() in text:
            score += pts  # pts は負値

    # 割引率ボーナス
    discount = product.get("discount_rate", 0)
    if discount >= 30:
        score += 15
    elif discount >= 20:
        score += 10
    elif discount >= 10:
        score += 5

    # 価格帯ボーナス（衝動買いゾーン: 2,000〜15,000円）
    price = product.get("price", {}).get("amount", 0)
    if 2000 <= price <= 15000:
        score += 10
    elif price < 2000:
        score += 3   # 安すぎると「アフィ案件っぽい」と警戒される
    elif price > 50000:
        score -= 5   # 高額商品はXからの即決が難しい

    return max(0, min(100, score))


def sort_by_intent(products: list) -> list:
    """商品リストを購買意欲スコアの高い順にソートして返す"""
    for p in products:
        p["intent_score"] = score_purchase_intent(p)
    return sorted(products, key=lambda x: x["intent_score"], reverse=True)


# 一人暮らし男性向けカテゴリ定義
CATEGORIES = {
    "gadget":       {"label": "ガジェット・家電",   "keywords": ["ワイヤレスイヤホン", "スマート家電", "モバイルバッテリー", "USB充電器"], "search_index": "Electronics"},
    "kitchen":      {"label": "キッチン家電",       "keywords": ["電気圧力鍋", "炊飯器", "電子レンジ", "トースター"], "search_index": "Kitchen"},
    "cooking_tools":{"label": "調理器具",           "keywords": ["フライパン", "包丁", "まな板", "シリコンスチーマー"], "search_index": "Kitchen"},
    "cleaning":     {"label": "掃除・生活家電",     "keywords": ["コードレス掃除機", "ロボット掃除機", "食洗機"],     "search_index": "Appliances"},
    "daily_goods":  {"label": "日用品・消耗品",     "keywords": ["節水シャワーヘッド", "消臭剤", "収納ボックス"],     "search_index": "HealthPersonalCare"},
    "food":         {"label": "食品・飲料",         "keywords": ["冷凍食品", "インスタント", "プロテイン"],           "search_index": "Grocery"},
    "audio":        {"label": "オーディオ",         "keywords": ["ワイヤレスイヤホン", "ノイズキャンセリング"],       "search_index": "Electronics"},
    "smart_home":   {"label": "スマートホーム",     "keywords": ["スマートスピーカー", "スマート電球", "温湿度計"],   "search_index": "Electronics"},
    "pc":           {"label": "PC・デスク環境",     "keywords": ["モニター", "USBハブ", "ウェブカメラ"],             "search_index": "Computers"},
}


# ─────────────────────────────────────────
# PA-API で取得
# ─────────────────────────────────────────
def fetch_via_paapi(category: str, count: int) -> list:
    """Amazon PA-API でタイムセール商品を取得"""
    access_key    = os.getenv("AMAZON_ACCESS_KEY")
    secret_key    = os.getenv("AMAZON_SECRET_KEY")

    if not access_key or not secret_key:
        return []

    try:
        from amazon_paapi import AmazonApi

        cat_info = CATEGORIES.get(category, CATEGORIES["gadget"])
        amazon = AmazonApi(access_key, secret_key, ASSOCIATE_TAG, "JP")

        products = []
        for keyword in cat_info["keywords"]:
            result = amazon.search_items(
                keywords=keyword,
                search_index=cat_info["search_index"],
                item_count=min(count, 5),
                resources=[
                    "ItemInfo.Title",
                    "ItemInfo.Features",
                    "Offers.Listings.Price",
                    "Offers.Listings.SavingBasis",
                    "Offers.Summaries.OfferCount",
                    "Images.Primary.Large",
                    "DetailPageURL",  # アフィリエイトタグ付き公式URL（ShortUrl相当）
                ],
                min_saving_percent=10,  # 10%以上割引のみ
            )

            if not result or not result.items:
                continue

            for item in result.items:
                try:
                    asin  = item.asin
                    title = item.item_info.title.display_value if item.item_info else ""
                    if not title:
                        continue

                    price_info = None
                    discount_rate = 0
                    if item.offers and item.offers.listings:
                        listing = item.offers.listings[0]
                        if listing.price:
                            price_info = {
                                "amount":   listing.price.amount,
                                "currency": listing.price.currency,
                                "display":  listing.price.display_amount,
                            }
                        if listing.saving_basis and listing.price:
                            original = listing.saving_basis.amount
                            current  = listing.price.amount
                            if original and current and original > 0:
                                discount_rate = int((original - current) / original * 100)

                    image_url = ""
                    if item.images and item.images.primary and item.images.primary.large:
                        image_url = item.images.primary.large.url

                    features = []
                    if item.item_info and item.item_info.features:
                        features = item.item_info.features.display_values[:3]

                    # PA-API の DetailPageURL を優先（アフィリエイトタグ込みの公式URL）
                    # 取得できない場合は /dp/ASIN 形式で urllib.parse を使って構築
                    detail_url = getattr(item, "detail_page_url", None)
                    amazon_url = detail_url if detail_url else _make_dp_url(asin)

                    products.append({
                        "asin":          asin,
                        "title":         title,
                        "price":         price_info,
                        "discount_rate": discount_rate,
                        "category":      cat_info["label"],
                        "keyword":       keyword,
                        "features":      features,
                        "image_url":     image_url,
                        "amazon_url":    amazon_url,
                        "source":        "pa-api",
                        "fetched_at":    datetime.now().isoformat(),
                    })

                    if len(products) >= count:
                        break

                except Exception as e:
                    print(f"⚠️  商品パースエラー: {e}")
                    continue

            if len(products) >= count:
                break

            time.sleep(1)  # PA-APIのレートリミット対策

        return products[:count]

    except ImportError:
        print("⚠️  python-amazon-paapi 未インストール → Gemini fallbackを使用")
        return []
    except Exception as e:
        print(f"⚠️  PA-APIエラー: {e} → Gemini fallbackを使用")
        return []


# ─────────────────────────────────────────
# Gemini で代替生成（PA-API不使用時）
# ─────────────────────────────────────────
def fetch_via_gemini(category: str, count: int) -> list:
    """Gemini APIで今日おすすめのガジェット商品を生成（PA-APIなし時のfallback）"""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ GEMINI_API_KEY 未設定")
        return []

    cat_info = CATEGORIES.get(category, CATEGORIES["gadget"])
    today    = datetime.now().strftime("%Y年%m月%d日")

    prompt = f"""
あなたはAmazon Japanのガジェット専門バイヤーです。
{today}時点でAmazonで実際に販売されている商品を{count}件教えてください。

カテゴリ: {cat_info['label']}（{', '.join(cat_info['keywords'])}）

以下のJSON配列のみ出力（説明文不要）:
[
  {{
    "asin": "AmazonのASIN（10桁の英数字、例: B0B96T9CBY）。正確にわかる場合のみ入力、不明なら空文字",
    "search_keyword": "Amazon検索に使う短いキーワード（ブランド名+商品種別+スペック）",
    "title": "商品の表示タイトル（わかりやすく簡潔に）",
    "brand": "メーカー名",
    "price_yen": 価格（整数）,
    "original_price_yen": 定価（整数、セールでなければprice_yenと同じ）,
    "discount_rate": 割引率（0〜80の整数）,
    "category": "{cat_info['label']}",
    "features": ["特徴1", "特徴2", "特徴3"],
    "why_viral": "ガジェット好きがこの商品に反応する理由（50文字以内）",
    "story_hook": "思わずクリックしたくなる導入一文（30文字以内）"
  }}
]

条件:
- 実際にAmazon Japanで販売されている商品のみ（架空の商品は禁止）
- ASINが確実にわかる商品を優先する（有名ブランドの主力モデル等）
- ガジェット好き（20〜40代男性）が「これは！」と思う商品
- 割引率が高いものや、コスパが高い商品を優先
- JSON以外は出力しない
"""

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        resp   = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt,
        )
        raw = resp.text.strip()

        # JSONブロック抽出
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        items = json.loads(raw)
        products = []

        for item in items[:count]:
            keyword = item.get("search_keyword", item.get("title", ""))
            price   = item.get("price_yen", 0)
            orig    = item.get("original_price_yen", price)

            # GeminiからASINが得られた場合は直リンク、なければ検索URL
            asin = item.get("asin", "").strip()
            if asin and re.match(r'^[A-Z0-9]{10}$', asin):
                amazon_url = _make_dp_url(asin)
                print(f"  ✅ ASIN直リンク: {asin} → {keyword[:25]}...")
            elif keyword:
                # CIではAmazonのbot検出でASINスクレイピングが失敗するため検索URLを使用
                amazon_url = _make_search_url(keyword)
                print(f"  🔍 検索URL使用: {keyword[:30]}...")
            else:
                amazon_url = ""

            products.append({
                "search_keyword":  keyword,
                "title":           item.get("title", ""),
                "brand":           item.get("brand", ""),
                "price": {
                    "amount":   price,
                    "currency": "JPY",
                    "display":  f"¥{price:,}",
                },
                "original_price": {
                    "amount":  orig,
                    "display": f"¥{orig:,}",
                },
                "discount_rate": item.get("discount_rate", 0),
                "category":      item.get("category", cat_info["label"]),
                "features":      item.get("features", []),
                "why_viral":     item.get("why_viral", ""),
                "story_hook":    item.get("story_hook", ""),
                "amazon_url":    amazon_url,
                "source":        "gemini-generated",
                "fetched_at":    datetime.now().isoformat(),
            })

        return products

    except json.JSONDecodeError as e:
        print(f"❌ JSONパースエラー: {e}")
        print(f"   Raw: {raw[:200]}")
        return []
    except Exception as e:
        print(f"❌ Gemini APIエラー: {e}")
        return []


# ─────────────────────────────────────────
# キャッシュ管理（同日は再取得しない）
# ─────────────────────────────────────────
# 静的フォールバック（APIなし・Quota超過時）
# ─────────────────────────────────────────
_STATIC_PRODUCTS = [
    {
        "asin": "B09W2PNZQQ",
        "title": "TP-Link WiFi 無線LAN ルーター AX3000",
        "brand": "TP-Link",
        "price": {"amount": 5980, "currency": "JPY", "display": "¥5,980"},
        "original_price": {"amount": 7980, "display": "¥7,980"},
        "discount_rate": 25,
        "category": "ガジェット",
        "features": ["WiFi 6対応", "AX3000 高速通信", "簡単セットアップ"],
        "why_viral": "テレワーク勢が一度は検討するコスパ最強ルーター",
        "story_hook": "Wi-Fiが遅かった原因、ルーターだった。",
        "amazon_url": f"https://www.amazon.co.jp/dp/B09W2PNZQQ?tag={ASSOCIATE_TAG}",
        "source": "static",
        "fetched_at": datetime.now().isoformat(),
    },
    {
        "asin": "B0BQZPFQ2X",
        "title": "Anker 622 Magnetic Battery (MagGo) 5000mAh",
        "brand": "Anker",
        "price": {"amount": 3990, "currency": "JPY", "display": "¥3,990"},
        "original_price": {"amount": 4990, "display": "¥4,990"},
        "discount_rate": 20,
        "category": "ガジェット",
        "features": ["MagSafe対応", "5000mAh大容量", "マグネット吸着でiPhoneにピタッと装着"],
        "why_viral": "iPhoneユーザーなら即買いレベルのコスパ。充電ケーブル不要",
        "story_hook": "スマホの充電、どこでも気にならなくなった理由。",
        "amazon_url": f"https://www.amazon.co.jp/dp/B0BQZPFQ2X?tag={ASSOCIATE_TAG}",
        "source": "static",
        "fetched_at": datetime.now().isoformat(),
    },
    {
        "asin": "B09JQL3NWT",
        "title": "Anker Soundcore Liberty 4 NC ワイヤレスイヤホン",
        "brand": "Anker Soundcore",
        "price": {"amount": 7990, "currency": "JPY", "display": "¥7,990"},
        "original_price": {"amount": 9990, "display": "¥9,990"},
        "discount_rate": 20,
        "category": "ガジェット",
        "features": ["アクティブノイズキャンセリング", "最大10時間再生", "外音取り込みモード"],
        "why_viral": "1万円以下でノイキャン最強クラス。コスパ議論が盛り上がる",
        "story_hook": "カフェでの集中力が、これを使う前と後で全然違う。",
        "amazon_url": f"https://www.amazon.co.jp/dp/B09JQL3NWT?tag={ASSOCIATE_TAG}",
        "source": "static",
        "fetched_at": datetime.now().isoformat(),
    },
    {
        "asin": "B0C4BXHX2V",
        "title": "Baseus 67W USB-C 急速充電器 GaN窒化ガリウム採用",
        "brand": "Baseus",
        "price": {"amount": 2480, "currency": "JPY", "display": "¥2,480"},
        "original_price": {"amount": 3280, "display": "¥3,280"},
        "discount_rate": 24,
        "category": "ガジェット",
        "features": ["GaN採用で小型・軽量", "67W急速充電", "USB-C + USB-A 2ポート"],
        "why_viral": "純正アダプタより小さくて速い。ガジェット民の定番",
        "story_hook": "充電器を変えただけで、朝の準備が10分早くなった。",
        "amazon_url": f"https://www.amazon.co.jp/dp/B0C4BXHX2V?tag={ASSOCIATE_TAG}",
        "source": "static",
        "fetched_at": datetime.now().isoformat(),
    },
    {
        "asin": "B0BX4MQ3GY",
        "title": "Logicool MX MASTER 3S パフォーマンスワイヤレスマウス",
        "brand": "Logicool",
        "price": {"amount": 14080, "currency": "JPY", "display": "¥14,080"},
        "original_price": {"amount": 16500, "display": "¥16,500"},
        "discount_rate": 15,
        "category": "ガジェット",
        "features": ["8000DPI高精度センサー", "電磁気スクロールホイール", "最大70日間バッテリー"],
        "why_viral": "一度使うと普通のマウスに戻れない。PC作業勢の聖域",
        "story_hook": "マウスって、仕事のスピードを変えるデバイスだと思ってなかった。",
        "amazon_url": f"https://www.amazon.co.jp/dp/B0BX4MQ3GY?tag={ASSOCIATE_TAG}",
        "source": "static",
        "fetched_at": datetime.now().isoformat(),
    },
    {
        "asin": "B0BJKCS73T",
        "title": "UGREEN 300W USB-C ハブ 10-in-1 ドッキングステーション",
        "brand": "UGREEN",
        "price": {"amount": 8980, "currency": "JPY", "display": "¥8,980"},
        "original_price": {"amount": 11980, "display": "¥11,980"},
        "discount_rate": 25,
        "category": "ガジェット",
        "features": ["USB-C × 4K HDMI出力", "100W PD充電対応", "10ポート同時使用可"],
        "why_viral": "MacBookユーザーが必ず一度は検討する拡張ハブ",
        "story_hook": "デスクのごちゃごちゃを一発で解決したガジェット。",
        "amazon_url": f"https://www.amazon.co.jp/dp/B0BJKCS73T?tag={ASSOCIATE_TAG}",
        "source": "static",
        "fetched_at": datetime.now().isoformat(),
    },
    {
        "asin": "B08N5WRWNW",
        "title": "Anker PowerCore 10000 モバイルバッテリー",
        "brand": "Anker",
        "price": {"amount": 2799, "currency": "JPY", "display": "¥2,799"},
        "original_price": {"amount": 3499, "display": "¥3,499"},
        "discount_rate": 20,
        "category": "ガジェット",
        "features": ["10000mAh大容量", "コンパクト・軽量", "PowerIQ対応高速充電"],
        "why_viral": "国内Amazonで何年もベストセラー。間違いないやつ",
        "story_hook": "モバイルバッテリー、今さらAnkerにした。",
        "amazon_url": f"https://www.amazon.co.jp/dp/B08N5WRWNW?tag={ASSOCIATE_TAG}",
        "source": "static",
        "fetched_at": datetime.now().isoformat(),
    },
    {
        "asin": "B09JQMJHXY",
        "title": "Echo Dot 第5世代 スマートスピーカー with Alexa",
        "brand": "Amazon",
        "price": {"amount": 5980, "currency": "JPY", "display": "¥5,980"},
        "original_price": {"amount": 7480, "display": "¥7,480"},
        "discount_rate": 20,
        "category": "ガジェット",
        "features": ["Alexa音声操作", "スマートホーム対応", "改良されたサウンド"],
        "why_viral": "スマートホームの入門機として圧倒的コスパ",
        "story_hook": "声でエアコンを消せるようになったら、もう戻れない。",
        "amazon_url": f"https://www.amazon.co.jp/dp/B09JQMJHXY?tag={ASSOCIATE_TAG}",
        "source": "static",
        "fetched_at": datetime.now().isoformat(),
    },
    {
        "asin": "B0C6GYLGYB",
        "title": "Kindle Paperwhite 電子書籍リーダー 防水",
        "brand": "Amazon",
        "price": {"amount": 14980, "currency": "JPY", "display": "¥14,980"},
        "original_price": {"amount": 17980, "display": "¥17,980"},
        "discount_rate": 17,
        "category": "ガジェット",
        "features": ["防水対応(IPX8)", "グレア軽減ディスプレイ", "最大12週間バッテリー"],
        "why_viral": "読書習慣を作りたい人の最強デバイス",
        "story_hook": "紙の本をやめた理由を正直に話す。",
        "amazon_url": f"https://www.amazon.co.jp/dp/B0C6GYLGYB?tag={ASSOCIATE_TAG}",
        "source": "static",
        "fetched_at": datetime.now().isoformat(),
    },
]


def _static_fallback(category: str, count: int) -> list:
    """
    静的な商品データを返す（全APIが利用できない場合）。
    DB の static_products を優先し、なければコード内の _STATIC_PRODUCTS にフォールバック。
    """
    try:
        data = db.get_static_products()
        if data:
            cat_label = CATEGORIES.get(category, CATEGORIES["gadget"])["label"]
            filtered  = [p for p in data if p.get("category") == cat_label]
            result    = filtered if filtered else data
            return result[:count]
    except Exception as e:
        print(f"  ⚠️  static_products DB読み込みエラー: {e} → 内蔵データを使用")
    # ランダムシャッフルして毎回異なる商品が先頭に来るようにする
    import random as _random
    pool = list(_STATIC_PRODUCTS)
    _random.shuffle(pool)
    return pool[:count]


# ─────────────────────────────────────────
def load_cache() -> list:
    """当日のキャッシュを DB から返す。期限切れ or なければ空リスト（DB版）"""
    try:
        return db.get_amazon_deals(max_age_hours=6.0)
    except Exception as e:
        print(f"⚠️  キャッシュDB読み込み失敗: {e}")
        return []


def save_cache(products: list) -> None:
    """商品リストを DB に保存する（DB版）"""
    try:
        db.save_amazon_deals(products)
    except Exception as e:
        print(f"⚠️  キャッシュDB書き込み失敗: {e}")


# ─────────────────────────────────────────
# メイン取得関数
# ─────────────────────────────────────────
def fetch_deals(category: str = "gadget", count: int = 5, force_refresh: bool = False) -> list:
    """
    Amazon商品を取得する（PA-API → Gemini fallback）

    Args:
        category:      カテゴリキー（gadget/audio/charging/camera/pc/smart_home/all）
        count:         取得件数
        force_refresh: キャッシュを無視して再取得

    Returns:
        商品リスト
    """
    # カテゴリ"all"は全カテゴリから取得
    if category == "all":
        all_products = []
        per_cat = max(1, count // len(CATEGORIES))
        for cat_key in CATEGORIES:
            products = fetch_deals(cat_key, per_cat, force_refresh)
            all_products.extend(products)
        return all_products[:count]

    # キャッシュ確認
    if not force_refresh:
        cached = load_cache()
        if cached:
            cat_label = CATEGORIES[category]["label"]
            # product_rotator.py が保存する category 名は "ガジェット" など短縮形になるため
            # 完全一致に加えて「前方一致」も許容する（例: "ガジェット" in "ガジェット・家電"）
            filtered = [
                p for p in cached
                if (
                    p.get("category") == cat_label
                    or p.get("category", "").startswith(cat_label.split("・")[0])
                    or cat_label.startswith(p.get("category", "X_NO_MATCH"))
                )
            ]
            if not filtered:
                # カテゴリフィルタで0件 → キャッシュ全件を使う（カテゴリ不問）
                filtered = cached
            if len(filtered) >= count:
                print(f"📦 キャッシュ使用 ({category}: {len(filtered)}件)")
                return filtered[:count]

    print(f"🔍 {CATEGORIES[category]['label']}を{count}件取得中...")

    # PA-API を試みる
    products = fetch_via_paapi(category, count)

    # Gemini fallback
    if not products:
        print("   → Gemini fallbackで生成中...")
        products = fetch_via_gemini(category, count)

    # 静的データ fallback（PA-APIもGeminiも使えない場合）
    if not products:
        print("   → 静的データfallbackを使用")
        products = _static_fallback(category, count)

    if products:
        # 購買意欲スコアでソート（0.5%の壁対策）
        products = sort_by_intent(products)

        # コンテキストブースト（天候・給料日・時間帯で動的調整）
        try:
            from context_injector import apply_context_boost
            products = apply_context_boost(products, verbose=True)
        except Exception as e:
            print(f"  ⚠️  コンテキストブーストスキップ: {e}")

        # URLバリデーション: 404・エラーページにリダイレクトされる商品を除外
        # キャッシュヒット（24時間以内）の商品はHTTPリクエストをスキップする
        print("  🔗 URLバリデーション中...")
        val_cache   = _load_validation_cache()
        valid_products = []

        try:
            from utils.notifier import notify_info as _notify_info
        except Exception:
            _notify_info = None

        import re as _re

        for p in products:
            url  = p.get("amazon_url", "")
            m    = _re.search(r"/dp/([A-Z0-9]{10})", url)
            asin = m.group(1) if m else ""

            # ── キャッシュヒット: 24時間以内に検証済みならスキップ ──
            if _is_validation_fresh(asin, val_cache):
                print(f"  ⚡ キャッシュHIT（検証スキップ）: {p.get('title', '')[:30]}")
                valid_products.append(p)
                continue

            # ── 実際にHTTPで検証 ──
            is_valid, asin = _validate_amazon_url(url)
            if is_valid:
                _mark_validated(asin, val_cache)
                valid_products.append(p)
                continue

            # ── 無効URLの場合: search_keyword で再解決を試みる ──
            old_asin = asin
            keyword  = p.get("search_keyword") or p.get("keyword") or p.get("title", "")
            if keyword:
                print(f"  🔄 URL再解決中: {p.get('title', '')[:30]}")
                new_url          = _resolve_asin(keyword)
                re_valid, new_asin = _validate_amazon_url(new_url)
                if re_valid:
                    p = {**p, "amazon_url": new_url}
                    _mark_validated(new_asin, val_cache)
                    valid_products.append(p)
                    msg = f"🔗 Amazonリンク自動修復成功：ASIN {old_asin} -> {new_asin} に更新して投稿を継続します。"
                    print(f"  ✅ 再解決成功: {new_url[:60]}")
                    if _notify_info:
                        try:
                            _notify_info(
                                "x_automation/fetch_amazon_deals.py",
                                msg,
                                f"商品: {p.get('title', '')[:60]}",
                            )
                        except Exception as e:
                            print(f"  ⚠️  Discord通知失敗（無視して続行）: {e}")
                    continue

            print(f"  ⚠️  URLスキップ（商品ページなし）: {p.get('title', '')[:30]} → {url[:60]}")

        skipped = len(products) - len(valid_products)
        if skipped:
            print(f"  ℹ️  {skipped}件スキップ、{len(valid_products)}件有効")
        products = valid_products
        _save_validation_cache(val_cache)

        # 既存キャッシュとマージして保存（asin がない商品は search_keyword で比較）
        existing = load_cache()
        existing_keys = {p.get("asin") or p.get("search_keyword", "") for p in existing}
        new_products = [
            p for p in products
            if (p.get("asin") or p.get("search_keyword", "")) not in existing_keys
        ]
        save_cache(existing + new_products)
        print(f"✅ {len(products)}件取得完了（URLバリデーション済み・コンテキスト補正済みスコア順）")

    return products


# ─────────────────────────────────────────
# 表示ユーティリティ
# ─────────────────────────────────────────
def print_products(products: list):
    """取得した商品を整形表示"""
    print(f"\n{'=' * 60}")
    print(f"🛒 取得商品一覧 ({len(products)}件)")
    print(f"{'=' * 60}")

    for i, p in enumerate(products, 1):
        discount = p.get("discount_rate", 0)
        price    = p.get("price", {}).get("display", "価格不明")
        source   = p.get("source", "")
        hook     = p.get("story_hook", "")

        intent = p.get("intent_score", score_purchase_intent(p))
        intent_bar = "█" * (intent // 10) + "░" * (10 - intent // 10)

        print(f"\n【{i}】{p['title'][:50]}")
        print(f"   価格: {price}" + (f"  ({discount}%OFF)" if discount else ""))
        print(f"   購買意欲スコア: {intent_bar} {intent}/100")
        if hook:
            print(f"   フック: {hook}")
        print(f"   URL: {p.get('amazon_url', 'N/A')[:60]}")
        print(f"   取得元: {'PA-API' if 'pa-api' in source else 'Gemini生成'}")

    print(f"\n💾 保存先: {DEALS_JSON}")


# ─────────────────────────────────────────
# CLI
# ─────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Amazonセール商品取得")
    parser.add_argument("--category", default="gadget",
                        choices=list(CATEGORIES.keys()) + ["all"],
                        help="カテゴリ (デフォルト: gadget)")
    parser.add_argument("--count", type=int, default=5, help="取得件数 (デフォルト: 5)")
    parser.add_argument("--refresh", action="store_true", help="キャッシュを無視して再取得")
    args = parser.parse_args()

    products = fetch_deals(args.category, args.count, args.refresh)

    if products:
        print_products(products)
    else:
        print("❌ 商品を取得できませんでした")
        sys.exit(1)


if __name__ == "__main__":
    main()
