"""
Amazon アソシエイト 商品監視モジュール

【取得戦略（優先順位）】
1. Amazon PA-API（AMAZON_ACCESS_KEY + AMAZON_SECRET_KEY が設定されている場合）
2. x_automation/amazon_deals.json のキャッシュ（Gemini生成済み）
3. x_automation/static_products.json の静的データ

seen_amazon.json で処理済みを管理し、未処理分のみ返す。
定期実行では静的データも「未処理が残っていれば」流せるため、
PA-API未設定でも一定期間は機能する。

【実行】
  python3 money_agent/amazon_monitor.py          # 新着確認
  python3 money_agent/amazon_monitor.py reset    # 既読リセット
"""

import os
import sys
import json
from pathlib import Path

SEEN_FILE   = Path(__file__).parent / "seen_amazon.json"
MAX_PER_RUN = 3

_X_AUTO_DIR = Path(__file__).parent.parent / "x_automation"
if str(_X_AUTO_DIR) not in sys.path:
    sys.path.insert(0, str(_X_AUTO_DIR))

ASSOCIATE_TAG = os.environ.get("AMAZON_ASSOCIATE_TAG", "")


# ============================================================
# 既読管理
# ============================================================
def load_seen() -> set:
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    return set()


def save_seen(seen: set):
    SEEN_FILE.write_text(
        json.dumps(sorted(seen), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ============================================================
# PA-API 取得（オプション）
# ============================================================
def _fetch_via_paapi(count: int = MAX_PER_RUN) -> list:
    """PA-API で商品を取得（認証情報がある場合のみ）"""
    access_key  = os.environ.get("AMAZON_ACCESS_KEY", "")
    secret_key  = os.environ.get("AMAZON_SECRET_KEY", "")
    partner_tag = ASSOCIATE_TAG

    if not (access_key and secret_key and partner_tag):
        return []

    try:
        from fetch_amazon_deals import fetch_via_paapi, CATEGORIES
        products = []
        for category in list(CATEGORIES.keys())[:2]:
            products.extend(fetch_via_paapi(category, count))
            if len(products) >= count:
                break
        return products[:count]
    except Exception as e:
        print(f"[Amazon PA-API] 取得失敗: {e}")
        return []


# ============================================================
# キャッシュ・静的データから読み込み
# ============================================================
def _load_cached_products() -> list:
    """Gemini生成済みキャッシュ + 静的データを読み込む"""
    products = []

    # Gemini生成済みキャッシュ
    cache_files = [
        _X_AUTO_DIR / "amazon_deals.json",
        Path(__file__).parent.parent / "data" / "amazon_deals.json",
    ]
    for cache_file in cache_files:
        if cache_file.exists():
            try:
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    products.extend(data)
            except Exception:
                pass

    # 静的データ fallback
    static_files = [
        _X_AUTO_DIR / "static_products.json",
        Path(__file__).parent.parent / "data" / "static_products.json",
    ]
    for static_file in static_files:
        if static_file.exists():
            try:
                data = json.loads(static_file.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    products.extend(data)
            except Exception:
                pass

    return products


# ============================================================
# 商品データを product_watcher.py 向けに正規化
# ============================================================
def _normalize(p: dict) -> dict:
    url = p.get("amazon_url", "") or p.get("url", "")
    # アソシエイトタグが未付与なら追加
    if ASSOCIATE_TAG and url and "tag=" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}tag={ASSOCIATE_TAG}"

    return {
        "asin":        p.get("asin", ""),
        "title":       p.get("title", ""),
        "url":         url,
        "category":    p.get("category", "ガジェット"),
        "description": (
            p.get("story_hook", "")
            or p.get("user_problem", "")
            or ", ".join(p.get("features", []))[:300]
        ),
        "price":       p.get("price", {}).get("display", "") if isinstance(p.get("price"), dict) else "",
        "discount":    p.get("discount_rate", 0),
        "source":      "amazon",
        "_raw":        p,
    }


# ============================================================
# 新着取得（メイン）
# ============================================================
def fetch_new_products(max_per_run: int = MAX_PER_RUN) -> list:
    """新着Amazon商品を取得して返す（seen管理あり）"""
    seen = load_seen()
    new_products = []

    # 1. PA-API（認証情報があれば）
    raw = _fetch_via_paapi(max_per_run)

    # 2. キャッシュ + 静的データ
    if not raw:
        raw = _load_cached_products()

    for p in raw:
        if len(new_products) >= max_per_run:
            break
        url = p.get("amazon_url", "") or p.get("url", "")
        key = p.get("asin", "") or url
        if not key or key in seen:
            continue
        new_products.append(_normalize(p))
        seen.add(key)

    save_seen(seen)
    print(f"[Amazon] 新着: {len(new_products)}件（seen管理済みを除外）")
    return new_products


# ============================================================
# CLI
# ============================================================
if __name__ == "__main__":
    # .env 読み込み
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    if "reset" in sys.argv:
        SEEN_FILE.write_text("[]", encoding="utf-8")
        print("既読リセット完了")
    else:
        products = fetch_new_products()
        for p in products:
            print(f"  [{p['category']}] {p['title'][:60]}")
            print(f"    {p['url'][:80]}")
