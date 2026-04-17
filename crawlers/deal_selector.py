"""
deal_selector.py — 全アフィリエイトサービスから「今一番熱い」案件を選ぶ

シグナル:
  楽天  : 0/5のつく日（ポイントアップ日）はスコア×2.0
  A8    : 月ごとの季節トレンドキーワードに合う案件をスコア×1.5〜2.0
  Amazon: 大型セール日（Prime Day / Black Friday 等）はスコア×2.0〜3.0

使い方:
  from crawlers.deal_selector import select_best_deal
  result = select_best_deal()
  # result = {
  #   "service": "a8",
  #   "deal":    {...},
  #   "score":   2.0,
  #   "reason":  "A8: 確定申告シーズン (×2.0) — freee（クラウド会計）",
  # }

各サービスのスコアを重みとして加重ランダム選択するため、
スコアが高いサービスが「高確率で」選ばれるが、毎回同じにはならない。
"""
from __future__ import annotations

import random
from datetime import date, datetime
from pathlib import Path
from typing import NamedTuple
import sys

_ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT_DIR))


# ── 型定義 ────────────────────────────────────────────────────

class ServiceScore(NamedTuple):
    service: str       # "rakuten" | "a8" | "amazon"
    score:   float     # ベーススコア × 各種倍率
    reason:  str       # ログ出力用の理由
    boosted_ids: list  # A8 の場合: ブースト対象 ins_id のリスト（優先選択に使用）


# ── 楽天: 0/5のつく日チェック ────────────────────────────────

def _rakuten_score(today: date) -> ServiceScore:
    """
    楽天の「5と0のつく日」（毎月 5/10/15/20/25/30日）は
    楽天カード利用でポイント5倍 → CVR が大幅アップするため、
    その日はベーススコア 1.0 を 2.0 に引き上げる。
    """
    BASE   = 1.0
    score  = BASE
    reason = "楽天: 通常日"

    day = today.day
    if day % 5 == 0:
        score  = BASE * 2.0
        reason = f"楽天: {day}日（5と0のつく日 ×2.0）"

    return ServiceScore("rakuten", score, reason, boosted_ids=[])


# ── A8: 季節トレンドキーワード ────────────────────────────────

# { (開始月, 終了月): [キーワード群] }
# 月は「以上・以下」で判定（跨ぎは年をまたいで処理）
_A8_SEASONAL: list[tuple[tuple[int, int], list[str], float]] = [
    ((1, 3),   ["確定申告", "税金", "節税", "iDeCo", "ふるさと納税", "クラウド会計"],  2.0),
    ((3, 4),   ["転職", "就活", "新生活", "クレジットカード", "引越し"],               1.6),
    ((5, 6),   ["副業", "在宅ワーク", "サイドFIRE"],                                  1.4),
    ((6, 8),   ["夏のボーナス", "投資", "証券口座", "NISA", "つみたてNISA"],          1.8),
    ((9, 10),  ["転職", "副業", "在宅ワーク", "FX"],                                  1.5),
    ((10, 11), ["年末調整", "保険", "医療保険", "生命保険"],                           1.6),
    ((11, 12), ["クレジットカード", "ポイ活", "楽天カード", "ふるさと納税"],           1.8),
]


def _a8_score(today: date, programs: list) -> ServiceScore:
    """
    現在月に合う季節キーワードを A8 キャッシュ内のプログラム名・ハッシュタグと照合し、
    マッチした案件をブーストする。
    """
    BASE  = 1.0
    month = today.month

    matched_keywords: list[str] = []
    best_multiplier = 1.0

    for (m_start, m_end), keywords, multiplier in _A8_SEASONAL:
        if m_start <= month <= m_end:
            matched_keywords.extend(keywords)
            best_multiplier = max(best_multiplier, multiplier)

    # キャッシュ内プログラムのうちキーワードにマッチする ins_id を収集
    boosted_ids: list[str] = []
    for prog in programs:
        name      = prog.get("name", "")
        hashtags  = " ".join(prog.get("hashtags", []))
        combined  = name + " " + hashtags
        if any(kw in combined for kw in matched_keywords):
            boosted_ids.append(prog.get("ins_id", ""))

    if matched_keywords and boosted_ids:
        score  = BASE * best_multiplier
        reason = (
            f"A8: {matched_keywords[0]}シーズン (×{best_multiplier}) "
            f"— マッチ案件 {len(boosted_ids)}件"
        )
    elif matched_keywords:
        # キーワードはあるが合う案件がない → 軽微なブーストのみ
        score  = BASE * 1.2
        reason = f"A8: {matched_keywords[0]}シーズン (キャッシュ未マッチ ×1.2)"
    else:
        score  = BASE
        reason = "A8: 通常日（季節シグナルなし）"

    return ServiceScore("a8", score, reason, boosted_ids=boosted_ids)


# ── Amazon: 大型セール日 ──────────────────────────────────────

# (月, 開始日, 終了日, 名前, 倍率)
_AMAZON_SALES: list[tuple[int, int, int, str, float]] = [
    (3, 1,  10, "新生活セール",      1.6),
    (6, 21, 30, "夏のセール開始",    1.5),
    (7, 11, 14, "Prime Day",         3.0),
    (10, 1, 10, "初秋セール",        1.5),
    (11, 22, 30, "Black Friday",     2.5),
    (12, 1,  5, "Cyber Monday週",    2.0),
    (12, 20, 25, "年末大型セール",   1.8),
]


def _amazon_score(today: date) -> ServiceScore:
    BASE  = 1.0
    month = today.month
    day   = today.day

    for m, d_start, d_end, name, multiplier in _AMAZON_SALES:
        if m == month and d_start <= day <= d_end:
            score  = BASE * multiplier
            reason = f"Amazon: {name} (×{multiplier})"
            return ServiceScore("amazon", score, reason, boosted_ids=[])

    return ServiceScore("amazon", BASE, "Amazon: 通常日", boosted_ids=[])


# ── 各サービスから実際の案件を取得 ────────────────────────────

def _fetch_rakuten_deal(genre_id: str = "100371") -> dict:
    """楽天から代表商品を1件取得する"""
    try:
        from crawlers.crawler_rakuten import fetch_products
        products = fetch_products(genre_id, hits=10)
        if products:
            return random.choice(products[:5])  # 上位5件からランダム
    except Exception as e:
        print(f"  [DealSelector] 楽天案件取得失敗: {e}")
    return {}


def _fetch_a8_deal(programs: list, boosted_ids: list) -> dict:
    """
    A8 から1プログラムを選択する。
    boosted_ids があればその中から weighted_choice、
    なければ全プログラムから weighted_choice。
    """
    try:
        from crawlers.crawler_a8 import weighted_choice
        candidates = (
            [p for p in programs if p.get("ins_id") in boosted_ids]
            if boosted_ids
            else programs
        )
        if not candidates:
            candidates = programs
        return weighted_choice(candidates[-20:])
    except Exception as e:
        print(f"  [DealSelector] A8案件取得失敗: {e}")
    return {}


def _fetch_amazon_deal(category: str = "gadget") -> dict:
    """Amazon から1商品を取得する"""
    try:
        from crawlers.crawler_amazon import fetch_deals
        products = fetch_deals(category=category, count=5)
        if products:
            return products[0]
    except Exception as e:
        print(f"  [DealSelector] Amazon案件取得失敗: {e}")
    return {}


# ── メイン: select_best_deal ─────────────────────────────────

def select_best_deal(
    rakuten_genre_id: str = "100371",  # 楽天デフォルトジャンル（スポーツ・アウトドア）
    amazon_category:  str = "gadget",
    verbose: bool = True,
) -> dict:
    """
    全アフィリエイトサービスのコンテキストスコアを算出し、
    加重ランダム選択で「今一番熱い」サービスを決定して案件を返す。

    Returns:
        {
            "service": "rakuten" | "a8" | "amazon",
            "deal":    {...},   # 各サービスの案件 dict
            "score":   float,
            "reason":  str,
        }
        失敗時は {}
    """
    today    = date.today()
    now_str  = datetime.now().strftime("%Y-%m-%d %H:%M")

    # A8 キャッシュを先に読んでおく（スコア算出に必要）
    try:
        from crawlers.crawler_a8 import load_programs
        a8_programs = load_programs()
    except Exception:
        a8_programs = []

    # ── 各サービスのスコア算出 ────────────────────────────────
    scores: list[ServiceScore] = [
        _rakuten_score(today),
        _a8_score(today, a8_programs),
        _amazon_score(today),
    ]

    if verbose:
        print(f"  [DealSelector] {now_str} スコア計算:")
        for s in scores:
            print(f"    {s.service:10s} score={s.score:.2f}  {s.reason}")

    # ── 加重ランダム選択（スコアが高いほど選ばれやすい） ─────
    weights  = [s.score for s in scores]
    selected = random.choices(scores, weights=weights, k=1)[0]

    if verbose:
        print(f"  [DealSelector] 選択サービス: {selected.service} ({selected.reason})")

    # ── 選択サービスから実際の案件を取得 ─────────────────────
    deal: dict = {}

    if selected.service == "rakuten":
        deal = _fetch_rakuten_deal(rakuten_genre_id)
    elif selected.service == "a8":
        deal = _fetch_a8_deal(a8_programs, selected.boosted_ids)
    elif selected.service == "amazon":
        deal = _fetch_amazon_deal(amazon_category)

    if not deal:
        # 失敗時は他サービスをフォールバック順に試す
        fallback_order = [s for s in scores if s.service != selected.service]
        fallback_order.sort(key=lambda s: s.score, reverse=True)
        for fallback in fallback_order:
            if fallback.service == "rakuten":
                deal = _fetch_rakuten_deal(rakuten_genre_id)
            elif fallback.service == "a8":
                deal = _fetch_a8_deal(a8_programs, fallback.boosted_ids)
            elif fallback.service == "amazon":
                deal = _fetch_amazon_deal(amazon_category)
            if deal:
                selected = fallback
                print(f"  [DealSelector] フォールバック → {fallback.service}")
                break

    if not deal:
        return {}

    # A8 選択時は posted_count をインクリメント
    if selected.service == "a8" and deal.get("ins_id"):
        try:
            from crawlers.crawler_a8 import increment_posted
            increment_posted(deal["ins_id"])
        except Exception:
            pass

    return {
        "service": selected.service,
        "deal":    deal,
        "score":   selected.score,
        "reason":  selected.reason,
    }


# ── CLI テスト ────────────────────────────────────────────────

if __name__ == "__main__":
    result = select_best_deal(verbose=True)
    if result:
        import json
        print("\n--- 選択結果 ---")
        print(f"サービス : {result['service']}")
        print(f"スコア   : {result['score']:.2f}")
        print(f"理由     : {result['reason']}")
        print(f"案件     : {json.dumps(result['deal'], ensure_ascii=False, indent=2)[:300]}")
    else:
        print("案件取得失敗")
