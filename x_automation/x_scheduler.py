"""
X投稿スケジューラー
cron から毎日1回呼ぶだけで、4投稿を時間通りに自動実行
"""
import os
import sys
import time
import json
from datetime import datetime

# パスを通す
sys.path.insert(0, os.path.dirname(__file__))

from x_post_generator import generate_post, get_today_schedule
from x_poster import post_now, show_log

# ─────────────────────────────────────────
# .envを読み込む
# ─────────────────────────────────────────
env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

# X APIキーが揃っているかチェック
HAS_X_KEYS = all([
    os.getenv("X_API_KEY"),
    os.getenv("X_API_SECRET"),
    os.getenv("X_ACCESS_TOKEN"),
    os.getenv("X_ACCESS_TOKEN_SECRET"),
])

# アフィリエイト専用パターン（a8 / product=Amazon / rakuten）
import random
DAILY_PATTERNS = [
    ["a8",      "product", "a8",      "rakuten"],
    ["product", "a8",      "rakuten", "a8"],
    ["a8",      "rakuten", "a8",      "product"],
    ["rakuten", "a8",      "product", "a8"],
    ["a8",      "product", "a8",      "rakuten"],
]


def run():
    today_str = datetime.now().strftime("%Y/%m/%d")
    mode = "🚀 LIVE" if HAS_X_KEYS else "🧪 DRY RUN"

    print("=" * 55)
    print(f"📅 X自動投稿スケジューラー起動 [{mode}]")
    print(f"   {today_str}")
    print("=" * 55)

    if not HAS_X_KEYS:
        print("\n⚠️  X APIキー未設定のため、DRY RUNモードで実行します")
        print("   .envに以下を追加してください:")
        print("   X_API_KEY=xxx")
        print("   X_API_SECRET=xxx")
        print("   X_ACCESS_TOKEN=xxx")
        print("   X_ACCESS_TOKEN_SECRET=xxx\n")

    # 今日のパターンと時間割を決定（日付でシードを固定→毎日同じパターンにならない）
    random.seed(int(datetime.now().strftime("%Y%m%d")))
    pattern = random.choice(DAILY_PATTERNS)
    schedule = get_today_schedule()
    random.seed()  # シードリセット

    print(f"📋 今日のスケジュール:")
    for i, (t, pt) in enumerate(zip(schedule, pattern)):
        print(f"   {i+1}. {t.strftime('%H:%M')}  [{pt}]")
    print()

    # 各投稿を時間通りに実行
    for i, (post_time, post_type) in enumerate(zip(schedule, pattern)):
        now = datetime.now()
        wait_sec = (post_time - now).total_seconds()

        if wait_sec > 60:
            print(f"⏳ 投稿{i+1}: {post_time.strftime('%H:%M')} まで"
                  f" {int(wait_sec//60)}分 待機...")
            time.sleep(wait_sec)
        elif wait_sec > 0:
            time.sleep(wait_sec)
        else:
            # 既に過ぎた時間はスキップ
            print(f"⏭️  投稿{i+1} ({post_time.strftime('%H:%M')}) は既に過去 → スキップ")
            continue

        print(f"\n🚀 投稿 {i+1}/{len(schedule)} 実行!")
        post_now(
            force_type=post_type,
            test_mode=not HAS_X_KEYS,
        )
        print()

    print("=" * 55)
    print(f"✅ 今日の全投稿完了！ ({today_str})")
    print("=" * 55)

    # 直近ログを表示
    print()
    show_log(days=3)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"

    if cmd == "run":
        run()
    elif cmd == "preview":
        # 時間を待たずに今すぐ全投稿プレビュー
        print("📋 今日の投稿プレビュー（時間待ちなし）\n")
        random.seed(int(datetime.now().strftime("%Y%m%d")))
        pattern = random.choice(DAILY_PATTERNS)
        schedule = get_today_schedule()
        random.seed()
        for i, (t, pt) in enumerate(zip(schedule, pattern)):
            post = generate_post(force_type=pt)
            print(f"【{t.strftime('%H:%M')}】{post['label']} ({post['chars']}文字)")
            print("─" * 45)
            print(post["text"])
            print()
    elif cmd == "log":
        show_log(days=7)
