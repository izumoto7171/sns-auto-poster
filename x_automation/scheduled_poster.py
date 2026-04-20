"""
予約投稿スクリプト（スパム回避・ランダム間隔）
post_queue.json から未投稿のものを取り出し、ランダムな間隔でX APIに投稿する。

【スパム回避の仕組み】
・投稿間隔: 2〜6時間のランダム間隔（同時刻連投を防ぐ）
・時間帯フィルター: 深夜2〜6時は投稿しない（自然な行動パターンを模倣）
・日次上限: 1日最大6投稿（X無料枠の1500/月に余裕を持たせる）
・テキストの軽微なランダム変化: 記号・改行を微妙に変えて重複検知を回避

使い方:
  python3 scheduled_poster.py preview     # キューと予定時刻を確認（投稿しない）
  python3 scheduled_poster.py run         # 予約投稿を開始（今日分）
  python3 scheduled_poster.py run --all   # キュー全件を今日中に投稿
  python3 scheduled_poster.py status      # 投稿済み・未投稿の件数確認
  python3 scheduled_poster.py clear-done  # 投稿済みエントリをキューから削除
"""
import os
import sys
import json
import time
import random
import argparse
from datetime import datetime, timedelta
from typing import Optional


QUEUE_FILE   = os.path.join(os.path.dirname(__file__), "post_queue.json")
POST_LOG_FILE = os.path.join(os.path.dirname(__file__), "post_log.json")

# ─────────────────────────────────────────
# スパム回避パラメーター
# ─────────────────────────────────────────
MIN_INTERVAL_HOURS = 2      # 投稿間隔の最小（時間）
MAX_INTERVAL_HOURS = 6      # 投稿間隔の最大（時間）
QUIET_HOURS_START  = 2      # 深夜投稿禁止 開始（時）
QUIET_HOURS_END    = 6      # 深夜投稿禁止 終了（時）
DAILY_POST_LIMIT   = 6      # 1日の最大投稿数
FIRST_POST_DELAY_MIN = 5    # 起動後の最初の投稿までの最小待機（分）
FIRST_POST_DELAY_MAX = 30   # 起動後の最初の投稿までの最大待機（分）


# ─────────────────────────────────────────
# キュー管理
# ─────────────────────────────────────────
def load_queue() -> list:
    if not os.path.exists(QUEUE_FILE):
        return []
    with open(QUEUE_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_queue(queue: list):
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)


def get_pending(queue: list) -> list:
    return [p for p in queue if p.get("status") == "pending"]


def mark_posted(queue: list, post_id: str, success: bool):
    for p in queue:
        if p["id"] == post_id:
            p["status"]    = "posted" if success else "failed"
            p["posted_at"] = datetime.now().isoformat()
            break
    save_queue(queue)


# ─────────────────────────────────────────
# 投稿ログ
# ─────────────────────────────────────────
def append_post_log(entry: dict):
    log = []
    if os.path.exists(POST_LOG_FILE):
        with open(POST_LOG_FILE, encoding="utf-8") as f:
            log = json.load(f)
    log.append(entry)
    with open(POST_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def count_today_posts() -> int:
    """今日 scheduled_poster で投稿した件数を返す"""
    if not os.path.exists(POST_LOG_FILE):
        return 0
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        with open(POST_LOG_FILE, encoding="utf-8") as f:
            log = json.load(f)
        return sum(
            1 for e in log
            if e.get("posted_at", "").startswith(today)
            and e.get("source") == "scheduled_poster"
        )
    except Exception:
        return 0


# ─────────────────────────────────────────
# スパム回避ロジック
# ─────────────────────────────────────────
def is_quiet_time(dt: Optional[datetime] = None) -> bool:
    """深夜帯かどうか判定"""
    h = (dt or datetime.now()).hour
    return QUIET_HOURS_START <= h < QUIET_HOURS_END


def next_valid_post_time(after: datetime) -> datetime:
    """
    after の時刻から MIN〜MAX 時間後で、かつ深夜帯でない時刻を返す。
    """
    delta_hours = random.uniform(MIN_INTERVAL_HOURS, MAX_INTERVAL_HOURS)
    candidate   = after + timedelta(hours=delta_hours)

    # 深夜帯に入る場合は翌朝6時以降にスキップ
    if is_quiet_time(candidate):
        next_day_morning = candidate.replace(
            hour=QUIET_HOURS_END, minute=random.randint(5, 45), second=0
        )
        if next_day_morning < candidate:
            next_day_morning += timedelta(days=1)
        candidate = next_day_morning

    return candidate


def add_subtle_variation(text: str) -> str:
    """
    テキストに微妙なバリエーションを加えてスパム検知を回避。
    意味は変えず、句読点・スペース・改行を少し調整する。
    """
    variations = [
        lambda t: t.replace("。\n", "。\n\n") if "。\n" in t and "\n\n" not in t else t,
        lambda t: t.replace("、", "、 ").replace("、  ", "、 "),
        lambda t: t,  # 変化なし（約1/3の確率で元のまま）
        lambda t: t,
    ]
    return random.choice(variations)(text)


# ─────────────────────────────────────────
# 実際の投稿
# ─────────────────────────────────────────
def post_to_x(text: str, test_mode: bool = False) -> bool:
    """tweepy で X に投稿。test_mode=True なら実際には投稿しない。"""
    if test_mode:
        print(f"  [DRY RUN] 投稿テキスト ({len(text)}文字):")
        print(f"  {text[:80]}{'...' if len(text) > 80 else ''}")
        return True

    try:
        import tweepy

        api_key       = os.getenv("X_API_KEY")
        api_secret    = os.getenv("X_API_SECRET")
        access_token  = os.getenv("X_ACCESS_TOKEN")
        access_secret = os.getenv("X_ACCESS_TOKEN_SECRET")

        if not all([api_key, api_secret, access_token, access_secret]):
            print("  ⚠️  X APIキーが未設定のため DRY RUN で実行")
            return True

        client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret,
        )
        resp = client.create_tweet(text=text)
        tweet_id = resp.data["id"] if resp.data else "unknown"
        print(f"  ✅ 投稿完了 (tweet_id: {tweet_id})")
        return True

    except ImportError:
        print("  ❌ tweepy 未インストール: pip install tweepy")
        return False
    except Exception as e:
        print(f"  ❌ 投稿エラー: {e}")
        return False


# ─────────────────────────────────────────
# コマンド: preview
# ─────────────────────────────────────────
def cmd_preview():
    queue   = load_queue()
    pending = get_pending(queue)
    posted  = [p for p in queue if p.get("status") == "posted"]
    failed  = [p for p in queue if p.get("status") == "failed"]

    print("=" * 55)
    print(f"📋 post_queue.json の状態")
    print("=" * 55)
    print(f"  未投稿 (pending) : {len(pending)}件")
    print(f"  投稿済み (posted): {len(posted)}件")
    print(f"  失敗 (failed)    : {len(failed)}件")
    print()

    if not pending:
        print("未投稿のキューはありません。")
        print("human_post_generator.py で投稿を生成してください。")
        return

    # 仮の投稿スケジュールを表示
    now = datetime.now()
    # 最初の投稿は FIRST_POST_DELAY_MIN〜MAX 分後
    first_delay = random.randint(FIRST_POST_DELAY_MIN, FIRST_POST_DELAY_MAX)
    current_time = now + timedelta(minutes=first_delay)

    print(f"📅 予定スケジュール（今から最大 {DAILY_POST_LIMIT} 件）")
    print(f"   投稿間隔: {MIN_INTERVAL_HOURS}〜{MAX_INTERVAL_HOURS}時間のランダム")
    print(f"   深夜帯スキップ: {QUIET_HOURS_START:02d}:00〜{QUIET_HOURS_END:02d}:00")
    print()

    limit  = min(len(pending), DAILY_POST_LIMIT)
    today_posts = count_today_posts()
    remaining   = DAILY_POST_LIMIT - today_posts

    for i, post in enumerate(pending[:limit]):
        if is_quiet_time(current_time):
            current_time = next_valid_post_time(current_time - timedelta(hours=MAX_INTERVAL_HOURS))

        status_note = "" if i < remaining else " ← 今日の上限超過、翌日以降"
        print(f"  [{i+1}] {current_time.strftime('%m/%d %H:%M')}{status_note}")
        print(f"       テンプレート{post.get('template_id', '?')} | {post['text'][:50]}...")
        print()

        current_time = next_valid_post_time(current_time)


# ─────────────────────────────────────────
# コマンド: run
# ─────────────────────────────────────────
def cmd_run(post_all: bool = False, test_mode: bool = False):
    # .env 読み込み
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

    HAS_X_KEYS = all([
        os.getenv("X_API_KEY"), os.getenv("X_API_SECRET"),
        os.getenv("X_ACCESS_TOKEN"), os.getenv("X_ACCESS_TOKEN_SECRET"),
    ])
    if not HAS_X_KEYS:
        print("⚠️  X APIキー未設定 → DRY RUNモードで実行します")
        test_mode = True

    queue   = load_queue()
    pending = get_pending(queue)

    if not pending:
        print("未投稿のキューがありません。")
        return

    today_posted = count_today_posts()
    daily_limit  = len(pending) if post_all else DAILY_POST_LIMIT
    remaining    = daily_limit - today_posted

    if remaining <= 0:
        print(f"今日の投稿上限 ({DAILY_POST_LIMIT}件) に達しています。")
        print("--all オプションで上限を解除できます。")
        return

    targets = pending[:remaining]
    mode_label = "🧪 DRY RUN" if test_mode else "🚀 LIVE"

    print("=" * 55)
    print(f"📤 予約投稿開始 [{mode_label}]")
    print(f"   {len(targets)}件を投稿します（残キュー: {len(pending)}件）")
    print(f"   投稿間隔: {MIN_INTERVAL_HOURS}〜{MAX_INTERVAL_HOURS}時間のランダム")
    print("=" * 55)

    # 最初の投稿は少し待つ（すぐ実行するより自然）
    first_delay_sec = random.randint(FIRST_POST_DELAY_MIN, FIRST_POST_DELAY_MAX) * 60
    first_post_time = datetime.now() + timedelta(seconds=first_delay_sec)
    print(f"\n⏳ 最初の投稿まで {first_delay_sec // 60} 分待機...")
    if not test_mode:
        time.sleep(first_delay_sec)

    current_time = datetime.now()

    for i, post in enumerate(targets):
        print(f"\n📨 投稿 {i+1}/{len(targets)}")
        print(f"   テンプレート{post.get('template_id', '?')}")

        varied_text = add_subtle_variation(post["text"])
        success = post_to_x(varied_text, test_mode=test_mode)

        mark_posted(queue, post["id"], success)

        log_entry = {
            "source":    "scheduled_poster",
            "template_id": post.get("template_id"),
            "text":      varied_text,
            "success":   success,
            "posted_at": datetime.now().isoformat(),
            "test_mode": test_mode,
        }
        append_post_log(log_entry)

        if i < len(targets) - 1:
            # 次の投稿まで待機
            next_time  = next_valid_post_time(datetime.now())
            wait_sec   = max(0, (next_time - datetime.now()).total_seconds())
            wait_min   = int(wait_sec // 60)
            print(f"   次の投稿: {next_time.strftime('%H:%M')} ({wait_min}分後)")

            if not test_mode and wait_sec > 0:
                print(f"   ⏳ {wait_min}分待機中...")
                time.sleep(wait_sec)

    print("\n" + "=" * 55)
    print(f"✅ 完了！ {len(targets)}件を処理しました")
    remaining_count = len([p for p in load_queue() if p.get("status") == "pending"])
    print(f"   残キュー: {remaining_count}件")
    print("=" * 55)


# ─────────────────────────────────────────
# コマンド: status
# ─────────────────────────────────────────
def cmd_status():
    queue  = load_queue()
    today  = datetime.now().strftime("%Y-%m-%d")

    pending  = [p for p in queue if p.get("status") == "pending"]
    posted   = [p for p in queue if p.get("status") == "posted"]
    failed   = [p for p in queue if p.get("status") == "failed"]
    today_ct = count_today_posts()

    print("=" * 55)
    print("📊 投稿キュー ステータス")
    print("=" * 55)
    print(f"  未投稿 (pending) : {len(pending):3d} 件")
    print(f"  投稿済み (posted): {len(posted):3d} 件")
    print(f"  失敗 (failed)    : {len(failed):3d} 件")
    print(f"  本日の投稿数     : {today_ct:3d} 件 / 上限 {DAILY_POST_LIMIT} 件")
    print()

    if failed:
        print("⚠️  失敗した投稿:")
        for p in failed[-5:]:
            print(f"  - [{p.get('posted_at', '')[:16]}] {p['text'][:50]}...")


# ─────────────────────────────────────────
# コマンド: clear-done
# ─────────────────────────────────────────
def cmd_clear_done():
    queue   = load_queue()
    before  = len(queue)
    queue   = [p for p in queue if p.get("status") == "pending"]
    after   = len(queue)
    save_queue(queue)
    print(f"✅ {before - after}件の投稿済みエントリを削除しました（残: {after}件）")


# ─────────────────────────────────────────
# エントリーポイント
# ─────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="X予約投稿ツール（スパム回避付き）")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("preview",    help="スケジュールをプレビュー（投稿しない）")
    subparsers.add_parser("status",     help="キューの状態を確認")
    subparsers.add_parser("clear-done", help="投稿済みエントリを削除")

    run_parser = subparsers.add_parser("run", help="予約投稿を開始")
    run_parser.add_argument("--all",      action="store_true", help="日次上限を無視して全件投稿")
    run_parser.add_argument("--dry-run",  action="store_true", help="実際には投稿しない")

    args = parser.parse_args()

    if args.command == "preview":
        cmd_preview()
    elif args.command == "run":
        cmd_run(post_all=args.all, test_mode=args.dry_run)
    elif args.command == "status":
        cmd_status()
    elif args.command == "clear-done":
        cmd_clear_done()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
