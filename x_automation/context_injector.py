"""
リアルタイム・コンテキスト注入モジュール

天候・カレンダーイベントに基づいて、商品の購買意欲スコアを動的に補正する。

【スコア補正の仕組み】
  fetch_amazon_deals.py の score_purchase_intent() の後に呼ばれ、
  「今この瞬間に刺さる商品」を上位に押し上げる。

【コンテキスト例】
  - 雨の日       → レイングッズ・室内用品のスコア +20
  - 給料日(25日) → 15,000円超ガジェットのスコア +15
  - 月曜朝       → 仕事効率化ガジェットのスコア +10
  - 土日         → エンタメ・ゲーム系のスコア +10
  - 夏(7〜8月)   → 冷却グッズ・ポータブル扇風機のスコア +20

使い方:
  # fetch_amazon_deals.py 内から呼ぶ
  from context_injector import apply_context_boost
  products = apply_context_boost(products)

  # 単体テスト
  python3.11 x_automation/context_injector.py
"""

import os
import json
import requests
from datetime import datetime, date
from pathlib import Path

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

# 天候取得先（Open-Meteo: 無料・APIキー不要）
WEATHER_API = "https://api.open-meteo.com/v1/forecast"
TOKYO_LAT   = 35.6895
TOKYO_LON   = 139.6917


# ─────────────────────────────────────────
# コンテキスト取得
# ─────────────────────────────────────────
def get_current_context() -> dict:
    """
    現在の「コンテキスト」を収集する。

    Returns:
        {
          "weather":      "rain" | "snow" | "hot" | "cold" | "clear",
          "temp_celsius": float,
          "is_rainy":     bool,
          "is_hot":       bool,    # 28℃以上
          "is_cold":      bool,    # 10℃以下
          "is_payday":    bool,    # 毎月25日 or 最終営業日
          "is_weekend":   bool,
          "is_monday":    bool,
          "hour":         int,
          "month":        int,
          "day":          int,
          "season":       "spring" | "summer" | "autumn" | "winter",
          "events":       [str],   # 今日のイベント一覧（ログ表示用）
        }
    """
    now  = datetime.now()
    ctx  = {
        "weather":      "clear",
        "temp_celsius": 20.0,
        "is_rainy":     False,
        "is_hot":       False,
        "is_cold":      False,
        "is_payday":    _is_payday(now),
        "is_weekend":   now.weekday() >= 5,
        "is_monday":    now.weekday() == 0,
        "hour":         now.hour,
        "month":        now.month,
        "day":          now.day,
        "season":       _get_season(now.month),
        "events":       [],
    }

    # 天候取得（Open-Meteo）
    weather_info = _fetch_weather()
    if weather_info:
        ctx.update(weather_info)

    # イベントリスト（ログ用）
    events = []
    if ctx["is_rainy"]:  events.append(f"雨（{ctx['temp_celsius']:.0f}℃）")
    if ctx["is_hot"]:    events.append(f"猛暑（{ctx['temp_celsius']:.0f}℃）")
    if ctx["is_cold"]:   events.append(f"寒波（{ctx['temp_celsius']:.0f}℃）")
    if ctx["is_payday"]: events.append("給料日（25日）")
    if ctx["is_weekend"]: events.append("週末")
    if ctx["is_monday"]: events.append("月曜日")
    ctx["events"] = events

    return ctx


def _fetch_weather() -> dict:
    """Open-Meteo API で東京の天候を取得（無料・APIキー不要）"""
    try:
        params = {
            "latitude":   TOKYO_LAT,
            "longitude":  TOKYO_LON,
            "current":    ["temperature_2m", "precipitation", "weathercode"],
            "timezone":   "Asia/Tokyo",
        }
        resp = requests.get(WEATHER_API, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()

        current   = data.get("current", {})
        temp      = current.get("temperature_2m", 20.0)
        precip    = current.get("precipitation", 0.0)
        wcode     = current.get("weathercode", 0)

        # WMO天気コード: 51-67/80-99 = 雨・嵐, 71-77 = 雪
        is_rainy  = (precip > 0.1) or (51 <= wcode <= 67) or (80 <= wcode <= 99)
        is_snowy  = (71 <= wcode <= 77)

        weather = "clear"
        if is_snowy:  weather = "snow"
        elif is_rainy: weather = "rain"
        elif temp >= 28: weather = "hot"
        elif temp <= 10: weather = "cold"

        return {
            "weather":      weather,
            "temp_celsius": temp,
            "is_rainy":     is_rainy,
            "is_hot":       temp >= 28,
            "is_cold":      temp <= 10,
        }

    except Exception as e:
        print(f"  ⚠️  天候取得失敗（フォールバック使用）: {e}")
        return {}


def _is_payday(now: datetime) -> bool:
    """給料日判定: 毎月25日 or それが土日なら前の金曜"""
    if now.day == 25:
        return True
    # 25日が土曜→23日(金)、日曜→24日(金)
    payday = date(now.year, now.month, 25)
    if payday.weekday() == 5 and now.day == 23:  # 土→23日
        return True
    if payday.weekday() == 6 and now.day == 24:  # 日→24日
        return True
    return False


def _get_season(month: int) -> str:
    if month in (3, 4, 5):   return "spring"
    if month in (6, 7, 8):   return "summer"
    if month in (9, 10, 11): return "autumn"
    return "winter"


# ─────────────────────────────────────────
# コンテキスト別スコアブースト定義
# ─────────────────────────────────────────

# 各ルールは: (条件関数, スコアブースト, 対象キーワード, 理由メッセージ)
# 条件関数は context dict を受け取り bool を返す
BOOST_RULES = [
    # ── 天候ルール ──────────────────────────
    {
        "name":     "雨の日ブースト",
        "trigger":  lambda c: c["is_rainy"],
        "boost":    20,
        "keywords": ["レインコート", "傘", "防水", "室内", "ゲーム", "読書",
                     "充電", "モバイルバッテリー", "ノイズキャンセリング", "イヤホン"],
        "message":  "雨天 → 室内用ガジェット・防水グッズのスコアを+20",
    },
    {
        "name":     "猛暑ブースト",
        "trigger":  lambda c: c["is_hot"],
        "boost":    20,
        "keywords": ["扇風機", "冷却", "USB", "ポータブル", "冷感", "ファン",
                     "クーラー", "熱中症", "水筒", "アウトドア"],
        "message":  "猛暑（28℃+） → 冷却グッズのスコアを+20",
    },
    {
        "name":     "寒波ブースト",
        "trigger":  lambda c: c["is_cold"],
        "boost":    15,
        "keywords": ["ヒーター", "暖房", "ホットブランケット", "充電", "手袋",
                     "防寒", "スマートウォッチ", "温度"],
        "message":  "寒波（10℃以下） → 暖房・防寒グッズのスコアを+15",
    },
    # ── カレンダールール ─────────────────────
    {
        "name":     "給料日ブースト",
        "trigger":  lambda c: c["is_payday"],
        "boost":    15,
        "min_price": 15000,
        "message":  "給料日（25日） → 15,000円超ガジェットのスコアを+15",
    },
    {
        "name":     "週末ブースト",
        "trigger":  lambda c: c["is_weekend"],
        "boost":    10,
        "keywords": ["ゲーム", "エンタメ", "スピーカー", "プロジェクター",
                     "アウトドア", "キャンプ", "カメラ", "動画"],
        "message":  "週末 → エンタメ・アウトドア系のスコアを+10",
    },
    {
        "name":     "月曜朝ブースト",
        "trigger":  lambda c: c["is_monday"] and 6 <= c["hour"] <= 10,
        "boost":    10,
        "keywords": ["キーボード", "マウス", "モニター", "充電", "ノート",
                     "生産性", "効率", "仕事", "PC", "ワーク"],
        "message":  "月曜朝 → 仕事効率化ガジェットのスコアを+10",
    },
    # ── 季節ルール ───────────────────────────
    {
        "name":     "夏季ブースト",
        "trigger":  lambda c: c["season"] == "summer",
        "boost":    10,
        "keywords": ["防水", "アウトドア", "USB扇風機", "ポータブル", "日焼け止め"],
        "message":  "夏季（6〜8月） → アウトドア・冷却系を+10",
    },
    {
        "name":     "冬季ブースト",
        "trigger":  lambda c: c["season"] == "winter",
        "boost":    10,
        "keywords": ["充電", "ヒーター", "スマートウォッチ", "イヤーマフ", "グローブ"],
        "message":  "冬季（12〜2月） → 防寒・充電系を+10",
    },
    # ── 時間帯ルール ─────────────────────────
    {
        "name":     "夜の衝動買いブースト",
        "trigger":  lambda c: 21 <= c["hour"] <= 23,
        "boost":    8,
        "keywords": ["セール", "タイムセール", "限定", "値下がり"],
        "message":  "深夜タイム → セール品の購買トリガーを+8",
    },
]


def apply_context_boost(products: list, ctx: dict = None, verbose: bool = True) -> list:
    """
    商品リストにコンテキストブーストを適用して返す。
    スコア更新後、再ソートする。

    Args:
        products: 商品リスト（intent_scoreが付いていること）
        ctx:      コンテキストdict（Noneなら自動取得）
        verbose:  ブースト内容を表示するか

    Returns:
        ブースト適用後の商品リスト（スコア順）
    """
    if ctx is None:
        ctx = get_current_context()

    if verbose:
        events_str = " / ".join(ctx["events"]) if ctx["events"] else "通常"
        print(f"  🌤️  今日のコンテキスト: {events_str}")

    applied_rules = []

    for product in products:
        boost_total = 0
        boost_reasons = []

        for rule in BOOST_RULES:
            # トリガー判定
            try:
                triggered = rule["trigger"](ctx)
            except Exception:
                continue

            if not triggered:
                continue

            # キーワードマッチ
            if "keywords" in rule:
                text = " ".join([
                    product.get("title", ""),
                    product.get("category", ""),
                    product.get("brand", ""),
                    " ".join(product.get("features", [])),
                    product.get("why_viral", ""),
                ]).lower()

                matched = any(kw.lower() in text for kw in rule["keywords"])
                if not matched:
                    continue

            # 価格下限チェック
            if "min_price" in rule:
                price = product.get("price", {}).get("amount", 0)
                if price < rule["min_price"]:
                    continue

            boost_total += rule["boost"]
            boost_reasons.append(rule["name"])

        if boost_total > 0:
            old_score = product.get("intent_score", 50)
            product["intent_score"] = min(100, old_score + boost_total)
            product["context_boost"] = boost_total
            product["boost_reasons"] = boost_reasons
        else:
            product.setdefault("context_boost", 0)
            product.setdefault("boost_reasons", [])

        if boost_total > 0:
            rule_name = boost_reasons[0] if boost_reasons else ""
            if rule_name not in applied_rules:
                applied_rules.append(rule_name)

    if verbose and applied_rules:
        print(f"  🚀 コンテキストブースト適用: {', '.join(applied_rules)}")

    # スコア順に再ソート
    return sorted(products, key=lambda x: x.get("intent_score", 0), reverse=True)


# ─────────────────────────────────────────
# 単体テスト
# ─────────────────────────────────────────
def main():
    print("\n" + "=" * 60)
    print("🌤️  コンテキスト注入テスト")
    print("=" * 60)

    ctx = get_current_context()

    print(f"\n現在のコンテキスト:")
    print(f"  天候    : {ctx['weather']} ({ctx['temp_celsius']:.1f}℃)")
    print(f"  給料日  : {'✅' if ctx['is_payday'] else '❌'}")
    print(f"  週末    : {'✅' if ctx['is_weekend'] else '❌'}")
    print(f"  月曜朝  : {'✅' if ctx['is_monday'] and 6 <= ctx['hour'] <= 10 else '❌'}")
    print(f"  季節    : {ctx['season']}")
    print(f"  時刻    : {ctx['hour']}時")
    print(f"  イベント: {ctx['events'] or ['なし']}")

    # テスト商品でブースト動作確認
    test_products = [
        {
            "title": "Anker モバイルバッテリー 防水 20000mAh",
            "brand": "Anker",
            "category": "充電・バッテリー",
            "features": ["防水IP67", "急速充電対応"],
            "price": {"amount": 4980},
            "intent_score": 65,
            "why_viral": "防水で安心",
        },
        {
            "title": "Logicool MX MASTER 3S マウス",
            "brand": "Logicool",
            "category": "PC周辺機器",
            "features": ["生産性向上", "ワイヤレス"],
            "price": {"amount": 14080},
            "intent_score": 72,
            "why_viral": "仕事効率が上がる",
        },
        {
            "title": "UGREEN USB-C 65W 急速充電器",
            "brand": "UGREEN",
            "category": "ガジェット",
            "features": ["GaN", "急速充電"],
            "price": {"amount": 3480},
            "intent_score": 78,
            "why_viral": "コスパ最強充電器",
        },
    ]

    print(f"\nブースト前スコア:")
    for p in test_products:
        print(f"  {p['title'][:40]:40s} {p['intent_score']}/100")

    boosted = apply_context_boost(test_products, ctx, verbose=True)

    print(f"\nブースト後スコア（スコア順）:")
    for p in boosted:
        cb = p.get("context_boost", 0)
        reasons = ", ".join(p.get("boost_reasons", []))
        boost_str = f" (+{cb} {reasons})" if cb else ""
        print(f"  {p['title'][:40]:40s} {p['intent_score']}/100{boost_str}")

    print()


if __name__ == "__main__":
    main()
