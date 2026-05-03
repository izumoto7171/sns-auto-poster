"""
X投稿 重複回避セレクター

機能:
- post_log.json の過去COOLDOWN_DAYS日分と照合
- 完全一致・フック（1行目）一致は選出対象から除外
- 同一タイプがMAX_RUN回連続にならないよう調整
- 1日4スロットへの割り当て結果を返す
- 外部から check_duplicate() で単体テスト可能

使い方:
  python3 content_selector.py          # 本日の4スロット投稿プランを表示
  python3 content_selector.py --check "投稿テキスト"  # 重複チェック
"""
import json
import random
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


BASE_DIR      = Path(__file__).parent
POST_LOG_FILE = BASE_DIR / "post_log.json"
POOL_FILE     = BASE_DIR / "content_pool.json"

COOLDOWN_DAYS = 14   # 同じ投稿を再掲しない日数
MAX_RUN       = 2    # 同一タイプの連続上限（これを超えると除外候補）

POST_TYPES = [
    {"type": "a8",       "label": "A8アフィリエイト",    "weight": 40},
    {"type": "product",  "label": "Amazon商品紹介",      "weight": 35},
    {"type": "rakuten",  "label": "楽天商品紹介",        "weight": 25},
]

# deal_selector が使えるかチェック（オプション依存）
def _get_deal_boosted_types() -> dict[str, float]:
    """
    deal_selector のスコアに基づいてアフィリエイトタイプの重みを動的に返す。
    失敗時は空 dict（フォールバックで POST_TYPES の固定値を使う）。
    """
    try:
        import sys as _sys
        _sys.path.insert(0, str(BASE_DIR.parent))
        from crawlers.deal_selector import _rakuten_score, _a8_score, _amazon_score
        from crawlers.crawler_a8 import load_programs
        from datetime import date
        today = date.today()
        programs = load_programs()
        scores = {
            "rakuten": _rakuten_score(today).score,
            "a8":      _a8_score(today, programs).score,
            "product": _amazon_score(today).score,
        }
        return scores
    except Exception:
        return {}

TIME_SLOTS = [
    {"label": "朝",   "range": "07:00〜09:00"},
    {"label": "昼",   "range": "11:00〜13:00"},
    {"label": "夕方", "range": "17:00〜19:00"},
    {"label": "夜",   "range": "21:00〜23:00"},
]


# ─────────────────────────────────────────
# ログ読み込み
# ─────────────────────────────────────────

def _parse_dt(entry: dict) -> datetime:
    # post_log.jsonは"timestamp"キー、x_poster.pyは"datetime"キーで記録するため両対応
    dt_str = entry.get("datetime") or entry.get("posted_at") or entry.get("timestamp") or ""
    try:
        return datetime.fromisoformat(dt_str)
    except (ValueError, TypeError):
        return datetime.min


def load_recent_log(days: int = COOLDOWN_DAYS) -> list[dict]:
    """
    過去days日分の投稿ログを返す。
    Supabase が利用可能な場合はDBから、そうでなければローカルJSONにフォールバック。
    x_poster.py はSupabaseに書き込むため、ローカルJSONは古くなる場合がある。
    """
    cutoff = datetime.now() - timedelta(days=days)

    # Supabase から読み込み（x_poster.py の保存先と一致させる）
    try:
        import sys as _sys
        _sys.path.insert(0, str(BASE_DIR.parent))
        from db_client import db
        rows = db.get_posts(platform="x", limit=200)
        if rows:
            return [r for r in rows if r.get("success") and _parse_dt(r) >= cutoff]
    except Exception:
        pass

    # フォールバック: ローカルJSONファイル
    if not POST_LOG_FILE.exists():
        return []
    try:
        with POST_LOG_FILE.open(encoding="utf-8") as f:
            log = json.load(f)
    except Exception:
        return []
    return [e for e in log if e.get("success") and _parse_dt(e) >= cutoff]


# ─────────────────────────────────────────
# 重複判定
# ─────────────────────────────────────────

def _hook_of(text: str) -> str:
    """投稿の1行目（フック）を返す"""
    return text.split("\n")[0].strip()


def build_recent_index(recent_log: list[dict]) -> tuple[set[str], set[str]]:
    """
    (recent_full_texts, recent_hooks) を返す。
    full_texts : 完全一致チェック用
    hooks      : フック（1行目）一致チェック用
    """
    full_texts: set[str] = set()
    hooks: set[str] = set()
    for e in recent_log:
        t = e.get("text", "").strip()
        if t:
            full_texts.add(t)
            hooks.add(_hook_of(t))
    return full_texts, hooks


def is_duplicate(candidate: str, full_texts: set[str], hooks: set[str]) -> bool:
    """完全一致 or フック（1行目）一致なら True"""
    c = candidate.strip()
    return c in full_texts or _hook_of(c) in hooks


def check_duplicate(text: str, days: int = COOLDOWN_DAYS) -> bool:
    """単一テキストが過去days日以内に投稿済みか判定（外部呼び出し用）"""
    recent_log = load_recent_log(days)
    full_texts, hooks = build_recent_index(recent_log)
    return is_duplicate(text, full_texts, hooks)


# ─────────────────────────────────────────
# プール管理
# ─────────────────────────────────────────

def load_pool() -> list[dict]:
    """content_pool.json を読み込む"""
    if not POOL_FILE.exists():
        print(f"[WARN] {POOL_FILE} が見つかりません。build_content_pool.py を実行してください。")
        return []
    try:
        with POOL_FILE.open(encoding="utf-8") as f:
            data = json.load(f)
        return data.get("items", [])
    except Exception as e:
        print(f"[ERROR] content_pool.json の読み込みに失敗: {e}")
        return []


# ─────────────────────────────────────────
# タイプ選択
# ─────────────────────────────────────────

def weighted_type_select(
    exclude_types: Optional[list[str]] = None,
    deal_scores: Optional[dict[str, float]] = None,
) -> dict:
    """
    重み付きランダムで投稿タイプを選択。
    deal_scores が渡された場合、アフィリエイトタイプ（product/a8/rakuten）の
    重みを deal_selector のスコア比で動的に調整する。
    """
    affiliate_types = {"product", "a8", "rakuten"}
    candidates = [pt for pt in POST_TYPES if pt["type"] not in (exclude_types or [])]
    if not candidates:
        candidates = POST_TYPES

    # deal_scores でアフィリエイト重みを上書き
    if deal_scores:
        adjusted = []
        for pt in candidates:
            if pt["type"] in affiliate_types and pt["type"] in deal_scores:
                new_weight = pt["weight"] * deal_scores[pt["type"]]
                adjusted.append({**pt, "weight": new_weight})
            else:
                adjusted.append(pt)
        candidates = adjusted

    total = sum(pt["weight"] for pt in candidates)
    r = random.uniform(0, total)
    cumulative = 0.0
    for pt in candidates:
        cumulative += pt["weight"]
        if r <= cumulative:
            return pt
    return candidates[-1]


# ─────────────────────────────────────────
# スロット選択
# ─────────────────────────────────────────

def select_for_slot(
    pool: list[dict],
    post_type: str,
    full_texts: set[str],
    hooks: set[str],
    used_ids: set[str],
) -> Optional[dict]:
    """
    pool から指定タイプの未重複アイテムを1件ランダム選択。
    見つからなければ None。
    """
    candidates = [
        item for item in pool
        if item.get("type") == post_type
        and item.get("id") not in used_ids
        and not is_duplicate(item.get("text", ""), full_texts, hooks)
    ]
    if not candidates:
        return None
    return random.choice(candidates)


def select_daily_posts(n_slots: int = 4) -> list[dict]:
    """
    1日分の投稿をn_slotsスロット分選出して返す。

    Returns:
        各要素: {slot, range, type, label, item_id, text, deal_reason?}
    """
    recent_log = load_recent_log()
    full_texts, hooks = build_recent_index(recent_log)
    pool = load_pool()

    # deal_selector のスコアを取得（アフィリエイト重みの動的調整に使用）
    deal_scores = _get_deal_boosted_types()
    if deal_scores:
        best_service = max(deal_scores, key=deal_scores.get)
        print(f"[DealSelector] 今日のアフィリエイトブースト: {best_service} (score={deal_scores[best_service]:.2f})")

    results: list[dict] = []
    used_ids: set[str] = set()
    type_run: list[str] = []  # 直近の選択タイプ履歴（連続チェック用）

    for slot_idx in range(n_slots):
        slot = TIME_SLOTS[slot_idx]

        # 同一タイプがMAX_RUN連続なら、そのタイプを除外候補に
        exclude: list[str] = []
        if len(type_run) >= MAX_RUN and len(set(type_run[-MAX_RUN:])) == 1:
            exclude = [type_run[-1]]

        chosen_type: Optional[dict] = None
        chosen_item: Optional[dict] = None

        # タイプを変えながら最大5回試行
        tried_types: set[str] = set()
        for _ in range(5):
            pt = weighted_type_select(
                exclude_types=list(set(exclude) | tried_types),
                deal_scores=deal_scores or None,
            )
            item = select_for_slot(pool, pt["type"], full_texts, hooks, used_ids)
            if item:
                chosen_type = pt
                chosen_item = item
                break
            tried_types.add(pt["type"])

        if chosen_item and chosen_type:
            used_ids.add(chosen_item["id"])
            type_run.append(chosen_type["type"])
            # 同日内でも同じフック/テキストを重複させない
            hooks.add(_hook_of(chosen_item["text"]))
            full_texts.add(chosen_item["text"].strip())
            entry = {
                "slot":    slot["label"],
                "range":   slot["range"],
                "type":    chosen_type["type"],
                "label":   chosen_type["label"],
                "item_id": chosen_item["id"],
                "text":    chosen_item["text"],
            }
            # アフィリエイトタイプの場合、deal_selector の選択理由を付与
            if deal_scores and chosen_type["type"] in {"product", "a8", "rakuten"}:
                entry["deal_boost"] = deal_scores.get(chosen_type["type"], 1.0)
            results.append(entry)
        else:
            results.append({
                "slot":    slot["label"],
                "range":   slot["range"],
                "type":    None,
                "label":   "候補なし",
                "item_id": None,
                "text":    "（このスロットは投稿候補がありません。build_content_pool.py でプールを補充してください）",
            })

    return results


# ─────────────────────────────────────────
# フィルタリング（human_post_generator.py から呼ぶ用）
# ─────────────────────────────────────────

def filter_new_posts(posts: list[dict], days: int = COOLDOWN_DAYS) -> tuple[list[dict], list[dict]]:
    """
    生成済み投稿リストから重複を除外して返す。

    Args:
        posts: [{"text": str, ...}, ...] 形式のリスト
        days:  クールダウン日数

    Returns:
        (new_posts, skipped_posts) のタプル
        skipped_posts の各アイテムには "_skip_reason" と "_hook" キーが追加される。
          skip_reason:
            "full_duplicate"    : テキスト完全一致
            "hook_duplicate"    : フック（1行目）一致
            "session_duplicate" : 同一呼び出し内での重複
    """
    recent_log = load_recent_log(days)
    full_texts, hooks = build_recent_index(recent_log)

    new_posts: list[dict] = []
    skipped: list[dict] = []
    seen_hooks: set[str] = set()

    for post in posts:
        text = post.get("text", "").strip()
        hook = _hook_of(text)

        if text in full_texts:
            reason = "full_duplicate"
        elif hook in hooks:
            reason = "hook_duplicate"
        elif hook in seen_hooks:
            reason = "session_duplicate"
        else:
            reason = None

        if reason:
            skipped.append({**post, "_skip_reason": reason, "_hook": hook})
        else:
            new_posts.append(post)
            seen_hooks.add(hook)
            full_texts.add(text)
            hooks.add(hook)

    return new_posts, skipped


SKIP_LOG_FILE = BASE_DIR / "post_skip.log"


def write_skip_log(skipped: list[dict]) -> int:
    """
    スキップされた投稿を post_skip.log (JSONL) に追記する。

    Args:
        skipped: filter_new_posts() が返す skipped_posts リスト

    Returns:
        書き込んだ件数
    """
    if not skipped:
        return 0

    now = datetime.now().isoformat()
    written = 0
    try:
        with SKIP_LOG_FILE.open("a", encoding="utf-8") as f:
            for post in skipped:
                text = post.get("text", "")
                entry = {
                    "timestamp":     now,
                    "template_id":   post.get("template_id"),
                    "hook":          post.get("_hook") or _hook_of(text),
                    "skip_reason":   post.get("_skip_reason", "unknown"),
                    "original_text": text,
                }
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                written += 1
    except Exception as e:
        print(f"[WARN] skip ログの書き込みに失敗: {e}")

    return written


# ─────────────────────────────────────────
# 表示
# ─────────────────────────────────────────

def print_daily_plan(posts: list[dict]):
    print("=" * 60)
    print(f"本日の投稿プラン（{datetime.now().strftime('%Y-%m-%d')}）")
    print(f"クールダウン: {COOLDOWN_DAYS}日間 / 連続上限: {MAX_RUN}回")
    print("=" * 60)
    for p in posts:
        status = "" if p["type"] else " [候補なし]"
        print(f"\n【{p['slot']} {p['range']}】{p['label']}{status}")
        print("─" * 50)
        print(p["text"])
    print("\n" + "=" * 60)


# ─────────────────────────────────────────
# CLI
# ─────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="X投稿 重複回避セレクター")
    parser.add_argument("--check", metavar="TEXT", help="指定テキストが重複かどうか判定して終了")
    parser.add_argument("--days",  type=int, default=COOLDOWN_DAYS, help=f"クールダウン日数（デフォルト: {COOLDOWN_DAYS}）")
    parser.add_argument("--slots", type=int, default=4, help="1日のスロット数（デフォルト: 4）")
    args = parser.parse_args()

    if args.check:
        result = check_duplicate(args.check, days=args.days)
        status = "重複あり（投稿スキップ推奨）" if result else "重複なし（投稿OK）"
        print(f"{status}")
        print(f"チェック期間: 過去{args.days}日間")
        return

    posts = select_daily_posts(n_slots=args.slots)
    print_daily_plan(posts)


if __name__ == "__main__":
    main()
