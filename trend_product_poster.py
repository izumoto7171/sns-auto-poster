"""
外国人に人気の日本商品トレンドを分析して動画投稿

処理フロー:
  1. Gemini API で「今外国人に人気の日本商品」を分析
  2. docs/products.json に既存商品があればそれを使用
  3. なければ Gemini が提案する ASIN で新商品を products.json に追加
  4. product_shorts_creator.py で動画生成
  5. YouTube にアップロード

使い方:
  python3.11 trend_product_poster.py              # 実行
  python3.11 trend_product_poster.py --dry-run    # 分析のみ（投稿しない）
  python3.11 trend_product_poster.py --show-trends # トレンド表示のみ
"""

import os, sys, json, re, argparse
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent

# .env 読み込み
env_path = BASE_DIR / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

PRODUCTS_JSON  = BASE_DIR / "docs" / "products.json"
TREND_LOG      = BASE_DIR / "output" / "trend_log.json"
AMAZON_TAG     = os.environ.get("AMAZON_ASSOCIATE_TAG", "smartearn22-22")

# カテゴリ英→日マッピング
CAT_EN_TO_JA = {
    "Japanese Snack":    "日本のお菓子",
    "Japan Stationery":  "日本の文房具",
    "Japanese Tradition":"日本の伝統アイテム",
    "Japan Skincare":    "日本のスキンケア",
    "Japan Kitchen":     "日本のキッチングッズ",
    "Anime Figure":      "アニメグッズ",
    "Gadget":            "ガジェット",
    "Subscription":      "サービス・サブスク",
}


# ─────────────────────────────────────────────
# Gemini でトレンド分析
# ─────────────────────────────────────────────
def analyze_trends_with_gemini() -> list:
    """
    外国人旅行者・海外在住者に今人気の日本商品をGeminiで分析。
    返り値: [{name, nameEn, category, categoryEn, description, descriptionEn,
              amazonAsin, imageQuery, reason}, ...]
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("google-genai が未インストール: pip3.11 install google-genai")
        sys.exit(1)

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("GEMINI_API_KEY が未設定です")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    today = datetime.now().strftime("%Y年%m月%d日")

    prompt = f"""
あなたは日本のインバウンドマーケティング専門家です。
今日は {today} です。

外国人旅行者・海外在住者・海外のJapanオタクに**今現在人気の高い日本商品**を5つ選んでください。

選定基準:
- SNS（TikTok/Instagram/YouTube）で外国人が紹介している
- Amazon Japan / 楽天で外国人レビューが多い
- 日本限定・日本発のユニークな商品
- 実際にAmazon Japanで購入可能なもの

以下のJSONのみを返してください（コードブロック・説明文なし）:
[
  {{
    "nameEn": "English product name",
    "name": "日本語商品名",
    "categoryEn": "Japanese Snack|Japan Stationery|Japanese Tradition|Japan Skincare|Japan Kitchen|Anime Figure|Gadget",
    "descriptionEn": "2-3 sentences in simple English for foreign buyers. Why foreigners love it.",
    "description": "日本語説明文",
    "amazonAsin": "B0XXXXXXXXX or empty string if unknown",
    "imageSearchQuery": "english search query for product image",
    "trendReason": "why foreigners love this right now (English, 1 sentence)"
  }},
  ...
]
"""

    # モデルを順番に試す
    models_to_try = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-flash"]
    raw = ""
    for model_name in models_to_try:
        try:
            resp = client.models.generate_content(model=model_name, contents=prompt)
            raw  = resp.text.strip()
            print(f"  モデル: {model_name}")
            break
        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                print(f"  {model_name}: クォータ超過 → 次のモデルを試行")
                continue
            print(f"Gemini エラー ({model_name}): {e}")
            return _fallback_trends()

    if not raw:
        print("  全モデルでクォータ超過 → フォールバックリストを使用")
        return _fallback_trends()

    try:
        raw = re.sub(r"```json\s*", "", raw)
        raw = re.sub(r"```\s*", "", raw)
        m   = re.search(r"\[.*\]", raw, re.DOTALL)
        if not m:
            print(f"JSONパースできません → フォールバック使用")
            return _fallback_trends()
        data = json.loads(m.group())
        print(f"Gemini トレンド分析完了: {len(data)}件")
        return data
    except json.JSONDecodeError:
        return _fallback_trends()


def _fallback_trends() -> list:
    """APIが使えない場合のフォールバックトレンドリスト（定期更新）"""
    print("  フォールバックトレンドリストを使用")
    return [
        {
            "nameEn": "Kracie Popin Cookin DIY Candy Kit",
            "name": "クラシエ ポッピンクッキン",
            "categoryEn": "Japanese Snack",
            "descriptionEn": "Make your own Japanese candy! Viral DIY kit loved by foreigners on TikTok. Sushi, ramen, and burger-shaped gummies you build yourself.",
            "description": "自分で作る日本のお菓子キット。TikTokで外国人に大人気。",
            "amazonAsin": "B07BWQGZMX",
            "imageSearchQuery": "Popin Cookin Japanese candy kit",
            "trendReason": "DIY candy videos go viral on TikTok with millions of views from foreign creators",
        },
        {
            "nameEn": "Shiseido Senka Perfect Whip Face Wash",
            "name": "専科 パーフェクトホイップ",
            "categoryEn": "Japan Skincare",
            "descriptionEn": "Japan's bestselling foaming face wash. Creates ultra-dense foam that gently cleanses. Famous in Asian skincare routines worldwide.",
            "description": "日本のベストセラー洗顔料。濃密泡が人気。",
            "amazonAsin": "B002KTTF6C",
            "imageSearchQuery": "Shiseido Senka Perfect Whip face wash Japan",
            "trendReason": "Featured in thousands of 'Japanese skincare routine' videos globally",
        },
        {
            "nameEn": "Sailor Moon Prism Power Compact Mirror",
            "name": "セーラームーン プリズムパワー コンパクトミラー",
            "categoryEn": "Anime Figure",
            "descriptionEn": "Iconic Sailor Moon collectible mirror replica. A must-have for anime fans worldwide. Limited edition Japan exclusive.",
            "description": "セーラームーンのコンパクトミラーレプリカ。",
            "amazonAsin": "",
            "imageSearchQuery": "Sailor Moon compact mirror Japan collectible",
            "trendReason": "Sailor Moon 30th anniversary merchandise trending on Instagram among international fans",
        },
        {
            "nameEn": "Kuretake ZIG Clean Color Real Brush Pens",
            "name": "クレタケ ZIG クリーンカラーリアルブラッシュ",
            "categoryEn": "Japan Stationery",
            "descriptionEn": "Professional brush pens beloved by artists worldwide. Water-based, blendable ink in 60 vivid colors. Made in Japan.",
            "description": "世界中のアーティストに愛される呉竹の筆ペン。",
            "amazonAsin": "B009WTXVHI",
            "imageSearchQuery": "Kuretake ZIG brush pen Japan art",
            "trendReason": "Trending among watercolor and lettering artists on YouTube and Pinterest globally",
        },
        {
            "nameEn": "Nissin Cup Noodles Seafood Flavor Japan",
            "name": "日清カップヌードル シーフード",
            "categoryEn": "Japanese Snack",
            "descriptionEn": "The iconic Japan-exclusive seafood flavor Cup Noodle. Foreigners rave about the unique taste unavailable overseas. A must-try souvenir.",
            "description": "日本限定シーフード味カップヌードル。外国人定番土産。",
            "amazonAsin": "B08PFBVXY4",
            "imageSearchQuery": "Nissin Cup Noodles seafood Japan",
            "trendReason": "Japan-exclusive flavors trending in 'things to buy in Japan' content on YouTube",
        },
    ]


# ─────────────────────────────────────────────
# 既存 products.json とのマッチング
# ─────────────────────────────────────────────
def match_existing_product(trend: dict, products: list) -> dict | None:
    """トレンド商品が既存products.jsonにあるか確認（名前・ASINで検索）"""
    trend_name = trend.get("nameEn", "").lower()
    trend_asin = trend.get("amazonAsin", "")

    for p in products:
        # ASIN一致
        asin_m = re.search(r"/dp/([A-Z0-9]{10})", p.get("amazonUrl", ""))
        if trend_asin and asin_m and asin_m.group(1) == trend_asin:
            return p

        # 名前の類似（50%以上のトークンが一致）
        p_name = (p.get("nameEn") or p.get("name", "")).lower()
        t_tokens = set(trend_name.split())
        p_tokens = set(p_name.split())
        if t_tokens and p_tokens:
            overlap = len(t_tokens & p_tokens) / min(len(t_tokens), len(p_tokens))
            if overlap >= 0.5:
                return p

    return None


# ─────────────────────────────────────────────
# Amazon 画像を取得（Gemini が ASIN を知っている場合）
# ─────────────────────────────────────────────
def get_amazon_image_url(asin: str) -> str:
    """Amazon の標準画像URL を構築（公式APIなし）"""
    if not asin or len(asin) < 10:
        return ""
    return f"https://m.media-amazon.com/images/I/default_{asin}._AC_SL500_.jpg"


def get_wikimedia_image(query: str) -> str:
    """Wikimedia Commons から画像URL を取得"""
    import urllib.request, urllib.parse
    search_url = (
        "https://commons.wikimedia.org/w/api.php"
        f"?action=query&list=search&srsearch={urllib.parse.quote(query)}"
        "&srnamespace=6&srlimit=5&format=json"
    )
    req = urllib.request.Request(search_url, headers={"User-Agent": "JapanAdCheck/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        titles = [x["title"] for x in data.get("query", {}).get("search", [])]
        for title in titles:
            info_url = (
                "https://commons.wikimedia.org/w/api.php"
                f"?action=query&titles={urllib.parse.quote(title)}"
                "&prop=imageinfo&iiprop=url|mime|width&format=json"
            )
            req2 = urllib.request.Request(info_url, headers={"User-Agent": "JapanAdCheck/1.0"})
            with urllib.request.urlopen(req2, timeout=8) as r2:
                info = json.loads(r2.read())
            for page in info.get("query", {}).get("pages", {}).values():
                ii = (page.get("imageinfo") or [{}])[0]
                if ii.get("mime") in ("image/jpeg", "image/png") and ii.get("width", 0) >= 600:
                    return ii.get("url", "")
    except Exception:
        pass
    return ""


# ─────────────────────────────────────────────
# 新商品を products.json に追加
# ─────────────────────────────────────────────
def add_new_product(trend: dict, products: list) -> dict:
    """Geminiのトレンドデータから新商品エントリを作成してproducts.jsonに追加"""
    new_id = max((p["id"] for p in products), default=0) + 1
    asin   = trend.get("amazonAsin", "").strip()
    cat_en = trend.get("categoryEn", "Japanese Snack")
    cat_ja = CAT_EN_TO_JA.get(cat_en, "日本のお菓子")

    amazon_url = (
        f"https://www.amazon.co.jp/dp/{asin}?tag={AMAZON_TAG}" if asin
        else ""
    )

    # 画像URL: Amazon → Wikimedia の順で探す
    image_url = ""
    if asin:
        # Amazonの画像URLを試す（複数パターン）
        for img_id in ["61", "71", "51", "81"]:
            test_url = f"https://m.media-amazon.com/images/I/{img_id}XXXXXXXX._AC_SL500_.jpg"
        # 実際には ASIN から画像IDは取れないのでWikimediaを使う
        image_url = get_wikimedia_image(trend.get("imageSearchQuery", trend.get("nameEn", "")))
    if not image_url:
        image_url = get_wikimedia_image(trend.get("imageSearchQuery", trend.get("nameEn", "")))

    new_product = {
        "id":            new_id,
        "name":          trend.get("name", trend.get("nameEn", "")),
        "nameEn":        trend.get("nameEn", ""),
        "category":      cat_ja,
        "categoryEn":    cat_en,
        "image":         image_url,
        "description":   trend.get("description", ""),
        "descriptionEn": trend.get("descriptionEn", ""),
        "amazonUrl":     amazon_url,
        "rakutenUrl":    "",
        "videoNumber":   new_id,
        "trendReason":   trend.get("trendReason", ""),
        "addedAt":       datetime.now().isoformat(),
    }

    products.append(new_product)
    with open(PRODUCTS_JSON, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    print(f"  新商品追加: [{new_id}] {new_product['nameEn']} → products.json")
    return new_product


# ─────────────────────────────────────────────
# トレンドログ管理
# ─────────────────────────────────────────────
def load_trend_log() -> list:
    TREND_LOG.parent.mkdir(parents=True, exist_ok=True)
    if TREND_LOG.exists():
        with open(TREND_LOG, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_trend_log(log: list):
    with open(TREND_LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────
# メイン
# ─────────────────────────────────────────────
def run(dry_run: bool = False, show_trends: bool = False):
    print(f"=== トレンド商品分析 & 投稿 ({datetime.now().strftime('%Y/%m/%d %H:%M')}) ===\n")

    # 1. Gemini でトレンド分析
    print("【Step 1】Gemini でトレンド分析中...")
    trends = analyze_trends_with_gemini()
    if not trends:
        print("トレンドデータが取得できませんでした")
        sys.exit(1)

    for i, t in enumerate(trends, 1):
        print(f"  {i}. {t.get('nameEn','')} — {t.get('trendReason','')}")

    if show_trends:
        print("\nトレンド詳細:")
        print(json.dumps(trends, ensure_ascii=False, indent=2))
        return

    # 2. 既存products.jsonと照合
    with open(PRODUCTS_JSON, encoding="utf-8") as f:
        products = json.load(f)

    print(f"\n【Step 2】既存商品と照合（{len(products)}件）...")

    target_product = None
    target_trend   = None
    trend_log      = load_trend_log()
    recent_ids     = {e["product_id"] for e in trend_log[-20:]}  # 直近20件は除外

    for trend in trends:
        existing = match_existing_product(trend, products)
        if existing:
            if existing["id"] not in recent_ids:
                print(f"  ✅ 既存商品マッチ: [{existing['id']}] {existing.get('nameEn') or existing['name']}")
                target_product = existing
                target_trend   = trend
                break
            else:
                print(f"  ⏭ 最近投稿済み: [{existing['id']}] {existing.get('nameEn') or existing['name']}")
        else:
            print(f"  🆕 新商品: {trend.get('nameEn','')} → 追加します")
            target_product = add_new_product(trend, products)
            target_trend   = trend
            # products.json 再読み込み
            with open(PRODUCTS_JSON, encoding="utf-8") as f:
                products = json.load(f)
            break

    if not target_product:
        # 全部最近投稿済みの場合は最初のトレンドを強制使用
        print("\n全トレンドが最近投稿済み → 最初のトレンドを強制使用")
        existing = match_existing_product(trends[0], products)
        target_product = existing or add_new_product(trends[0], products)
        target_trend   = trends[0]
        with open(PRODUCTS_JSON, encoding="utf-8") as f:
            products = json.load(f)

    name = target_product.get("nameEn") or target_product["name"]
    print(f"\n投稿対象: [{target_product['id']}] {name}")
    if target_trend:
        print(f"トレンド理由: {target_trend.get('trendReason','')}")

    if dry_run:
        print("\n[DRY RUN] 分析のみ完了（動画生成・投稿はスキップ）")
        return

    # 3. 動画生成
    print("\n【Step 3】動画生成...")
    sys.path.insert(0, str(BASE_DIR))
    from product_shorts_creator import create_product_video, generate_description

    safe_name   = name[:20].replace(" ", "_").replace("/", "_")
    output_path = BASE_DIR / "output" / "product_shorts" / f"trend_{target_product['id']:02d}_{safe_name}.mp4"
    success     = create_product_video(target_product, str(output_path))
    if not success:
        print("動画生成失敗")
        sys.exit(1)

    # 4. YouTube アップロード
    print("\n【Step 4】YouTube アップロード...")
    sys.path.insert(0, str(BASE_DIR / "youtube_automation"))
    from youtube_uploader import upload_video

    cat   = target_product.get("categoryEn") or target_product.get("category", "")
    title = f"🇯🇵 {name} - Trending in Japan #Shorts"
    if len(title) > 60:
        title = f"{name} - Trending in Japan #Shorts"
    if len(title) > 60:
        title = f"{name} #Shorts"

    # トレンド理由をdescriptionに追記
    desc = generate_description(target_product)
    if target_trend and target_trend.get("trendReason"):
        desc = f"🔥 Trending now: {target_trend['trendReason']}\n\n" + desc

    tags = [name, "Japan", "JapanTrending", "JapanShopping", "JapaneseSouvenir",
            cat, "Shorts", "JapanExclusive", "VisitJapan", "TrendingJapan"]

    video_id = upload_video(
        video_path=str(output_path),
        title=title,
        description=desc,
        tags=tags,
        privacy="public",
        category_id="22",
    )

    if video_id:
        entry = {
            "product_id":   target_product["id"],
            "product_name": name,
            "video_id":     video_id,
            "url":          f"https://www.youtube.com/shorts/{video_id}",
            "trend_reason": target_trend.get("trendReason", "") if target_trend else "",
            "datetime":     datetime.now().isoformat(),
        }
        trend_log.append(entry)
        save_trend_log(trend_log)
        print(f"\n✅ 投稿完了: https://www.youtube.com/shorts/{video_id}")
        print(f"   商品: {name}")
        print(f"   ログ: {TREND_LOG}")
    else:
        print("❌ アップロード失敗")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="外国人向けトレンド商品の動画を投稿")
    parser.add_argument("--dry-run",     action="store_true", help="分析のみ（動画生成・投稿しない）")
    parser.add_argument("--show-trends", action="store_true", help="トレンド分析結果を表示して終了")
    args = parser.parse_args()
    run(dry_run=args.dry_run, show_trends=args.show_trends)
