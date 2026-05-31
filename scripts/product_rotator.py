"""
Amazon商品データ自動ローテーター（PA-API不使用）

【フロー】
1. data/product_history.json → 過去14日の使用済みキーワードを除外リストに
2. 実行時の「月」からイベント・テーマを決定（例: 4月 = 新生活）
3. data/static_products.json の季節外れ商品をGeminiに検知・置換させる
4. Geminiで本日分5件を新規生成 → data/amazon_deals.json を上書き
5. data/product_history.json に今日のキーワードを追記

商品URL形式:
  静的データ: https://www.amazon.co.jp/dp/{ASIN}/?tag={ASSOCIATE_TAG}（個別商品ページ・成果対象）
  Gemini生成: https://www.amazon.co.jp/s?k={URLエンコード済みキーワード}&tag={ASSOCIATE_TAG}（ASIN未確定時）

実行:
  python3 scripts/product_rotator.py             # 本番実行
  python3 scripts/product_rotator.py --dry-run   # プレビューのみ（ファイル書き込みなし）
  python3 scripts/product_rotator.py --force     # 同日でも強制更新
"""

from __future__ import annotations

import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

# ─────────────────────────────────────────
# パス定義
# ─────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR     = PROJECT_ROOT / "data"
ENV_PATH     = PROJECT_ROOT / ".env"

STATIC_JSON  = DATA_DIR / "static_products.json"
DEALS_JSON   = DATA_DIR / "amazon_deals.json"
HISTORY_JSON = DATA_DIR / "product_history.json"

# ─────────────────────────────────────────
# 環境変数読み込み
# ─────────────────────────────────────────
if ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

ASSOCIATE_TAG    = os.getenv("AMAZON_ASSOCIATE_TAG", "smartearn22-22")
HISTORY_DAYS     = 14    # 過去何日分の商品を除外するか
PRODUCTS_PER_DAY = 5     # 毎日生成する商品数

# ─────────────────────────────────────────
# 月別イベント・テーマ定義（日本の生活サイクル）
# ─────────────────────────────────────────
MONTHLY_EVENTS: dict[int, dict] = {
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
STALE_RULES: list[tuple[list[str], list[int]]] = [
    (["扇風機", "冷却ファン", "USB扇風機", "冷感", "日焼け止め", "UVケア"],   [6, 7, 8]),
    (["ヒーター", "電気毛布", "ホットブランケット", "カイロ", "防寒グッズ"], [11, 12, 1, 2]),
    (["レインコート", "折り畳み傘", "梅雨対策"],                             [6, 7]),
    (["クリスマス", "クリスマスギフト", "クリスマスプレゼント"],              [11, 12]),
    (["花粉", "花粉症対策"],                                                 [2, 3, 4, 5]),
]


# ─────────────────────────────────────────
# ユーティリティ
# ─────────────────────────────────────────
def make_search_url(keyword: str) -> str:
    """Amazon検索URL生成（PA-API不使用・アフィリエイトタグ付き）"""
    return f"https://www.amazon.co.jp/s?k={quote(keyword)}&tag={ASSOCIATE_TAG}"


def get_season(month: int) -> str:
    mapping = {3: "春", 4: "春", 5: "春", 6: "夏", 7: "夏", 8: "夏",
               9: "秋", 10: "秋", 11: "秋"}
    return mapping.get(month, "冬")


def is_stale(product: dict, month: int) -> bool:
    """商品が現在の月に対して季節外れかどうかを判定する"""
    text = " ".join([
        product.get("title", ""),
        product.get("search_keyword", ""),
        " ".join(product.get("features", [])),
        product.get("why_viral", ""),
    ])
    for keywords, valid_months in STALE_RULES:
        if any(kw in text for kw in keywords) and month not in valid_months:
            return True
    return False


# ─────────────────────────────────────────
# 履歴管理
# ─────────────────────────────────────────
def load_history() -> dict:
    if not HISTORY_JSON.exists():
        return {"entries": []}
    try:
        return json.loads(HISTORY_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {"entries": []}


def save_history(history: dict) -> None:
    HISTORY_JSON.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


def get_recent_keywords(history: dict) -> list[str]:
    """過去HISTORY_DAYS日の使用済みキーワードを返す"""
    cutoff = datetime.now() - timedelta(days=HISTORY_DAYS)
    keywords: list[str] = []
    for entry in history.get("entries", []):
        try:
            if datetime.fromisoformat(entry["date"]) >= cutoff:
                keywords.extend(entry.get("keywords", []))
        except (KeyError, ValueError):
            continue
    return list(set(keywords))


def append_history(history: dict, keywords: list[str], month: int, season: str) -> dict:
    """今日のキーワードを履歴に追記し、30日以上前のエントリを削除する"""
    history["entries"].append({
        "date":     datetime.now().isoformat(),
        "keywords": keywords,
        "month":    month,
        "season":   season,
    })
    cutoff = datetime.now() - timedelta(days=30)
    history["entries"] = [
        e for e in history["entries"]
        if datetime.fromisoformat(e.get("date", "2000-01-01")) >= cutoff
    ]
    return history


# ─────────────────────────────────────────
# Gemini による商品生成
# ─────────────────────────────────────────
def generate_via_gemini(
    count: int,
    month: int,
    season: str,
    events: list[str],
    theme: str,
    excluded: list[str],
) -> list[dict]:
    """
    Gemini APIで今日の文脈に最適なAmazon商品を生成する。
    出力は常にJSONフォーマット。
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ GEMINI_API_KEY 未設定")
        return []

    exclusion_note = ""
    if excluded:
        exclusion_note = (
            f"\n\n【重複除外】以下と被る商品・カテゴリは絶対に出さないこと: "
            f"{', '.join(excluded[:20])}"
        )

    prompt = f"""あなたはAmazon Japanのガジェット専門バイヤーです。
今日は{month}月（{season}）です。テーマ: {theme}
今月のイベント: {', '.join(events)}{exclusion_note}

このテーマ・季節に合ったガジェットや電子機器を{count}件推薦してください。
対象ユーザー: ガジェット好きな20〜40代男性。コスパが高く話題になりやすい商品を優先。

以下のJSON配列のみ出力（コードブロック・説明文は不要）:
[
  {{
    "search_keyword": "Amazon検索キーワード（ブランド名+商品種別+スペック、30文字以内）",
    "title": "商品表示タイトル（わかりやすく、40文字以内）",
    "brand": "メーカー名",
    "price_yen": 予想価格（整数、円）,
    "original_price_yen": 定価（整数、必ずprice_yenより大きい）,
    "discount_rate": 割引率（10〜40の整数）,
    "category": "カテゴリ（ガジェット/充電・バッテリー/オーディオ/PC周辺機器/スマートホーム のいずれか）",
    "features": ["特徴1", "特徴2", "特徴3"],
    "why_viral": "ガジェット好きが反応する理由（40文字以内）",
    "story_hook": "思わずクリックしたくなる導入一文（25文字以内）",
    "user_problem": "解決するユーザーの悩み（20文字以内）"
  }}
]

条件:
- {month}月/{season}のイベント（{', '.join(events)}）に合致した商品
- 価格帯は2,000〜20,000円の衝動買いゾーンを優先
- JSON以外は絶対に出力しない"""

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        resp   = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt,
        )
        raw = resp.text.strip()

        # JSONブロック抽出
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        items    = json.loads(raw)
        now_iso  = datetime.now().isoformat()
        products = []

        for item in items[:count]:
            kw    = item.get("search_keyword", item.get("title", ""))
            price = item.get("price_yen", 0)
            orig  = item.get("original_price_yen", price)

            products.append({
                "search_keyword": kw,
                "title":          item.get("title", ""),
                "brand":          item.get("brand", ""),
                "price":          {"amount": price, "currency": "JPY", "display": f"¥{price:,}"},
                "original_price": {"amount": orig,  "display": f"¥{orig:,}"},
                "discount_rate":  item.get("discount_rate", 0),
                "category":       item.get("category", "ガジェット"),
                "features":       item.get("features", []),
                "why_viral":      item.get("why_viral", ""),
                "story_hook":     item.get("story_hook", ""),
                "user_problem":   item.get("user_problem", ""),
                "amazon_url":     make_search_url(kw),
                "source":         "gemini",
                "generated_at":   now_iso,
            })

        return products

    except json.JSONDecodeError as e:
        print(f"❌ JSONパースエラー: {e}")
        try:
            print(f"   Raw（先頭300文字）: {raw[:300]}")
        except Exception:
            pass
        return []
    except Exception as e:
        print(f"❌ Gemini APIエラー: {e}")
        return []


# ─────────────────────────────────────────
# static_products.json 管理
# ─────────────────────────────────────────
def load_static() -> list[dict]:
    if not STATIC_JSON.exists():
        return []
    try:
        return json.loads(STATIC_JSON.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_static(products: list[dict]) -> None:
    STATIC_JSON.write_text(json.dumps(products, ensure_ascii=False, indent=2), encoding="utf-8")


def refresh_stale_static(
    month: int,
    season: str,
    events: list[str],
    theme: str,
    dry_run: bool,
) -> None:
    """
    static_products.json の季節外れ商品をGeminiで検知・置換する。
    """
    static    = load_static()
    if not static:
        print("  ⚠️  static_products.json が存在しないためスキップ")
        return

    stale     = [p for p in static if is_stale(p, month)]
    non_stale = [p for p in static if not is_stale(p, month)]

    if not stale:
        print(f"  ✅ 季節外れなし（{len(static)}件すべて適切）")
        return

    stale_titles = [p.get("title", "")[:20] for p in stale]
    print(f"  ⚠️  季節外れ検知: {len(stale)}/{len(static)} 件")
    for t in stale_titles:
        print(f"     - {t}")

    if dry_run:
        print("  🔍 dry-run: 置換をスキップ")
        return

    print(f"  🤖 Geminiで{len(stale)}件を置換中...")
    excluded = [p.get("search_keyword", p.get("title", "")) for p in non_stale]
    fresh    = generate_via_gemini(
        count=len(stale), month=month, season=season,
        events=events, theme=theme, excluded=excluded,
    )

    if fresh:
        updated = (non_stale + fresh)[:len(static)]
        save_static(updated)
        print(f"  ✅ {len(stale)}件を{season}の旬商品に置換しました")
    else:
        print("  ❌ Gemini生成失敗 → 静的データを維持")


# ─────────────────────────────────────────
# メイン
# ─────────────────────────────────────────
def rotate(dry_run: bool = False, force: bool = False) -> None:
    now    = datetime.now()
    month  = now.month
    season = get_season(month)
    info   = MONTHLY_EVENTS.get(month, {"events": [], "theme": "定番ガジェット"})
    events = info["events"]
    theme  = info["theme"]

    print(f"\n{'=' * 60}")
    print(f"🔄 Amazon商品ローテーター")
    print(f"   {now.strftime('%Y年%m月%d日 %H:%M')} | {season} | {', '.join(events)}")
    print(f"   テーマ: {theme}")
    print(f"{'=' * 60}")

    # 同日スキップ判定（20時間以内に生成済みならスキップ）
    if not force and not dry_run and DEALS_JSON.exists():
        try:
            existing = json.loads(DEALS_JSON.read_text(encoding="utf-8"))
            if existing and existing[0].get("generated_at"):
                age_h = (now - datetime.fromisoformat(existing[0]["generated_at"])).total_seconds() / 3600
                if age_h < 20:
                    print(f"✅ 本日分は生成済み（{age_h:.1f}時間前）→ スキップ")
                    print("   強制更新する場合: --force オプションを使用")
                    return
        except Exception:
            pass

    # 過去14日の使用済みキーワードを取得
    history  = load_history()
    excluded = get_recent_keywords(history)
    if excluded:
        preview = ', '.join(excluded[:8])
        suffix  = f" 他{len(excluded) - 8}件" if len(excluded) > 8 else ""
        print(f"\n📋 除外キーワード（過去{HISTORY_DAYS}日）: {preview}{suffix}")

    # 静的データの季節外れチェック & 置換
    print(f"\n🌸 静的データ鮮度チェック...")
    refresh_stale_static(month, season, events, theme, dry_run)

    # 本日分をGeminiで生成
    print(f"\n🤖 Gemini で本日分 {PRODUCTS_PER_DAY} 件を生成中...")
    products = generate_via_gemini(
        count=PRODUCTS_PER_DAY, month=month, season=season,
        events=events, theme=theme, excluded=excluded,
    )

    # Gemini失敗時は静的データにフォールバック
    if not products:
        print("⚠️  Gemini生成失敗 → data/static_products.json にフォールバック")
        products = load_static()
        if not products:
            print("❌ 静的データも存在しません。終了します。")
            sys.exit(1)
        now_iso = now.isoformat()
        for p in products:
            p["generated_at"] = now_iso
            p["source"]       = "static-fallback"

    # プレビュー表示
    print(f"\n{'─' * 60}")
    print(f"📦 本日の商品 ({len(products)}件)")
    print(f"{'─' * 60}")
    for i, p in enumerate(products, 1):
        price = p.get("price", {}).get("display", "?")
        disc  = p.get("discount_rate", 0)
        hook  = p.get("story_hook", "")
        print(f"\n【{i}】{p.get('title', '')}")
        print(f"   {price}" + (f"  ({disc}%OFF想定)" if disc else ""))
        if hook:
            print(f"   「{hook}」")
        print(f"   {p.get('amazon_url', '')}")

    if dry_run:
        print(f"\n🔍 dry-run モード: ファイルへの書き込みをスキップ")
        return

    # ファイル書き込み
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    DEALS_JSON.write_text(json.dumps(products, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n💾 data/amazon_deals.json を更新（{len(products)}件）")

    used_kw = [p.get("search_keyword", p.get("title", "")) for p in products]
    history = append_history(history, used_kw, month, season)
    save_history(history)
    print(f"📝 data/product_history.json を更新（{len(used_kw)}件追記）")

    print(f"\n✅ 完了")


def main() -> None:
    parser = argparse.ArgumentParser(description="Amazon商品データ自動ローテーター")
    parser.add_argument("--dry-run", action="store_true", help="プレビューのみ（ファイル書き込みなし）")
    parser.add_argument("--force",   action="store_true", help="同日でも強制更新")
    args = parser.parse_args()
    rotate(dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    main()
