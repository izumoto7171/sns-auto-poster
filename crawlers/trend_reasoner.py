"""
trend_reasoner.py — トレンドワードから売れ筋商品を選別してキューに積む

フロー:
  1. トレンドキーワードを取得（pytrends → 月別季節キーワードでフォールバック）
  2. キーワード → Amazon カテゴリ / 楽天検索キーワード / A8テーマ にマッピング
  3. Amazon・楽天 API で売れ筋商品を上位3件ずつ取得
  4. A8提携済み案件との一致度スコアを算出
  5. 事前フィルタリングを通過したものを context_note 付きで pending_tasks へ保存

クォータ節約設計:
  - context_note はルールベース生成（Gemini不使用）
  - Amazon は fetch_via_gemini（Gemini使用）、楽天は API（Gemini不使用）
  - A8は既存キャッシュとのマッチングのみ（API不要）

使い方:
  python3 crawlers/trend_reasoner.py               # 通常実行
  python3 crawlers/trend_reasoner.py --dry-run     # DB書き込みなし・確認のみ
  python3 crawlers/trend_reasoner.py --kw 節約 転職 # キーワード手動指定
  python3 crawlers/trend_reasoner.py --top 5       # 上位5キーワードで実行
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, date
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "x_automation"))

from crawlers.deal_selector import (
    pre_filter_amazon,
    pre_filter_a8,
    pre_filter_rakuten,
    CACHE_REUSE_DAYS,
)

# ── 定数 ──────────────────────────────────────────────────────
TOP_KEYWORDS      = 3    # 1回の実行で処理するトレンドキーワード数
PRODUCTS_PER_KW   = 3    # キーワードあたりの商品取得数（Amazon/楽天それぞれ）
A8_MATCH_THRESHOLD = 3   # このスコア以上のA8案件のみキューに追加
MAX_PRIORITY      = 10   # pending_tasks の priority 上限

# ── キーワード → Amazonカテゴリ マッピング ────────────────────
# キーワードの部分一致で最初にヒットしたカテゴリを使う
_KW_TO_AMAZON_CATEGORY: list[tuple[list[str], str]] = [
    (["ガジェット", "スマホ", "充電", "イヤホン", "ワイヤレス", "Bluetooth"],          "gadget"),
    (["PC", "パソコン", "モニター", "デスク", "キーボード", "マウス"],                 "pc"),
    (["在宅", "テレワーク", "リモート", "副業", "在宅ワーク", "フリーランス",
      "確定申告", "仕事", "勉強", "ノート"],                                            "pc"),
    (["料理", "調理", "キッチン", "フライパン", "包丁"],                               "cooking_tools"),
    (["食品", "食事", "弁当", "プロテイン", "栄養"],                                   "food"),
    (["掃除", "洗濯", "洗剤", "収納", "整理", "片付け"],                               "cleaning"),
    (["音楽", "スピーカー", "ヘッドホン", "オーディオ"],                               "audio"),
    (["スマートホーム", "スマート家電", "IoT", "温湿度"],                               "smart_home"),
    (["節約", "コスパ", "日用品", "節税", "投資", "NISA", "iDeCo", "ポイ活"],         "daily_goods"),
    (["炊飯", "電子レンジ", "トースター", "コーヒー", "家電"],                         "kitchen"),
]

# ── キーワード → 楽天ジャンルID マッピング（なければキーワード検索にフォールバック）
_KW_TO_RAKUTEN_GENRE: dict[str, str] = {
    "ガジェット":  "213264",   # 家電・カメラ・AV機器
    "キッチン":    "100227",   # キッチン用品
    "食品":        "100316",   # 食品
    "掃除":        "215783",   # 生活家電
    "コスパ":      "558944",   # 生活雑貨
    "ファッション": "100371",  # ファッション
}

# ── キーワード → A8テーマ マッピング ──────────────────────────
_KW_TO_A8_THEMES: dict[str, list[str]] = {
    "確定申告":     ["tax", "accounting", "freelance"],
    "副業":         ["side_hustle", "freelance"],
    "投資":         ["investment_savings", "nisa"],
    "節税":         ["tax", "accounting"],
    "転職":         ["side_hustle", "freelance"],
    "節約":         ["lifestyle", "investment_savings"],
    "クレジット":   ["lifestyle"],
    "保険":         ["lifestyle"],
    "在宅":         ["side_hustle", "productivity"],
    "AI":           ["ai_tools", "side_hustle"],
    "ブログ":       ["blog", "side_hustle"],
    "フリーランス": ["freelance", "side_hustle"],
    "NISA":         ["nisa", "investment_savings"],
    "iDeCo":        ["nisa", "tax"],
    "証券":         ["investment_savings"],
}

# ── キーワード別「有益ツイート」トピック定義 ─────────────────────
# x_info タイプの raw_data に埋め込む豆知識・共感テーマ
_INFO_TOPICS: dict[str, list[tuple[str, str]]] = {
    "副業":      [("tip",     "月1万円を副業で稼ぐための最初の3ステップ"),
                  ("empathy", "副業を始めたいのに一歩が踏み出せない理由")],
    "節約":      [("tip",     "一人暮らしの食費を月2万円以下にする実践法"),
                  ("empathy", "節約しようとするほど続かない…その原因")],
    "確定申告":  [("tip",     "フリーランスが見逃しがちな経費トップ5"),
                  ("empathy", "確定申告の時期に毎年後悔することランキング")],
    "投資":      [("tip",     "新NISAで月3万円積立すると10年後いくらになるか"),
                  ("empathy", "投資を始めたくても「損するのが怖い」人へ")],
    "在宅ワーク": [("tip",    "在宅勤務の集中力を2倍にする環境設定5選"),
                   ("empathy", "在宅勤務でオンオフが切れない人あるある")],
    "転職":      [("tip",     "未経験転職を成功させた人がやっていた準備法"),
                  ("empathy", "転職したいけど動けない人が抱える本音")],
    "AI":        [("tip",     "ChatGPTで月5時間の作業を削減する使い方"),
                  ("empathy", "AIが普及してきて正直焦っている話")],
    "NISA":      [("tip",     "新NISAを今すぐ始めた方がいい3つの理由"),
                  ("empathy", "NISAを始めるタイミングを迷い続けてる人へ")],
    "iDeCo":     [("tip",     "iDeCoで年間いくら節税できるか計算してみた"),
                  ("empathy", "iDeCoを放置してて後悔したこと")],
}

_INFO_TOPICS_DEFAULT = [
    ("tip",     "{keyword}で生活が変わった3つの習慣"),
    ("empathy", "{keyword}を始めたいのに踏み出せない人へ"),
]

# ── 月別季節キーワード（pytrends 失敗時のフォールバック） ─────
_MONTHLY_FALLBACK: dict[int, list[str]] = {
    1:  ["確定申告", "iDeCo", "新NISA", "節税"],
    2:  ["確定申告", "副業収入", "フリーランス"],
    3:  ["新生活", "転職", "引越し", "節約"],
    4:  ["新社会人", "資産運用", "副業"],
    5:  ["副業", "在宅ワーク", "AI副業"],
    6:  ["ボーナス 投資", "新NISA", "節約"],
    7:  ["夏 副業", "FIRE", "節約術"],
    8:  ["AI 稼ぐ", "在宅ワーク", "副業"],
    9:  ["転職", "資産運用", "iDeCo"],
    10: ["年末調整", "保険", "ふるさと納税"],
    11: ["ふるさと納税", "クレジットカード", "節税"],
    12: ["ふるさと納税 締め切り", "確定申告 準備", "節約"],
}


# ─────────────────────────────────────────────────────────────
# トレンドキーワード取得
# ─────────────────────────────────────────────────────────────

def get_trend_keywords(top_n: int = TOP_KEYWORDS) -> list[str]:
    """
    pytrends で日本のトレンドを取得し、上位 top_n 件を返す。
    失敗時は月別季節キーワードで代替。
    """
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl="ja-JP", tz=540, timeout=(10, 30))
        try:
            df = pt.realtime_trending_searches(pn="JP")
            if df is not None and not df.empty:
                kws = df["title"].tolist()[:top_n]
                print(f"[TrendReasoner] pytrends(realtime) 取得: {kws}")
                return kws
        except Exception:
            pass
        df  = pt.trending_searches(pn="japan")
        kws = df[0].tolist()[:top_n]
        print(f"[TrendReasoner] pytrends(daily) 取得: {kws}")
        return kws
    except ImportError:
        print("[TrendReasoner] pytrends 未インストール → 季節キーワード使用")
    except Exception as e:
        print(f"[TrendReasoner] pytrends 失敗: {e} → 季節キーワード使用")

    month = date.today().month
    kws   = _MONTHLY_FALLBACK.get(month, ["節約", "副業", "ガジェット"])[:top_n]
    print(f"[TrendReasoner] 季節キーワード使用: {kws}")
    return kws


# ─────────────────────────────────────────────────────────────
# キーワード → 各サービスマッピング
# ─────────────────────────────────────────────────────────────

def map_keyword(keyword: str) -> dict:
    """
    トレンドキーワードから各サービス向けの情報を導出する。

    Returns:
        {
            "amazon_category": str,        # fetch_deals に渡すカテゴリキー
            "amazon_search_kw": str,       # Gemini生成のヒント用キーワード
            "rakuten_keyword": str,        # 楽天キーワード検索に使う文字列
            "rakuten_genre_id": str|None,  # ジャンルIDがあれば使用
            "a8_themes": list[str],        # A8マッチングに使うテーマリスト
            "affinity_tags": list[str],    # コンテキスト生成用タグ
        }
    """
    amazon_cat = "gadget"  # デフォルト
    for kw_list, cat in _KW_TO_AMAZON_CATEGORY:
        if any(k in keyword for k in kw_list):
            amazon_cat = cat
            break

    rakuten_genre = None
    for k, gid in _KW_TO_RAKUTEN_GENRE.items():
        if k in keyword:
            rakuten_genre = gid
            break

    a8_themes: list[str] = []
    for k, themes in _KW_TO_A8_THEMES.items():
        if k in keyword:
            a8_themes.extend(themes)
    a8_themes = list(dict.fromkeys(a8_themes))  # 重複除去・順序維持

    # 楽天のキーワード検索文字列: 「一人暮らし + トレンドキーワード」にする
    rakuten_kw = f"一人暮らし {keyword}" if len(keyword) <= 6 else keyword

    return {
        "amazon_category":  amazon_cat,
        "amazon_search_kw": keyword,
        "rakuten_keyword":  rakuten_kw,
        "rakuten_genre_id": rakuten_genre,
        "a8_themes":        a8_themes,
        "affinity_tags":    a8_themes[:3],
    }


# ─────────────────────────────────────────────────────────────
# A8 一致度スコア算出
# ─────────────────────────────────────────────────────────────

def score_a8_program(program: dict, keyword: str, a8_themes: list[str]) -> int:
    """
    A8案件とトレンドキーワードの一致度を算出する。

    スコア内訳:
      +5: 商品名にキーワードが含まれる
      +3: themes が a8_themes に一致（最大3テーマ分）
      +2: hashtags にキーワードが含まれる
      +2: sns_score >= 7
      +1: epc >= 15
      +1: confirm_rate >= 15%

    Returns: int (0〜15)
    """
    score = 0
    name       = program.get("name", "")
    hashtags   = " ".join(program.get("hashtags", []))
    prog_themes = program.get("themes", [])

    if keyword in name:
        score += 5

    theme_hits = sum(1 for t in prog_themes if t in a8_themes)
    score += min(theme_hits * 3, 9)

    if keyword in hashtags:
        score += 2

    if program.get("sns_score", 0) >= 7:
        score += 2

    try:
        if float(program.get("epc", 0)) >= 15:
            score += 1
    except (ValueError, TypeError):
        pass

    try:
        rate_str = str(program.get("confirm_rate", "0")).replace("%", "")
        if float(rate_str) >= 15:
            score += 1
    except (ValueError, TypeError):
        pass

    return score


def load_a8_programs() -> list:
    """
    a8_programs_cache.json と program_portfolio.json の両方からA8案件を読み込む。
    重複は ins_id で排除。
    """
    programs: dict[str, dict] = {}

    # a8_programs_cache.json
    cache_path = _ROOT / "money_agent" / "a8_programs_cache.json"
    if cache_path.exists():
        try:
            raw = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                for p in raw:
                    if isinstance(p, dict) and p.get("ins_id"):
                        programs[p["ins_id"]] = p
        except Exception as e:
            print(f"[TrendReasoner] a8_programs_cache 読み込み失敗: {e}")

    # program_portfolio.json（A8 の ins_id が id として入っている）
    portfolio_path = _ROOT / "money_agent" / "config" / "program_portfolio.json"
    if portfolio_path.exists():
        try:
            raw = json.loads(portfolio_path.read_text(encoding="utf-8"))
            for p in raw.get("programs", []):
                pid = p.get("id", "")
                if pid and pid not in programs:
                    # portfolio → a8_programs_cache 形式に変換
                    programs[pid] = {
                        "ins_id":      pid,
                        "name":        p.get("name", ""),
                        "reward":      p.get("reward", ""),
                        "affiliate_url": p.get("affiliate_url", ""),
                        "hashtags":    [],
                        "themes":      p.get("themes", []),
                        "posted_count": 0,
                        "epc":         p.get("epc", 0),
                        "confirm_rate": p.get("confirm_rate", "0%"),
                        "description": p.get("description", ""),
                    }
        except Exception as e:
            print(f"[TrendReasoner] program_portfolio 読み込み失敗: {e}")

    return list(programs.values())


# ─────────────────────────────────────────────────────────────
# context_note 生成（ルールベース、Gemini不使用）
# ─────────────────────────────────────────────────────────────

def build_context_note(
    keyword: str,
    product: dict,
    source: str,
    a8_match: Optional[dict] = None,
    mapping: Optional[dict] = None,
) -> str:
    """
    「なぜ今このトレンドでこの商品なのか」を説明する context_note を生成する。
    Gemini不使用・ルールベースのみ。

    Returns: str (200文字以内)
    """
    today     = datetime.now().strftime("%Y年%-m月")
    parts: list[str] = []

    # ① トレンド起因の説明
    parts.append(f"{today}トレンドキーワード「{keyword}」に基づいて自動選別")

    # ② 商品スペック情報
    if source == "amazon":
        _raw_price   = product.get("price_yen", product.get("price", ""))
        # PA-API は {"amount": 2480} 形式で返す場合がある
        price        = _raw_price.get("amount", 0) if isinstance(_raw_price, dict) else _raw_price
        discount     = product.get("discount_rate", 0)
        title        = product.get("title", product.get("name", ""))[:25]
        why_viral    = product.get("why_viral", "")
        if price:
            parts.append(f"価格:{price}円")
        if discount and int(discount) >= 5:
            parts.append(f"割引{discount}%")
        if why_viral:
            parts.append(f"選定理由: {why_viral[:40]}")
        elif title:
            parts.append(f"商品: {title}")
    elif source == "rakuten":
        price    = product.get("price", product.get("itemPrice", ""))
        reviews  = product.get("review_count", product.get("reviewCount", 0))
        avg      = product.get("review_avg",   product.get("reviewAverage", 0))
        name     = product.get("name", product.get("itemName", ""))[:25]
        if price:
            parts.append(f"価格:{price}円")
        if reviews and int(reviews) > 0:
            parts.append(f"レビュー{reviews}件/{avg}点")
        if name:
            parts.append(f"商品: {name}")
    elif source == "a8":
        reward = product.get("reward", product.get("reward_text", ""))
        name   = product.get("name", "")[:25]
        parts.append(f"A8案件: {name}")
        if reward:
            parts.append(f"報酬: {reward}")

    # ③ A8案件との親和性（商品に紐づけられるA8がある場合）
    if a8_match:
        a8_name  = a8_match["program"].get("name", "")[:20]
        a8_score = a8_match["score"]
        parts.append(f"A8紐付き: {a8_name}(親和性{a8_score}/15)")

    # ④ キーワードの季節性 / 投稿タイミングの根拠
    if mapping and mapping.get("a8_themes"):
        themes_str = "/".join(mapping["a8_themes"][:2])
        parts.append(f"テーマ: {themes_str}")

    note = " | ".join(parts)
    return note[:300]


# ─────────────────────────────────────────────────────────────
# Amazon 商品取得（トレンドキーワード対応）
# ─────────────────────────────────────────────────────────────

def fetch_amazon_for_keyword(keyword: str, category: str, count: int = PRODUCTS_PER_KW) -> list:
    """
    トレンドキーワードに対応する Amazon 商品を取得する。
    PA-API → fetch_via_gemini の順で試みる。
    """
    try:
        sys.path.insert(0, str(_ROOT / "x_automation"))
        from fetch_amazon_deals import fetch_deals, fetch_via_gemini, CATEGORIES

        # まず通常の fetch_deals（キャッシュ優先）
        products = fetch_deals(category=category, count=count)
        if products:
            # キーワードで intent_score を再スコアリング（より関連性の高い商品を優先）
            for p in products:
                kw_bonus = 5 if keyword in p.get("title", "") else 0
                p["intent_score"] = p.get("intent_score", 50) + kw_bonus
            products.sort(key=lambda p: p.get("intent_score", 0), reverse=True)
            print(f"  [Amazon] {category}カテゴリから{len(products[:count])}件取得")
            return products[:count]
    except Exception as e:
        print(f"  [Amazon] fetch_deals 失敗: {e}")

    # フォールバック: Gemini でキーワードに合わせた商品を生成
    try:
        from fetch_amazon_deals import fetch_via_gemini
        products = fetch_via_gemini(category=category, count=count)
        print(f"  [Amazon] Gemini生成で{len(products)}件取得")
        return products[:count]
    except Exception as e:
        print(f"  [Amazon] fetch_via_gemini 失敗: {e}")
    return []


# ─────────────────────────────────────────────────────────────
# 楽天 商品取得
# ─────────────────────────────────────────────────────────────

def fetch_rakuten_for_keyword(
    keyword: str,
    rakuten_keyword: str,
    genre_id: Optional[str],
    count: int = PRODUCTS_PER_KW,
) -> list:
    """
    トレンドキーワードに対応する楽天商品を取得する。
    キーワード検索 → ジャンル検索の順で試みる。
    """
    try:
        from crawlers.crawler_rakuten import fetch_products_by_keyword, fetch_products

        # キーワード検索（より関連性が高い）
        products = fetch_products_by_keyword(rakuten_keyword, hits=count + 3)
        if products:
            print(f"  [楽天] キーワード「{rakuten_keyword}」で{len(products[:count])}件取得")
            return products[:count]

        # フォールバック: ジャンル検索
        if genre_id:
            products = fetch_products(genre_id, hits=count + 3)
            if products:
                print(f"  [楽天] ジャンルID={genre_id}で{len(products[:count])}件取得")
                return products[:count]
    except Exception as e:
        print(f"  [楽天] 商品取得失敗: {e}")
    return []


# ─────────────────────────────────────────────────────────────
# success_metrics 読み込み（priority ボーナス）
# ─────────────────────────────────────────────────────────────

def _load_success_metrics() -> dict:
    """
    Supabase success_metrics テーブルから category → weight_bonus を返す。
    DB未設定・エラー時は空dict（priority ボーナスなし）でフォールバック。
    """
    try:
        from db_client import db
        return db.get_success_metrics_dict()
    except Exception as e:
        print(f"[TrendReasoner] success_metrics 読み込み失敗（スキップ）: {e}")
        return {}


def _metrics_bonus(themes: list[str], category: str, success_metrics: dict) -> int:
    """
    themes・category が success_metrics に含まれる場合、最大 weight_bonus を返す。
    複数ヒットした場合は最大値を採用（加算しない）。
    """
    bonus = success_metrics.get(category, 0)
    for theme in themes:
        bonus = max(bonus, success_metrics.get(theme, 0))
    return min(bonus, 5)  # 最大 +5 までに制限


# ─────────────────────────────────────────────────────────────
# 有益ツイートタスク生成（x_info post_type）
# ─────────────────────────────────────────────────────────────

def _generate_info_tasks(keyword: str, mapping: dict, dry_run: bool) -> int:
    """
    トレンドキーワードから「アフィリリンクなし有益ツイート」タスクを2件生成して
    pending_tasks（post_type='x_info'）に投入する。

    Returns: 追加件数
    """
    topic_key    = next((k for k in _INFO_TOPICS if k in keyword), None)
    topic_pairs  = _INFO_TOPICS.get(topic_key, [
        (t, s.format(keyword=keyword)) for t, s in _INFO_TOPICS_DEFAULT
    ])

    added = 0
    for info_type, topic in topic_pairs:
        raw_data = {
            "keyword":   keyword,
            "info_type": info_type,   # "tip" or "empathy"
            "topic":     topic,
            "category":  mapping.get("amazon_category", "general"),
            "themes":    mapping.get("a8_themes", []),
        }
        product_key = f"info_{keyword}_{info_type}"[:80]

        if not dry_run:
            from db_client import db
            ok     = db.push_pending_task(
                source      = "info",
                product_key = product_key,
                raw_data    = raw_data,
                priority    = 1,
                post_type   = "x_info",
            )
            status = "追加" if ok else "スキップ(既存)"
            print(f"    [Info/{info_type}] {status}: {topic[:50]}")
            if ok:
                added += 1
        else:
            print(f"    [Info/{info_type}] dry-run: {topic[:50]}")

    return added


# ─────────────────────────────────────────────────────────────
# キューへの保存
# ─────────────────────────────────────────────────────────────

def _push_product_to_queue(
    product: dict,
    source: str,
    product_key: str,
    context_note: str,
    priority: int,
    post_type: str,
    dry_run: bool,
) -> bool:
    """事前フィルタ通過済み商品を pending_tasks に保存する。"""
    from db_client import db
    enriched = {**product, "context_note": context_note}
    added = db.push_pending_task(
        source      = source,
        product_key = product_key,
        raw_data    = enriched,
        priority    = priority,
        post_type   = post_type,
    )
    status = "追加" if added else "スキップ(既存)"
    print(f"    [{source}] {status}: {product_key[:45]} (priority={priority})")
    return added


# ─────────────────────────────────────────────────────────────
# メイン: run()
# ─────────────────────────────────────────────────────────────

def run(
    keywords:  Optional[list[str]] = None,
    top_n:     int  = TOP_KEYWORDS,
    post_type: str  = "x",
    dry_run:   bool = False,
) -> dict:
    """
    トレンド分析 → 商品取得 → フィルタリング → キュー投入の全フローを実行する。

    Returns:
        {
            "keywords":        list[str],   # 処理したトレンドキーワード
            "amazon_added":    int,
            "rakuten_added":   int,
            "a8_added":        int,
            "filtered_out":    int,
            "already_queued":  int,
        }
    """
    if keywords is None:
        keywords = get_trend_keywords(top_n=top_n)

    print(f"\n[TrendReasoner] 処理キーワード: {keywords}")
    print(f"[TrendReasoner] post_type={post_type} / dry_run={dry_run}\n")

    a8_programs     = load_a8_programs()
    success_metrics = _load_success_metrics()
    print(f"[TrendReasoner] A8案件ロード: {len(a8_programs)}件")
    print(f"[TrendReasoner] success_metrics: {len(success_metrics)}カテゴリ")

    stats = {
        "keywords":       keywords,
        "amazon_added":   0,
        "rakuten_added":  0,
        "a8_added":       0,
        "info_added":     0,
        "filtered_out":   0,
        "already_queued": 0,
    }

    for kw in keywords:
        print(f"\n── キーワード: 「{kw}」 ──")
        mapping = map_keyword(kw)
        print(f"  Amazon: {mapping['amazon_category']} / 楽天: {mapping['rakuten_keyword']} / A8テーマ: {mapping['a8_themes']}")

        # ── A8 マッチング（API不使用・スコアのみ） ────────────────
        a8_matches: list[dict] = []
        for prog in a8_programs:
            score = score_a8_program(prog, kw, mapping["a8_themes"])
            if score >= A8_MATCH_THRESHOLD:
                a8_matches.append({"program": prog, "score": score})
        a8_matches.sort(key=lambda x: x["score"], reverse=True)

        if a8_matches:
            print(f"  A8マッチ: {len(a8_matches)}件 (top: {a8_matches[0]['program']['name']} / score={a8_matches[0]['score']})")

        top_a8 = a8_matches[0] if a8_matches else None

        # ── Amazon 商品取得 ───────────────────────────────────────
        print(f"  Amazon商品取得中...")
        amazon_products = fetch_amazon_for_keyword(
            keyword  = kw,
            category = mapping["amazon_category"],
            count    = PRODUCTS_PER_KW,
        )
        for product in amazon_products:
            ok, reason = pre_filter_amazon(product)
            if not ok:
                print(f"    [Amazon] フィルタ除外: {reason}")
                stats["filtered_out"] += 1
                continue

            product_key  = product.get("asin") or product.get("search_keyword", product.get("title", ""))[:60]
            context_note = build_context_note(kw, product, "amazon", top_a8, mapping)
            m_bonus      = _metrics_bonus(mapping["a8_themes"], mapping["amazon_category"], success_metrics)
            priority     = min(
                int(product.get("intent_score", 50) / 10) + (top_a8["score"] if top_a8 else 0) + m_bonus,
                MAX_PRIORITY,
            )

            if not dry_run:
                added = _push_product_to_queue(product, "amazon", product_key, context_note, priority, post_type, dry_run)
                if added:
                    stats["amazon_added"] += 1
                else:
                    stats["already_queued"] += 1
            else:
                print(f"    [Amazon] dry-run: {product_key[:45]} | {context_note[:60]}")

        # ── 楽天 商品取得 ─────────────────────────────────────────
        print(f"  楽天商品取得中...")
        rakuten_products = fetch_rakuten_for_keyword(
            keyword         = kw,
            rakuten_keyword = mapping["rakuten_keyword"],
            genre_id        = mapping["rakuten_genre_id"],
            count           = PRODUCTS_PER_KW,
        )
        for product in rakuten_products:
            ok, reason = pre_filter_rakuten(product)
            if not ok:
                print(f"    [楽天] フィルタ除外: {reason}")
                stats["filtered_out"] += 1
                continue

            product_key  = product.get("url") or product.get("name", "")[:60]
            context_note = build_context_note(kw, product, "rakuten", top_a8, mapping)

            # レビュー数・評価が高いほど priority を上げる
            review_bonus = min(int(product.get("review_count", product.get("reviewCount", 0)) / 100), 3)
            m_bonus      = _metrics_bonus(mapping["a8_themes"], mapping["amazon_category"], success_metrics)
            priority     = min(2 + review_bonus + (top_a8["score"] if top_a8 else 0) + m_bonus, MAX_PRIORITY)

            if not dry_run:
                added = _push_product_to_queue(product, "rakuten", product_key, context_note, priority, post_type, dry_run)
                if added:
                    stats["rakuten_added"] += 1
                else:
                    stats["already_queued"] += 1
            else:
                print(f"    [楽天] dry-run: {product_key[:45]} | {context_note[:60]}")

        # ── A8 高スコア案件をキューに投入 ─────────────────────────
        # A8はAPIを叩かず既存キャッシュから直接追加
        for match in a8_matches[:2]:  # 上位2件のみ
            prog  = match["program"]
            score = match["score"]

            ok, reason = pre_filter_a8(prog)
            if not ok:
                print(f"    [A8] フィルタ除外: {reason}")
                stats["filtered_out"] += 1
                continue

            product_key  = prog.get("ins_id", prog.get("name", ""))[:80]
            context_note = build_context_note(kw, prog, "a8", None, mapping)
            m_bonus      = _metrics_bonus(mapping["a8_themes"], mapping["amazon_category"], success_metrics)
            priority     = min(score + m_bonus, MAX_PRIORITY)

            if not dry_run:
                added = _push_product_to_queue(prog, "a8", product_key, context_note, priority, post_type, dry_run)
                if added:
                    stats["a8_added"] += 1
                else:
                    stats["already_queued"] += 1
            else:
                print(f"    [A8] dry-run: {prog.get('name','')[:40]} (score={score}) | {context_note[:60]}")

        # ── 有益ツイートタスク（x_info）を生成 ───────────────────────
        print(f"  有益ツイートタスク生成中...")
        info_n = _generate_info_tasks(kw, mapping, dry_run)
        stats["info_added"] += info_n

    return stats


# ─────────────────────────────────────────────────────────────
# CLI エントリポイント
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="トレンドベースの商品選別 → キュー投入")
    parser.add_argument("--kw",        nargs="+", default=None,      help="キーワード手動指定（スペース区切り）")
    parser.add_argument("--top",       type=int,  default=TOP_KEYWORDS, help=f"取得するトレンドキーワード数 (デフォルト: {TOP_KEYWORDS})")
    parser.add_argument("--post-type", type=str,  default="x",       help="投稿タイプ (デフォルト: x)")
    parser.add_argument("--dry-run",   action="store_true",          help="DB書き込みなし・確認のみ")
    args = parser.parse_args()

    result = run(
        keywords  = args.kw,
        top_n     = args.top,
        post_type = args.post_type,
        dry_run   = args.dry_run,
    )

    print("\n" + "="*50)
    print("[TrendReasoner] 実行結果")
    print(f"  キーワード: {result['keywords']}")
    print(f"  Amazon追加:   {result['amazon_added']}件")
    print(f"  楽天追加:     {result['rakuten_added']}件")
    print(f"  A8追加:       {result['a8_added']}件")
    print(f"  有益ツイート: {result['info_added']}件 (x_info)")
    print(f"  フィルタ除外: {result['filtered_out']}件")
    print(f"  既存スキップ: {result['already_queued']}件")
    total = result["amazon_added"] + result["rakuten_added"] + result["a8_added"] + result["info_added"]
    print(f"  合計キュー追加: {total}件")
