"""
Amazonランキング商品自動収集スクリプト

フロー:
  1. x_automation/static_products.json + data/static_products.json を読み込む
  2. Amazonランキングページを巡回してASINと商品名を抽出
  3. 未登録商品のみをプールに追加（最大 MAX_PER_RUN 件/実行）
  4. プール上限（MAX_POOL_SIZE=50件）超過時は古い fetched 商品からローテーション
  5. 変更があった場合のみ両JSONを上書き保存

実行:
  python3 x_automation/trend_product_fetcher.py           # 本番
  python3 x_automation/trend_product_fetcher.py --dry-run # 確認のみ（書き込みなし）
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
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).parent          # x_automation/
ROOT_DIR = BASE_DIR.parent

# .env 読み込み
env_path = ROOT_DIR / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

ASSOCIATE_TAG = os.getenv("AMAZON_ASSOCIATE_TAG", "smartearn22-22")
MAX_PER_RUN   = 15  # 1回の実行で追加する上限（カテゴリ増加に対応）
MAX_POOL_SIZE = 200 # プールの上限件数（全カテゴリ対応）

# 巡回するランキングページ（PCガジェット系を優先）
RANKING_URLS = [
    # エレクトロニクス・ガジェット
    "https://www.amazon.co.jp/gp/bestsellers/electronics/2127209051",  # PCアクセサリ
    "https://www.amazon.co.jp/gp/bestsellers/electronics/",            # エレクトロニクス全体
    # キッチン・食品
    "https://www.amazon.co.jp/gp/bestsellers/kitchen/",                # キッチン用品
    "https://www.amazon.co.jp/gp/bestsellers/food-beverage/",          # 食品・飲料
    # 日用品・生活雑貨
    "https://www.amazon.co.jp/gp/bestsellers/hpc/",                    # ドラッグストア・ビューティー
    "https://www.amazon.co.jp/gp/bestsellers/home/",                   # ホーム＆キッチン
    "https://www.amazon.co.jp/gp/bestsellers/office-products/",        # 文房具・オフィス用品
    # インテリア・収納
    "https://www.amazon.co.jp/gp/bestsellers/home-improvement/",       # DIY・工具・ガーデン
    # スポーツ・アウトドア
    "https://www.amazon.co.jp/gp/bestsellers/sports/",                 # スポーツ＆アウトドア
    # セール・タイムセール
    "https://www.amazon.co.jp/gp/goldbox/",                            # タイムセール
    "https://www.amazon.co.jp/deals/",                                 # 本日のセール
]

# 同期更新する両JSONファイル
TARGET_JSON_FILES = [
    BASE_DIR / "static_products.json",          # product_rotator.py（x_automation）が参照
    ROOT_DIR / "data" / "static_products.json", # product_rotator.py（scripts）が参照
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
}

# カテゴリ判定（商品名の部分一致で決定）
_CATEGORY_MAP = [
    (["イヤホン", "ヘッドホン", "スピーカー", "Soundcore", "AirPods"], "オーディオ"),
    (["充電", "バッテリー", "モバイル", "GaN", "USB充電", "アダプタ"],  "充電・バッテリー"),
    (["スマートプラグ", "スマートスピーカー", "SwitchBot", "Hub", "Alexa", "Google Home"], "スマートホーム"),
    (["マウス", "キーボード", "モニター", "ウェブカメラ", "SSD", "USBハブ", "ドッキング"], "PC周辺機器"),
    (["デスクマット", "ケーブルホルダー", "ケーブル収納", "チェア", "スタンド"],            "デスク環境"),
    # キッチン・食品
    (["フライパン", "鍋", "包丁", "まな板", "キッチン", "調理", "レンジ", "トースター", "炊飯"], "キッチン"),
    (["コーヒー", "プロテイン", "水筒", "タンブラー", "弁当"],                              "食品・飲料"),
    # 日用品・ドラッグストア
    (["洗剤", "柔軟剤", "シャンプー", "ボディソープ", "歯ブラシ", "歯磨き"],                "日用品"),
    (["化粧水", "日焼け止め", "スキンケア", "メンズ美容", "髭剃り", "シェーバー"],          "美容・ケア"),
    (["サプリ", "ビタミン", "プロテイン", "健康"],                                          "健康"),
    # 収納・インテリア
    (["収納", "ラック", "棚", "ボックス", "整理", "山崎実業", "tower", "無印"],              "収納・整理"),
    (["照明", "ライト", "LED", "デスクライト", "間接照明"],                                 "照明"),
    (["カーテン", "マット", "クッション", "ブランケット"],                                  "インテリア"),
    # 掃除・洗濯
    (["掃除機", "クリーナー", "モップ", "ロボット掃除"],                                    "掃除"),
    (["洗濯", "乾燥", "ハンガー", "物干し", "アイロン"],                                    "洗濯"),
    # スポーツ・アウトドア
    (["ヨガ", "ストレッチ", "ダンベル", "筋トレ", "トレーニング"],                          "フィットネス"),
    (["キャンプ", "アウトドア", "ランタン", "テント", "チェア"],                             "アウトドア"),
    # 睡眠
    (["枕", "マットレス", "布団", "アイマスク", "耳栓", "睡眠"],                            "睡眠"),
]
_DEFAULT_CATEGORY = "生活雑貨"


def _make_dp_url(asin: str) -> str:
    return f"https://www.amazon.co.jp/dp/{asin}?tag={ASSOCIATE_TAG}"


def _detect_category(title: str) -> str:
    for keywords, category in _CATEGORY_MAP:
        if any(kw in title for kw in keywords):
            return category
    return _DEFAULT_CATEGORY


def _extract_brand(title: str) -> str:
    """先頭の英数字または日本語ブランド名を返す。"""
    m = re.match(r"^([A-Za-z][A-Za-z0-9]+|[゠-ヿ一-鿿]{2,6})", title)
    return m.group(1) if m else ""


def _extract_keywords(title: str) -> list[str]:
    """商品名を分割して意味のある語を最大4つ返す。"""
    tokens = re.split(r"[\s　 /　\[\]【】（）()「」『』・×＋]+", title)
    noise = {"の", "を", "が", "は", "に", "で", "と", "a", "an", "the"}
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


def _scrape_ranking_page(url: str) -> list[dict]:
    """
    Amazonランキングページから {asin, title} を抽出する。
    アクセス制限・タイムアウト時は空リストを返す。
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=12)
        if resp.status_code in (503, 429):
            print(f"  ⚠️  アクセス制限 ({resp.status_code}): {url}")
            return []
        if resp.status_code != 200:
            print(f"  ⚠️  HTTPエラー ({resp.status_code}): {url}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        results: list[dict] = []
        seen_asins: set[str] = set()

        for el in soup.find_all(attrs={"data-asin": True}):
            asin = el.get("data-asin", "").strip()
            if not asin or len(asin) != 10 or asin in seen_asins:
                continue

            title = ""
            # 複数セレクタでタイトルを試みる（Amazon はページ構造を頻繁に変更する）
            for sel in [
                "span._cDEzb_p13n-sc-css-line-clamp-3_g3dy1",
                "div._cDEzb_p13n-sc-css-line-clamp-4_2q2cc",
                "span.a-text-normal",
                "div.p13n-sc-truncate-desktop-type2",
                "span[class*='p13n-sc-truncate']",
            ]:
                tag = el.select_one(sel)
                if tag:
                    title = tag.get_text(strip=True)
                    break

            # セレクタが全滅した場合は img の alt テキストにフォールバック
            img_tag = el.find("img")
            if not title and img_tag:
                title = (img_tag.get("alt") or "").strip()

            if len(title) < 5:
                continue

            # ランキングページのサムネイル URL を取得
            image_url = ""
            if img_tag:
                for attr in ("src", "data-src"):
                    val = (img_tag.get(attr) or "").strip()
                    if val.startswith("http") and "amazon" in val:
                        # スプライト画像（1px gif）は除外
                        if "transparent-pixel" not in val and val.endswith((".jpg", ".png", ".jpeg")):
                            image_url = val
                            break
                # data-a-dynamic-image は JSON 形式 {"https://...": [W, H], ...}
                if not image_url:
                    dynamic = img_tag.get("data-a-dynamic-image", "")
                    if dynamic:
                        try:
                            import json as _json
                            url_map = _json.loads(dynamic)
                            # 解像度が最大の URL を選択
                            best = max(url_map.items(), key=lambda kv: kv[1][0] * kv[1][1])
                            image_url = best[0]
                        except Exception:
                            pass

            # 割引・セール情報を取得
            discount_pct = 0
            price_text = ""
            for price_sel in [
                "span.a-color-price",
                "span[data-a-color='price']",
                "span.p13n-sc-price",
            ]:
                price_tag = el.select_one(price_sel)
                if price_tag:
                    price_text = price_tag.get_text(strip=True)
                    break
            # 割引率の抽出（「-20%」「20%OFF」など）
            for disc_sel in [
                "span.savingsPercentage",
                "span[data-a-badge-color='sx-deal-color']",
                "span.a-text-bold",
            ]:
                disc_tag = el.select_one(disc_sel)
                if disc_tag:
                    disc_text = disc_tag.get_text(strip=True)
                    disc_m = re.search(r'(\d+)\s*%', disc_text)
                    if disc_m:
                        discount_pct = int(disc_m.group(1))
                        break

            seen_asins.add(asin)
            results.append({
                "asin": asin, "title": title, "image_url": image_url,
                "discount_pct": discount_pct, "price_text": price_text,
            })
            if len(results) >= MAX_PER_RUN * 3:
                break

        print(f"  📊 {len(results)} 件の ASIN 検出: {url[:60]}")
        return results

    except requests.Timeout:
        print(f"  ⚠️  タイムアウト: {url}")
        return []
    except Exception as e:
        print(f"  ⚠️  スクレイピングエラー: {e}")
        return []


def _build_product(asin: str, title: str, image_url: str = "",
                    discount_pct: int = 0, price_text: str = "") -> dict:
    """スクレイピング結果から static_products.json 互換の商品辞書を生成する。"""
    category = _detect_category(title)
    keywords = _extract_keywords(title)
    brand    = _extract_brand(title)

    return {
        "asin":           asin,
        "search_keyword": title[:40],
        "title":          title,
        "brand":          brand,
        "price":          {"amount": 0, "currency": "JPY", "display": price_text or "要確認"},
        "original_price": {"amount": 0, "display": "要確認"},
        "discount_rate":  discount_pct,
        "category":       category,
        "keywords":       keywords,
        "image_url":      image_url,
        "features": [
            "Amazonランキング上位の人気商品",
            "詳細はAmazonページを確認",
        ],
        "why_viral":    "ランキング急上昇中のガジェット。注目度が高い",
        "story_hook":   "Amazonで今売れてるやつ、試してみた。",
        "user_problem": "話題のガジェットを手に入れたい",
        "amazon_url":   _make_dp_url(asin),
        "source":       "fetched",
        "fetched_at":   datetime.now().isoformat(),
    }


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
    # fetched を後ろから優先削除
    fetched_indices = [i for i, p in enumerate(pool) if p.get("source") == "fetched"]
    for idx in sorted(fetched_indices, reverse=True):
        if over <= 0:
            break
        pool.pop(idx)
        over -= 1
    # それでも超える場合は末尾から削除
    return pool[:-over] if over > 0 else pool


def fetch_and_update(dry_run: bool = False) -> bool:
    """
    ランキングを巡回して両 static_products.json を更新する。

    Returns:
        True  ... 新規商品あり
        False ... 変更なし
    """
    print(f"\n{'=' * 60}")
    print("🔍 Amazonランキング商品自動収集")
    print(f"{'=' * 60}")

    # プライマリ JSON から既存 ASIN セットを構築
    primary_pool   = _load_json(TARGET_JSON_FILES[0])
    existing_asins = {p.get("asin", "") for p in primary_pool if p.get("asin")}
    print(f"📦 既存プール: {len(primary_pool)} 件（ASIN 登録済み: {len(existing_asins)} 件）")

    # ランキングページを巡回して候補を収集
    candidates: list[dict] = []
    seen_in_run: set[str] = set()

    max_per_category = max(3, MAX_PER_RUN // len(RANKING_URLS))
    for url in RANKING_URLS:
        print(f"\n🌐 巡回中: {url[:60]}")
        raw = _scrape_ranking_page(url)
        time.sleep(2)  # サーバー負荷軽減

        added_this_cat = 0
        for item in raw:
            asin = item["asin"]
            if asin in existing_asins or asin in seen_in_run:
                continue
            seen_in_run.add(asin)
            candidates.append(_build_product(
                asin, item["title"], item.get("image_url", ""),
                discount_pct=item.get("discount_pct", 0),
                price_text=item.get("price_text", ""),
            ))
            added_this_cat += 1
            if added_this_cat >= max_per_category:
                break

    if not candidates:
        print("\n✅ 新規商品なし（すべて登録済みまたは取得 0 件）")
        return False

    print(f"\n🆕 追加候補: {len(candidates)} 件")
    for p in candidates:
        print(f"   - [{p['asin']}] {p['title'][:50]}")
        print(f"              {p['amazon_url']}")

    if dry_run:
        print("\n🔍 dry-run: ファイル書き込みをスキップ")
        return True

    # 両 JSON ファイルを更新
    for json_path in TARGET_JSON_FILES:
        pool       = _load_json(json_path)
        pool_asins = {p.get("asin", "") for p in pool}
        new_items  = [c for c in candidates if c["asin"] not in pool_asins]
        if not new_items:
            print(f"  ℹ️  {json_path.name}: 追加対象なし（すべて既登録）")
            continue
        pool = pool + new_items
        pool = _rotate(pool, MAX_POOL_SIZE)
        _save_json(json_path, pool)
        print(f"  💾 {json_path.name}: {len(pool)} 件（+{len(new_items)} 件追加）")

    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Amazonランキング商品自動収集")
    parser.add_argument("--dry-run", action="store_true", help="確認のみ（書き込みなし）")
    args = parser.parse_args()

    changed = fetch_and_update(dry_run=args.dry_run)
    print("\n✅ 完了（変更あり）" if changed else "\n✅ 完了（変更なし）")


if __name__ == "__main__":
    main()
