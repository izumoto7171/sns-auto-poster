"""
キュー・キャッシュの状態確認 + 掃除スクリプト

使い方:
  python3 scripts/check_queue.py                        # 全確認
  python3 scripts/check_queue.py --queue                # pending_tasks のみ
  python3 scripts/check_queue.py --cache                # content_cache のみ
  python3 scripts/check_queue.py --stats                # 集計のみ
  python3 scripts/check_queue.py --clear-low-priority   # 低優先度タスクを削除
  python3 scripts/check_queue.py --clear-low-priority --min-priority 3 --older-than 1
"""
import argparse
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))
from db_client import _get_supabase

# --clear-low-priority のデフォルト値
DEFAULT_MIN_PRIORITY = 2   # これ未満の priority を「低優先度」とみなす
DEFAULT_OLDER_THAN_H = 6   # 作成から N 時間以上経過したものが対象


def check_pending_tasks(limit: int = 10) -> None:
    sb = _get_supabase()

    # 直近N件
    rows = (
        sb.table("pending_tasks")
        .select("id, source, product_key, priority, status, post_type, created_at, raw_data")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
        .data
    ) or []

    print(f"\n{'='*60}")
    print(f"  pending_tasks 直近{limit}件")
    print(f"{'='*60}")

    if not rows:
        print("  （レコードなし）")
        return

    for r in rows:
        note = (r.get("raw_data") or {}).get("context_note", "")
        note_short = (note[:60] + "…") if len(note) > 60 else note
        created = r.get("created_at", "")[:16]
        print(
            f"  [{r['id']:4d}] {r['source']:8s} | "
            f"pri={r['priority']:2d} | {r['status']:10s} | "
            f"{created} | {r['post_type']}"
        )
        print(f"         key : {r['product_key'][:55]}")
        if note_short:
            print(f"         note: {note_short}")
        print()

    # ステータス別集計
    stats_rows = (
        sb.table("pending_tasks")
        .select("status, post_type")
        .execute()
        .data
    ) or []

    from collections import Counter
    counts = Counter((r["status"], r["post_type"]) for r in stats_rows)
    print("  ステータス別集計:")
    for (status, pt), n in sorted(counts.items()):
        print(f"    {status:12s} / {pt}: {n}件")


def check_content_cache(limit: int = 10) -> None:
    sb = _get_supabase()

    rows = (
        sb.table("content_cache")
        .select("id, source, product_key, post_type, use_count, created_at, last_used_at, generated_text")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
        .data
    ) or []

    print(f"\n{'='*60}")
    print(f"  content_cache 直近{limit}件")
    print(f"{'='*60}")

    if not rows:
        print("  （レコードなし）")
        return

    now = datetime.now()
    for r in rows:
        created    = r.get("created_at", "")[:16]
        last_used  = (r.get("last_used_at") or "未使用")[:16]
        text_short = (r.get("generated_text", "")[:55] + "…") if len(r.get("generated_text","")) > 55 else r.get("generated_text","")

        # 鮮度判定
        try:
            age_h = (now - datetime.fromisoformat(r["created_at"].replace("Z",""))).total_seconds() / 3600
            freshness = "新鮮" if age_h < 72 else "古い(>3日)"
        except Exception:
            freshness = "?"

        print(
            f"  [{r['id']:4d}] {r['source']:8s} | "
            f"use={r['use_count']:2d} | {freshness:10s} | {created} | {r['post_type']}"
        )
        print(f"         key : {r['product_key'][:55]}")
        print(f"         text: {text_short}")
        print(f"         last: {last_used}")
        print()


def clear_low_priority(
    min_priority: int = DEFAULT_MIN_PRIORITY,
    older_than_h: float = DEFAULT_OLDER_THAN_H,
    dry_run: bool = False,
) -> None:
    """
    priority が min_priority 未満 かつ older_than_h 時間以上前に作成された
    pending タスクを削除し、トレンド案件（高優先度）をキュー先頭に浮上させる。

    dry_run=True の場合は削除対象の一覧を表示するだけで削除しない。
    """
    sb      = _get_supabase()
    cutoff  = (datetime.utcnow() - timedelta(hours=older_than_h)).isoformat()

    # 削除対象を先に取得して内容を表示する
    targets = (
        sb.table("pending_tasks")
        .select("id, source, product_key, priority, created_at, raw_data")
        .eq("status", "pending")
        .lt("priority", min_priority)
        .lt("created_at", cutoff)
        .order("priority", desc=False)
        .order("created_at", desc=False)
        .execute()
        .data
    ) or []

    print(f"\n{'='*60}")
    print(f"  低優先度クリア  (priority < {min_priority}, 作成 > {older_than_h}h 前)")
    print(f"  {'[DRY-RUN] 削除はしません' if dry_run else '削除実行'}")
    print(f"{'='*60}")

    if not targets:
        print("  対象タスクなし。キューはすでに最適な状態です。")
        return

    print(f"  対象: {len(targets)}件\n")
    for r in targets:
        created = r.get("created_at", "")[:16]
        key     = r["product_key"][:50]
        note    = (r.get("raw_data") or {}).get("context_note", "")[:50]
        print(f"  [{r['id']:4d}] pri={r['priority']:2d} | {r['source']:8s} | {created}")
        print(f"         key : {key}")
        if note:
            print(f"         note: {note}")
        print()

    if dry_run:
        print(f"  → dry-run のため削除をスキップ（実際に削除するには --clear-low-priority を単独で実行）")
        return

    # 削除実行
    ids = [r["id"] for r in targets]
    sb.table("pending_tasks").delete().in_("id", ids).execute()
    print(f"  削除完了: {len(ids)}件")

    # 削除後の残件数を表示
    remaining = (
        sb.table("pending_tasks")
        .select("id", count="exact")
        .eq("status", "pending")
        .execute()
    ).count or 0

    high_pri = (
        sb.table("pending_tasks")
        .select("id", count="exact")
        .eq("status", "pending")
        .gte("priority", min_priority)
        .execute()
    ).count or 0

    print(f"\n  残 pending: {remaining}件（うち高優先度 priority≥{min_priority}: {high_pri}件）")
    if high_pri > 0:
        print(f"  → トレンド案件がキュー先頭に浮上しました")


def check_stats() -> None:
    sb = _get_supabase()

    pending_count = (
        sb.table("pending_tasks")
        .select("id", count="exact")
        .eq("status", "pending")
        .execute()
    ).count or 0

    done_count = (
        sb.table("pending_tasks")
        .select("id", count="exact")
        .eq("status", "done")
        .execute()
    ).count or 0

    failed_count = (
        sb.table("pending_tasks")
        .select("id", count="exact")
        .eq("status", "failed")
        .execute()
    ).count or 0

    cache_count = (
        sb.table("content_cache")
        .select("id", count="exact")
        .execute()
    ).count or 0

    print(f"\n{'='*60}")
    print("  サマリー")
    print(f"{'='*60}")
    print(f"  pending_tasks:")
    print(f"    pending  : {pending_count}件  ← バッチ処理待ち")
    print(f"    done     : {done_count}件")
    print(f"    failed   : {failed_count}件")
    print(f"  content_cache: {cache_count}件")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="キュー・キャッシュ確認 + 掃除")
    parser.add_argument("--queue",              action="store_true", help="pending_tasks のみ表示")
    parser.add_argument("--cache",              action="store_true", help="content_cache のみ表示")
    parser.add_argument("--stats",              action="store_true", help="集計のみ表示")
    parser.add_argument("--limit",              type=int,   default=10,                   help="表示件数 (デフォルト: 10)")
    parser.add_argument("--clear-low-priority", action="store_true",                      help="低優先度の pending タスクを削除してトレンド案件を先頭へ")
    parser.add_argument("--min-priority",       type=int,   default=DEFAULT_MIN_PRIORITY, help=f"この値未満を低優先度とみなす (デフォルト: {DEFAULT_MIN_PRIORITY})")
    parser.add_argument("--older-than",         type=float, default=DEFAULT_OLDER_THAN_H, help=f"作成からN時間以上経過したものを対象 (デフォルト: {DEFAULT_OLDER_THAN_H})")
    parser.add_argument("--dry-run",            action="store_true",                      help="削除対象の確認のみ（実際には削除しない）")
    args = parser.parse_args()

    show_all = not (args.queue or args.cache or args.stats or args.clear_low_priority)

    try:
        if args.clear_low_priority:
            clear_low_priority(
                min_priority = args.min_priority,
                older_than_h = args.older_than,
                dry_run      = args.dry_run,
            )
        else:
            if show_all or args.stats:
                check_stats()
            if show_all or args.queue:
                check_pending_tasks(limit=args.limit)
            if show_all or args.cache:
                check_content_cache(limit=args.limit)
    except RuntimeError as e:
        print(f"\nエラー: {e}")
        print("SUPABASE_URL と SUPABASE_SERVICE_KEY を .env に設定してください")
        sys.exit(1)
