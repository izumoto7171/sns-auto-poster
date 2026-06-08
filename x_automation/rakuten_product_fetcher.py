"""
楽天商品自動収集スクリプト（IchibaItemSearch API）

フロー:
  1. x_automation/rakuten_products.json + data/rakuten_products.json を読み込む
  2. 楽天商品検索API からガジェット商品を取得（最大 MAX_PER_RUN 件）
  3. itemCode で重複チェックし、未登録商品のみをプール末尾に追加
  4. プール上限（MAX_POOL_SIZE=50件）超過時は古い fetched 商品からローテーション
  5. 変更があった場合のみ両JSONを上書き保存

実行:
  python3 x_automation/rakuten_product_fetcher.py           # 本番
  python3 x_automation/rakuten_product_fetcher.py --dry-run # 確認のみ（書き込みなし）

必要な環境変数:
  RAKUTEN_APP_ID          楽天アプリID（必須・未設定時はスキップして正常終了）
  RAKUTEN_ACCESS_KEY      楽天アクセスキー（必須）
  RAKUTEN_AFFILIATE_ID    楽天アフィリエイトID（任意・未設定でもURL生成可）
  RAKUTEN_ORIGIN          楽天API許可済みオリジン（未設定時はブログURLを使用）
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

BASE_DIR = Path(__file__).parent      # x_automation/
ROOT_DIR = BASE_DIR.parent

# .env 読み込み
env_path = ROOT_DIR / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

# ─────────────────────────────────────────
# 定数
# ─────────────────────────────────────────
MAX_PER_RUN   = 5   # 1回の実行で追加する上限
MAX_POOL_SIZE = 50  # プールの上限件数

# API認証（RAKUTEN_APPLICATION_ID → RAKUTEN_APP_ID の優先順でフォールバック）
def _get_app_id() -> str:
    return (
        os.getenv("RAKUTEN_APPLICATION_ID", "")
        or os.getenv("RAKUTEN_APP_ID", "")
    )

API_ENDPOINT = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20220601"

# RAKUTEN_ORIGIN 未設定時はブログURLをデフォルト値として使用（アプリ登録済みOrigin）
DEFAULT_ORIGIN = "https://smart-earn-life.hateblo.jp"

# 検索キーワード（順番に試して MAX_PER_RUN 件集まったら終了）
SEARCH_KEYWORDS = ["ガジェット USB", "ワイヤレスイヤホン", "充電器 GaN", "デスク 収納"]

# ふるさと納税など除外ワード（購買アフィリエイトと相性が悪い）
EXCLUDE_WORDS = ["ふるさと納税", "返礼品", "寄附", "寄付"]

# 同期更新する両JSONファイル
TARGET_JSON_FILES = [
    BASE_DIR / "rakuten_products.json",          # x_automation/ 以下
    ROOT_DIR / "data" / "rakuten_products.json", # data/ 以下
]

# カテゴリ判定
_CATEGORY_MAP = [
    (["イヤホン", "ヘッドホン", "スピーカー", "Soundcore", "AirPods"], "オーディオ"),
    (["充電", "バッテリー", "モバイル", "GaN", "USB充電", "アダプタ"],  "充電・バッテリー"),
    (["スマートプラグ", "スマートスピーカー", "SwitchBot", "Hub", "Alexa"], "スマートホーム"),
    (["マウス", "キーボード", "モニター", "ウェブカメラ", "SSD", "USBハブ"], "PC周辺機器"),
    (["デスクマット", "ケーブルホルダー", "ケーブル収納", "チェア", "スタンド"], "デスク環境"),
]
_DEFAULT_CATEGORY = "ガジェット"


def _detect_category(title: str) -> str:
    for keywords, category in _CATEGORY_MAP:
        if any(kw in title for kw in keywords):
            return category
    return _DEFAULT_CATEGORY


def _extract_brand(shop_name: str, title: str) -> str:
    m = re.match(r"^([A-Za-z][A-Za-z0-9]+|[ァ-ヶー一-鿿]{2,6})", title)
    if m:
        return m.group(1)
    return shop_name[:20] if shop_name else ""


def _extract_keywords(title: str, catchcopy: str = "") -> list[str]:
    text   = f"{title} {catchcopy}"
    tokens = re.split(r"[\s　 /\[\]【】（）()「」『』・×＋]+", text)
    noise  = {"の", "を", "が", "は", "に", "で", "と", "a", "an", "the", ""}
    seen: set[str] = set()
    result: list[str] = []
    for t in tokens:
        t = t.strip("-,.")
        if len(t) >= 2 and t not in noise and t not in seen:
            seen.add(t)
            result.append(t)
        if len(result) >= 4:
            break
    return result or [title[:10]]


def _is_excluded(title: str) -> bool:
    """ふるさと納税など除外ワードを含む商品を判定する。"""
    return any(w in title for w in EXCLUDE_WORDS)


def _build_product(item: dict) -> dict:
    """楽天APIレスポンスの Item オブジェクトから保存用辞書を生成する。"""
    title         = item.get("itemName", "")
    shop_name     = item.get("shopName", "")
    price         = int(item.get("itemPrice", 0))
    item_code     = item.get("itemCode", "")
    item_url      = item.get("itemUrl", "")
    affiliate_url = item.get("affiliateUrl", "") or item_url
    catchcopy     = item.get("catchcopy", "")
    image_url     = ""
    if item.get("mediumImageUrls"):
        image_url = item["mediumImageUrls"][0].get("imageUrl", "")

    category      = _detect_category(title)
    keywords      = _extract_keywords(title, catchcopy)
    brand         = _extract_brand(shop_name, title)
    price_display = f"¥{price:,}" if price else "要確認"

    return {
        "item_code":      item_code,
        "search_keyword": title[:40],
        "title":          title,
        "brand":          brand,
        "shop_name":      shop_name,
        "price":          {"amount": price, "currency": "JPY", "display": price_display},
        "original_price": {"amount": price, "display": price_display},
        "discount_rate":  0,
        "category":       category,
        "keywords":       keywords,
        "catchcopy":      catchcopy,
        "image_url":      image_url,
        "features": [
            catchcopy[:40] if catchcopy else "楽天人気ショップの商品",
            "詳細は楽天ページを確認",
        ],
        "why_viral":    "楽天で注目の人気ガジェット。コスパと評判が高い",
        "story_hook":   "楽天で話題になってるやつ、試してみた。",
        "user_problem": "コスパの高いガジェットを探している",
        "amazon_url":   "",           # 楽天商品には amazon_url なし
        "affiliate_url": affiliate_url,
        "item_url":     item_url,
        "source":       "fetched",
        "fetched_at":   datetime.now().isoformat(),
    }


def _fetch_rakuten(keyword: str, app_id: str, access_key: str,
                   affiliate_id: str, origin: str, hits: int = 10) -> list[dict]:
    """
    楽天 IchibaItem Search API を呼び出して商品リストを返す。
    エラー時は空リストを返す（例外は呼び出し元で続行）。
    """
    params: dict = {
        "applicationId": app_id,
        "accessKey":     access_key,
        "keyword":       keyword,
        "sort":          "-reviewCount",
        "hits":          hits,
        "imageFlag":     1,
        "format":        "json",
    }
    if affiliate_id:
        params["affiliateId"] = affiliate_id

    headers = {
        "Origin":  origin,
        "Referer": origin.rstrip("/") + "/",
    }

    try:
        resp = requests.get(API_ENDPOINT, params=params, headers=headers, timeout=12)
        if resp.status_code != 200:
            print(f"  ⚠️  楽天API HTTPエラー ({resp.status_code}): keyword={keyword}")
            print(f"      {resp.text[:100]}")
            return []
        items = resp.json().get("Items", [])
        return [it["Item"] for it in items if "Item" in it]
    except requests.Timeout:
        print(f"  ⚠️  楽天API タイムアウト: keyword={keyword}")
        return []
    except Exception as e:
        print(f"  ⚠️  楽天API エラー: {e}")
        return []


def _load_json(path: Path) -> list:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  ⚠️  JSON読み込みエラー ({path.name}): {e}")
    return []


def _save_json(path: Path, data: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _rotate(pool: list, max_size: int) -> list:
    """
    上限超過時に古い fetched 商品から削除する。
    source='static' の手動定義商品は削除しない。
    """
    if len(pool) <= max_size:
        return pool
    over = len(pool) - max_size
    fetched_indices = [i for i, p in enumerate(pool) if p.get("source") == "fetched"]
    for idx in sorted(fetched_indices, reverse=True):
        if over <= 0:
            break
        pool.pop(idx)
        over -= 1
    return pool[:-over] if over > 0 else pool


def fetch_and_update(dry_run: bool = False) -> bool:
    """
    楽天APIから商品を取得して両 rakuten_products.json を更新する。

    Returns:
        True  ... 新規商品あり
        False ... 変更なし
    """
    print(f"\n{'=' * 60}")
    print("🛍️  楽天商品自動収集（IchibaItem Search API）")
    print(f"{'=' * 60}")

    # 環境変数チェック（未設定時はスキップして正常終了）
    app_id       = _get_app_id()
    access_key   = os.getenv("RAKUTEN_ACCESS_KEY", "")
    affiliate_id = os.getenv("RAKUTEN_AFFILIATE_ID", "")
    origin       = os.getenv("RAKUTEN_ORIGIN", DEFAULT_ORIGIN)

    if not app_id:
        print("⚠️  RAKUTEN_APPLICATION_ID / RAKUTEN_APP_ID が未設定のためスキップします")
        return False
    if not access_key:
        print("⚠️  RAKUTEN_ACCESS_KEY が未設定のためスキップします")
        return False

    print(f"🔑 appId: {app_id[:8]}... / origin: {origin}")
    print(f"   affiliateId: {affiliate_id[:16]}..." if affiliate_id else "   affiliateId: 未設定（通常URLを使用）")

    # プライマリ JSON から既存 itemCode セットを構築
    primary_pool   = _load_json(TARGET_JSON_FILES[0])
    existing_codes = {p.get("item_code", "") for p in primary_pool if p.get("item_code")}
    print(f"📦 既存プール: {len(primary_pool)} 件（itemCode 登録済み: {len(existing_codes)} 件）")

    # キーワードを順に試して MAX_PER_RUN 件集める
    candidates: list[dict] = []
    seen_in_run: set[str]  = set()

    for keyword in SEARCH_KEYWORDS:
        if len(candidates) >= MAX_PER_RUN:
            break
        remain = MAX_PER_RUN - len(candidates)
        print(f"\n🔍 検索中: 「{keyword}」（残り {remain} 件必要）")
        raw = _fetch_rakuten(keyword, app_id, access_key, affiliate_id, origin, hits=10)
        print(f"  📊 API取得: {len(raw)} 件")
        time.sleep(1)  # APIレートリミット対策

        for item in raw:
            code  = item.get("itemCode", "")
            title = item.get("itemName", "")
            # 除外ワード・重複チェック
            if not code or _is_excluded(title):
                continue
            if code in existing_codes or code in seen_in_run:
                continue
            seen_in_run.add(code)
            candidates.append(_build_product(item))
            if len(candidates) >= MAX_PER_RUN:
                break

    if not candidates:
        print("\n✅ 新規商品なし（すべて登録済みまたは取得 0 件）")
        return False

    print(f"\n🆕 追加候補: {len(candidates)} 件")
    for p in candidates:
        print(f"   - [{p['item_code']}] {p['title'][:45]}")
        print(f"     価格: {p['price']['display']} | カテゴリ: {p['category']}")
        print(f"     URL: {p['affiliate_url'][:70]}")

    if dry_run:
        print("\n🔍 dry-run: ファイル書き込みをスキップ")
        return True

    # 両 JSON ファイルを更新
    for json_path in TARGET_JSON_FILES:
        pool       = _load_json(json_path)
        pool_codes = {p.get("item_code", "") for p in pool}
        new_items  = [c for c in candidates if c["item_code"] not in pool_codes]
        if not new_items:
            print(f"  ℹ️  {json_path.name}: 追加対象なし（すべて既登録）")
            continue
        pool = pool + new_items
        pool = _rotate(pool, MAX_POOL_SIZE)
        _save_json(json_path, pool)
        print(f"  💾 {json_path.name}: {len(pool)} 件（+{len(new_items)} 件追加）")

    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="楽天商品自動収集（IchibaItem Search API）")
    parser.add_argument("--dry-run", action="store_true", help="確認のみ（書き込みなし）")
    args = parser.parse_args()

    changed = fetch_and_update(dry_run=args.dry_run)
    print("\n✅ 完了（変更あり）" if changed else "\n✅ 完了（変更なし）")


if __name__ == "__main__":
    main()
