"""
Amazon商品データの自動ローテーター（PA-API不使用）

【フロー】
1. product_history.json から過去14日の使用済みキーワードを読み込む
2. 今日の季節・月別イベントを取得
3. static_products.json の季節外れ商品を検知して差し替え
4. Gemini APIで「今日の文脈に合った新商品」を生成（重複除外）
5. amazon_deals.json + product_history.json を更新

URL形式（PA-API不使用のため検索URL）:
  https://www.amazon.co.jp/s?k={URLエンコード済みキーワード}&tag={ASSOCIATE_TAG}

実行:
  python3 x_automation/product_rotator.py             # 本番実行
  python3 x_automation/product_rotator.py --dry-run   # プレビューのみ（ファイル書き込みなし）
  python3 x_automation/product_rotator.py --force     # 同日でも強制更新
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

BASE_DIR = Path(__file__).parent
ROOT_DIR = BASE_DIR.parent

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

ASSOCIATE_TAG    = os.getenv("AMAZON_ASSOCIATE_TAG", "smartearn22-22")
HISTORY_DAYS     = 14    # 過去何日分の履歴を除外するか
PRODUCTS_PER_DAY = 5     # 毎日生成する商品数


# ─────────────────────────────────────────
# 月別イベント・テーマ定義（日本の生活サイクル）
# ─────────────────────────────────────────
MONTHLY_EVENTS = {
    1:  {"events": ["新年", "初売り", "正月セール"],   "theme": "新年の気持ちの切り替えと自己投資"},
    2:  {"events": ["バレンタイン", "受験シーズン"],   "theme": "プレゼントと集中力向上ガジェット"},
    3:  {"events": ["新生活準備", "卒業", "春"],       "theme": "新生活を快適にするガジェット"},
    4:  {"events": ["新生活", "入学", "春"],           "theme": "新社会人・新学生のガジェット揃え"},
    5:  {"events": ["GW", "母の日", "春"],             "theme": "GW旅行と母の日プレゼント"},
    6:  {"events": ["梅雨", "父の日"],                 "theme": "梅雨の室内生活と父の日プレゼント"},
    7:  {"events": ["夏", "プライムデー", "夏休み"],   "theme": "夏のアウトドアと冷却ガジェット"},
    8:  {"events": ["夏", "お盆", "夏休み"],           "theme": "夏休みのエンタメとアウトドア"},
    9:  {"events": ["秋", "敬老の日"],                 "theme": "秋の学習・仕事効率化ガジェット"},
    10: {"events": ["ハロウィン", "秋"],               "theme": "秋の充実した生活と趣味ガジェット"},
    11: {"events": ["ブラックフライデー", "年末準備"], "theme": "年末の大型セールと年末大掃除"},
    12: {"events": ["クリスマス", "年末", "贈り物"],   "theme": "クリスマスプレゼントと年末まとめ買い"},
}

# ─────────────────────────────────────────
# 季節外れ検知ルール
# (キーワードリスト, 有効な月リスト)
# ─────────────────────────────────────────
STALE_RULES = [
    (["扇風機", "冷却ファン", "USB扇風機", "冷感", "冷却スプレー", "UVケア", "日焼け止め"], [6, 7, 8]),
    (["ヒーター", "電気毛布", "ホットブランケット", "カイロ", "防寒", "ホット"], [11, 12, 1, 2]),
    (["レインコート", "折り畳み傘", "梅雨"], [6, 7]),
    (["クリスマス", "プレゼント包装", "クリスマスギフト"], [11, 12]),
    (["花粉", "花粉症"], [2, 3, 4, 5]),
]


def make_search_url(keyword: str) -> str:
    """Amazon検索URL生成（PA-API不使用・アフィリエイトタグ付き）"""
    return f"https://www.amazon.co.jp/s?k={quote(keyword)}&tag={ASSOCIATE_TAG}"


def get_season(month: int) -> str:
    if month in (3, 4, 5):   return "春"
    if month in (6, 7, 8):   return "夏"
    if month in (9, 10, 11): return "秋"
    return "冬"


# ─────────────────────────────────────────
# 履歴管理（DB版）
# ─────────────────────────────────────────
def get_recent_keywords(days: int = HISTORY_DAYS) -> list:
    """過去N日の使用済みキーワードを DB から返す"""
    try:
        return db.get_recent_keywords(days=days)
    except Exception as e:
        print(f"  ⚠️  キーワード履歴DB読み込み失敗: {e}")
        return []


def add_history_entry(keywords: list, month: int, season: str) -> None:
    """今日の使用済みキーワードを DB に INSERT する（古いエントリは自動削除）"""
    try:
        db.add_keyword_history(keywords, month, season)
    except Exception as e:
        print(f"  ⚠️  キーワード履歴DB書き込み失敗: {e}")


# ─────────────────────────────────────────
# 季節外れ検知
# ─────────────────────────────────────────
def is_stale(product: dict, month: int) -> bool:
    """商品が現在の月に対して季節外れかどうか判定"""
    text = " ".join([
        product.get("title", ""),
        product.get("search_keyword", ""),
        " ".join(product.get("features", [])),
        product.get("why_viral", ""),
    ])
    for keywords, valid_months in STALE_RULES:
        if any(kw in text for kw in keywords):
            if month not in valid_months:
                return True
    return False


# ─────────────────────────────────────────
# Gemini による商品生成
# ─────────────────────────────────────────
def generate_products_via_gemini(
    count: int,
    month: int,
    season: str,
    events: list,
    theme: str,
    excluded_keywords: list,
) -> list:
    """
    Gemini APIを使って今日の文脈に最適なAmazon商品を生成する。
    URLはAmazon検索URL形式（PA-API不使用）で出力させる。
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ GEMINI_API_KEY 未設定")
        return []

    exclusion_note = ""
    if excluded_keywords:
        recent = excluded_keywords[:20]
        exclusion_note = f"\n\n【除外】最近紹介済みのため以下と被る商品は出さないこと: {', '.join(recent)}"

    prompt = f"""あなたはAmazon Japanのガジェット専門バイヤーです。
今日は{month}月（{season}）です。
今月のテーマ: {theme}
今月のイベント: {', '.join(events)}{exclusion_note}

上記の文脈で「今のユーザーが抱えそうな悩み」を解決するガジェット・電子機器を{count}件推薦してください。
ガジェット好きな20〜40代男性をターゲットにした、コスパが良く話題になりやすい商品を選ぶこと。

以下のJSON配列のみ出力（説明文・コードブロック不要）:
[
  {{
    "search_keyword": "Amazon検索に使う短いキーワード（ブランド名+商品種別+スペック、例: Anker GaN 65W 充電器）",
    "title": "商品の表示タイトル（わかりやすく簡潔に、40文字以内）",
    "brand": "メーカー名",
    "price_yen": 予想価格（整数、円）,
    "original_price_yen": 定価想定（整数、円。セール価格より高く設定）,
    "discount_rate": 想定割引率（0〜50の整数）,
    "category": "カテゴリ名（ガジェット/充電・バッテリー/オーディオ/PC周辺機器/スマートホーム のいずれか）",
    "features": ["特徴1", "特徴2", "特徴3"],
    "why_viral": "ガジェット好きがこれに反応する理由（50文字以内）",
    "story_hook": "思わずクリックしたくなる導入一文（30文字以内）",
    "user_problem": "この商品が解決するユーザーの悩み（20文字以内）"
  }}
]

条件:
- {month}月の季節・イベント（{', '.join(events)}）に合致した商品を選ぶこと
- 2,000〜20,000円の価格帯を優先（衝動買いしやすいゾーン）
- JSON以外は絶対に出力しない"""

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        resp   = client.models.generate_content(
            model="gemini-2.0-flash-lite",
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
        now_iso  = datetime.now().isoformat()

        for item in items[:count]:
            keyword = item.get("search_keyword", item.get("title", ""))
            price   = item.get("price_yen", 0)
            orig    = item.get("original_price_yen", price)

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
                "discount_rate":  item.get("discount_rate", 0),
                "category":       item.get("category", "ガジェット"),
                "features":       item.get("features", []),
                "why_viral":      item.get("why_viral", ""),
                "story_hook":     item.get("story_hook", ""),
                "user_problem":   item.get("user_problem", ""),
                "amazon_url":     make_search_url(keyword),
                "source":         "gemini-rotator",
                "fetched_at":     now_iso,
                "intent_score":   50,
                "context_boost":  0,
                "boost_reasons":  [],
            })

        return products

    except json.JSONDecodeError as e:
        print(f"❌ JSONパースエラー: {e}")
        print(f"   Raw: {raw[:300]}")
        return []
    except Exception as e:
        print(f"❌ Gemini APIエラー: {e}")
        return []


# ─────────────────────────────────────────
# static_products 管理（DB版）
# ─────────────────────────────────────────
def load_static_products() -> list:
    """静的商品マスタを DB から返す"""
    try:
        return db.get_static_products()
    except Exception as e:
        print(f"  ⚠️  静的商品DB読み込み失敗: {e}")
        return []


def save_static_products(products: list) -> None:
    """静的商品マスタを DB に保存する"""
    try:
        db.save_static_products(products)
    except Exception as e:
        print(f"  ⚠️  静的商品DB書き込み失敗: {e}")


def refresh_stale_static(month: int, season: str, events: list, theme: str, dry_run: bool = False):
    """
    static_products.json の季節外れ商品を検知してGeminiで差し替える。
    """
    static = load_static_products()
    if not static:
        print("  ⚠️  static_products.json が存在しないためスキップ")
        return

    stale    = [p for p in static if is_stale(p, month)]
    non_stale = [p for p in static if not is_stale(p, month)]

    if not stale:
        print(f"  ✅ 静的データに季節外れなし（{len(static)}件すべて適切）")
        return

    stale_titles = [p.get("title", "")[:25] for p in stale]
    print(f"  ⚠️  季節外れ検知 {len(stale)}/{len(static)} 件: {stale_titles}")

    if dry_run:
        print("  🔍 dry-run: 差し替えはスキップ")
        return

    non_stale_keywords = [p.get("search_keyword", p.get("title", "")) for p in non_stale]
    fresh = generate_products_via_gemini(
        count=len(stale),
        month=month,
        season=season,
        events=events,
        theme=theme,
        excluded_keywords=non_stale_keywords,
    )

    if not fresh:
        print("  ❌ 差し替え用Gemini生成失敗 → 静的データ維持")
        return

    new_static = non_stale + fresh
    save_static_products(new_static[:len(static)])
    print(f"  ✅ 静的データ更新: {len(stale)}件を{season}の旬商品に差し替え")


# ─────────────────────────────────────────
# インテントスコアリング（fetch_amazon_deals.py との連携）
# ─────────────────────────────────────────
def score_products(products: list) -> list:
    """購買意欲スコアとコンテキストブーストを適用する"""
    try:
        sys.path.insert(0, str(BASE_DIR))
        from fetch_amazon_deals import score_purchase_intent
        from context_injector import apply_context_boost, get_current_context

        for p in products:
            p["intent_score"] = score_purchase_intent(p)

        ctx = get_current_context()
        return apply_context_boost(products, ctx, verbose=True)

    except Exception as e:
        print(f"  ⚠️  スコアリングスキップ: {e}")
        return products


# ─────────────────────────────────────────
# メイン処理
# ─────────────────────────────────────────
def rotate(dry_run: bool = False, force: bool = False):
    """
    商品ローテーションを実行する。

    Args:
        dry_run: Trueの場合、ファイル書き込みを行わない（プレビューのみ）
        force:   同日でも強制更新する
    """
    now    = datetime.now()
    month  = now.month
    season = get_season(month)
    monthly = MONTHLY_EVENTS.get(month, {"events": [], "theme": "定番ガジェット"})
    events  = monthly["events"]
    theme   = monthly["theme"]

    print(f"\n{'=' * 60}")
    print(f"🔄 Amazon商品ローテーター")
    print(f"   {now.strftime('%Y年%m月%d日 %H:%M')} | {season} | {', '.join(events)}")
    print(f"   テーマ: {theme}")
    print(f"{'=' * 60}")

    # 同日実行チェック（20時間以内はスキップ）
    if not force and not dry_run:
        try:
            age_hours = db.get_last_amazon_deal_age_hours()
            if age_hours is not None and age_hours < 20:
                print(f"✅ 本日分は生成済み（{age_hours:.1f}時間前）→ スキップ")
                print("   強制更新する場合: --force オプションを使用")
                return
        except Exception:
            pass

    # 履歴から除外キーワードを取得
    excluded = get_recent_keywords(days=HISTORY_DAYS)
    if excluded:
        print(f"\n📋 除外キーワード（過去{HISTORY_DAYS}日）: {', '.join(excluded[:10])}" +
              (f" 他{len(excluded) - 10}件" if len(excluded) > 10 else ""))

    # 静的データの季節外れチェック
    print(f"\n🌸 静的データの鮮度チェック...")
    refresh_stale_static(month, season, events, theme, dry_run=dry_run)

    # Geminiで新商品を生成
    print(f"\n🤖 Geminiで{PRODUCTS_PER_DAY}件の商品を生成中...")
    products = generate_products_via_gemini(
        count=PRODUCTS_PER_DAY,
        month=month,
        season=season,
        events=events,
        theme=theme,
        excluded_keywords=excluded,
    )

    if not products:
        print("❌ Gemini生成失敗 → 静的データにフォールバック")
        products = load_static_products()
        if not products:
            print("❌ 静的データも存在しません。終了します。")
            sys.exit(1)

    # スコアリング適用
    products = score_products(products)

    # プレビュー表示
    print(f"\n{'─' * 60}")
    print(f"📦 生成された商品 ({len(products)}件)")
    print(f"{'─' * 60}")
    for i, p in enumerate(products, 1):
        price  = p.get("price", {}).get("display", "不明")
        disc   = p.get("discount_rate", 0)
        score  = p.get("intent_score", 0)
        boost  = p.get("context_boost", 0)
        hook   = p.get("story_hook", "")
        url    = p.get("amazon_url", "")
        print(f"\n【{i}】{p['title']}")
        print(f"   価格: {price}" + (f"  ({disc}%OFF想定)" if disc else ""))
        print(f"   スコア: {score}/100" + (f"  (+{boost} コンテキストブースト)" if boost else ""))
        if hook:
            print(f"   フック: {hook}")
        print(f"   URL: {url}")

    if dry_run:
        print(f"\n{'=' * 60}")
        print("🔍 dry-run モード: ファイル書き込みをスキップ")
        print(f"{'=' * 60}")
        return

    # amazon_products DB 更新
    try:
        db.save_amazon_deals(products)
        print(f"\n💾 amazon_products テーブルを更新 ({len(products)}件)")
    except Exception as e:
        print(f"⚠️  amazon_products DB書き込み失敗: {e}")

    # keyword_history DB 更新
    used_keywords = [p.get("search_keyword", p.get("title", "")) for p in products]
    add_history_entry(used_keywords, month, season)
    print(f"📝 keyword_history テーブルを更新 ({len(used_keywords)}件追記)")

    print(f"\n✅ ローテーション完了")


def main():
    parser = argparse.ArgumentParser(description="Amazon商品データ自動ローテーター")
    parser.add_argument("--dry-run", action="store_true", help="プレビューのみ（ファイル書き込みなし）")
    parser.add_argument("--force",   action="store_true", help="同日でも強制更新")
    args = parser.parse_args()
    rotate(dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    main()
