"""
投稿スキップ分析モジュール

post_skip.log（JSONL）を解析し、重複が多いテンプレートを特定してレポートを出力する。
optimizer.py から呼ばれる他、単独で使用可能。

使い方:
  python3 analyzer.py               # フルレポートを表示
  python3 analyzer.py --json        # JSON形式で出力（パイプ用）
  python3 analyzer.py --top 10      # ワーストを10件表示
"""
import json
import sys
import argparse
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

BASE_DIR      = Path(__file__).parent
SKIP_LOG_FILE = BASE_DIR / "post_skip.log"
POST_LOG_FILE = BASE_DIR / "post_log.json"
POOL_FILE     = BASE_DIR / "content_pool.json"

DEFAULT_TOP_N = 5


# ─────────────────────────────────────────
# データ読み込み
# ─────────────────────────────────────────

def load_skip_log() -> list[dict]:
    """post_skip.log (JSONL) を全件ロードする"""
    if not SKIP_LOG_FILE.exists():
        return []
    entries = []
    with SKIP_LOG_FILE.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"[WARN] post_skip.log:{lineno} パース失敗: {e}", file=sys.stderr)
    return entries


def load_pool_hook_index() -> dict[str, dict]:
    """content_pool.json を hook → item のインデックスで返す"""
    if not POOL_FILE.exists():
        return {}
    try:
        with POOL_FILE.open(encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    return {
        item["hook"]: item
        for item in data.get("items", [])
        if item.get("hook") and not item.get("deprecated")
    }


def load_posted_hook_counts() -> Counter:
    """post_log.json から実際に投稿成功したフックの出現回数を返す"""
    if not POST_LOG_FILE.exists():
        return Counter()
    try:
        with POST_LOG_FILE.open(encoding="utf-8") as f:
            log = json.load(f)
    except Exception:
        return Counter()
    hooks = [
        e.get("text", "").split("\n")[0].strip()
        for e in log
        if e.get("success") and e.get("text")
    ]
    return Counter(hooks)


# ─────────────────────────────────────────
# 診断
# ─────────────────────────────────────────

def _diagnose_hook(hook: str, skip_count: int, pool_item: Optional[dict]) -> str:
    """スキップが多い原因を推定して説明文を返す"""
    reasons = []

    if not pool_item:
        reasons.append("content_pool 未登録（Gemini 生成テキストのパターン重複）")
    if skip_count >= 5:
        reasons.append("同一フックが頻繁に生成されている（テンプレート多様性不足）")
    if hook.startswith("「") or hook.startswith("\u201c"):
        reasons.append("フックが引用符始まりの固定パターン")
    if "副業" in hook and any(x in hook for x in ["月", "万円", "円"]):
        reasons.append("副業＋収益数値パターンが多用されている")
    if "ChatGPT" in hook or "Gemini" in hook or "AI" in hook:
        reasons.append("AI固有名詞を含む定型フック")
    if "3選" in hook or "3つ" in hook or "5選" in hook:
        reasons.append("番号付き列挙フックが飽和している")

    return "、".join(reasons) if reasons else "使用頻度が高くクールダウン中"


# ─────────────────────────────────────────
# 分析メイン
# ─────────────────────────────────────────

def analyze(top_n: int = DEFAULT_TOP_N) -> dict:
    """
    post_skip.log を解析してレポート dict を返す。

    Returns:
        {
          "total_skips"      : int,
          "skip_reason_dist" : {"full_duplicate": n, ...},
          "worst_templates"  : [...],   # スキップ数順 top_n 件
          "never_skipped_pool": [...],  # プールにあるが一度もスキップ記録がないアイテム
          "generated_at"     : str,
        }
    """
    entries = load_skip_log()
    pool_index = load_pool_hook_index()
    posted_counts = load_posted_hook_counts()

    result = {
        "total_skips":       len(entries),
        "skip_reason_dist":  {},
        "worst_templates":   [],
        "never_skipped_pool": [],
        "generated_at":      datetime.now().isoformat(),
    }

    if not entries:
        return result

    # スキップ理由の集計
    result["skip_reason_dist"] = dict(Counter(e.get("skip_reason", "unknown") for e in entries))

    # フック別スキップ集計
    hook_skip: Counter = Counter(e.get("hook", "") for e in entries if e.get("hook"))

    # フック別スキップ理由の内訳
    hook_reasons: dict[str, Counter] = defaultdict(Counter)
    for e in entries:
        h = e.get("hook", "")
        if h:
            hook_reasons[h][e.get("skip_reason", "unknown")] += 1

    # ワーストテンプレート構築
    worst = []
    for hook, skip_count in hook_skip.most_common(top_n):
        pool_item = pool_index.get(hook)
        post_count = posted_counts.get(hook, 0)
        total = skip_count + post_count
        skip_rate = skip_count / total if total > 0 else 1.0

        worst.append({
            "hook":           hook,
            "skip_count":     skip_count,
            "post_count":     post_count,
            "skip_rate":      round(skip_rate, 3),
            "reason_dist":    dict(hook_reasons[hook]),
            "pool_item_id":   pool_item["id"]   if pool_item else None,
            "pool_item_type": pool_item["type"]  if pool_item else None,
            "pool_item_label":pool_item["label"] if pool_item else None,
            "pool_item_text": pool_item["text"]  if pool_item else None,
            "diagnosis":      _diagnose_hook(hook, skip_count, pool_item),
        })

    # スキップ率でソート（同率はスキップ数多い順）
    worst.sort(key=lambda x: (-x["skip_rate"], -x["skip_count"]))
    result["worst_templates"] = worst

    # プールにあるが一度もスキップされていないアイテム（潜在的な優良素材）
    skipped_hooks = set(hook_skip.keys())
    result["never_skipped_pool"] = [
        {"id": item["id"], "type": item["type"], "hook": item["hook"]}
        for item in pool_index.values()
        if item["hook"] not in skipped_hooks
    ]

    return result


# ─────────────────────────────────────────
# 表示
# ─────────────────────────────────────────

def print_report(report: dict, top_n: int = DEFAULT_TOP_N) -> list[dict]:
    """レポートを表示して worst_templates を返す"""
    W = 65
    print("=" * W)
    print(f"投稿スキップ分析レポート（{report['generated_at'][:16]}）")
    print("=" * W)

    total = report["total_skips"]
    if total == 0:
        print("\npost_skip.log にデータがありません。")
        print("human_post_generator.py を実行してスキップログを蓄積してください。")
        return []

    print(f"\n総スキップ数: {total}件")
    print("\n■ スキップ理由の内訳")
    for reason, count in sorted(report["skip_reason_dist"].items(), key=lambda x: -x[1]):
        bar = "█" * min(count, 30)
        print(f"  {reason:22s} {count:4d}件  {bar}")

    worst = report["worst_templates"]
    print(f"\n■ ワーストテンプレート TOP{min(top_n, len(worst))}（スキップ率順）")
    print("─" * W)
    for i, t in enumerate(worst[:top_n], 1):
        pool_id  = t["pool_item_id"] or "pool未登録"
        pct      = f"{t['skip_rate']:.0%}"
        reasons  = "  ".join(f"{k}:{v}" for k, v in t["reason_dist"].items())
        print(f"\n[{i}位] {pool_id:<20s}  スキップ率: {pct}")
        print(f"  フック   : {t['hook']}")
        print(f"  内訳     : {reasons}")
        print(f"  スキップ : {t['skip_count']}回  / 投稿済み: {t['post_count']}回")
        print(f"  診断     : {t['diagnosis']}")

    never = report["never_skipped_pool"]
    print(f"\n■ スキップ実績なし（優良候補） {len(never)}件")
    for item in never[:5]:
        print(f"  {item['id']:<20s}  {item['hook'][:45]}")
    if len(never) > 5:
        print(f"  ...他 {len(never) - 5}件")

    print("\n" + "=" * W)
    return worst


# ─────────────────────────────────────────
# CLI
# ─────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="投稿スキップ分析ツール")
    parser.add_argument("--top",  type=int, default=DEFAULT_TOP_N, help=f"ワースト件数（デフォルト: {DEFAULT_TOP_N}）")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力（パイプ用）")
    args = parser.parse_args()

    report = analyze(top_n=args.top)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_report(report, top_n=args.top)


if __name__ == "__main__":
    main()
