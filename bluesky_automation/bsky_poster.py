"""
Bluesky 自動投稿スクリプト
atproto（公式SDK・完全無料）で投稿
"""
import os
import sys
import json
import time
import random
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from bsky_post_generator import generate_post, get_today_schedule, POST_TYPES

# Supabase クライアント
sys.path.insert(0, str(Path(__file__).parent.parent))
from db_client import db

# ─────────────────────────────────────────
# .env読み込み
# ─────────────────────────────────────────
def load_env():
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


# ─────────────────────────────────────────
# Blueskyに投稿
# ─────────────────────────────────────────
def post_to_bluesky(text: str) -> dict:
    """atproto経由でBlueskyに投稿"""
    try:
        from atproto import Client

        handle   = os.getenv("BSKY_HANDLE")
        password = os.getenv("BSKY_APP_PASSWORD")

        if not handle or not password:
            print("⚠️ BSKY_HANDLE / BSKY_APP_PASSWORD が未設定")
            return {"success": False, "error": "credentials_missing"}

        client = Client()
        client.login(handle, password)
        resp = client.send_post(text=text)

        uri = resp.uri
        post_id = uri.split("/")[-1]
        url = f"https://bsky.app/profile/{handle}/post/{post_id}"

        print(f"✅ Bluesky投稿成功！")
        print(f"   URL: {url}")
        return {"success": True, "uri": uri, "url": url}

    except Exception as e:
        print(f"❌ Bluesky投稿エラー: {e}")
        return {"success": False, "error": str(e)}


def dry_run(text: str) -> dict:
    print("\n" + "━" * 50)
    print("📝 [DRY RUN] Bluesky投稿予定:")
    print("━" * 50)
    print(text)
    print("━" * 50)
    print(f"📊 文字数: {len(text)}")
    return {"success": True, "dry_run": True}


# ─────────────────────────────────────────
# ログ管理（DB版）
# ─────────────────────────────────────────
def save_log(post: dict, result: dict):
    """投稿ログを DB に INSERT する（競合排除）"""
    try:
        db.insert_post(
            platform  = "bluesky",
            post_type = post.get("type", ""),
            label     = post.get("label", ""),
            chars     = post.get("chars", 0),
            text      = post.get("text", ""),
            success   = result.get("success", False),
            url       = result.get("url", ""),
            dry_run   = result.get("dry_run", False),
        )
    except Exception as e:
        print(f"⚠️ DB書き込みエラー（ログ保存失敗）: {e}")


def show_log(days: int = 7):
    from datetime import timedelta
    try:
        log = db.get_posts(platform="bluesky", limit=200)
    except Exception as e:
        print(f"⚠️ DB読み込みエラー: {e}")
        return
    if not log:
        print("ログなし")
        return
    cutoff = datetime.now() - timedelta(days=days)
    print(f"\n📊 Bluesky投稿ログ（直近{days}日）")
    print("─" * 50)
    for entry in log:
        dt_str = entry.get("datetime") or entry.get("created_at", "")
        if not dt_str:
            continue
        try:
            dt = datetime.fromisoformat(dt_str.replace("Z", "").split("+")[0])
        except ValueError:
            continue
        if dt < cutoff:
            continue
        st    = "✅" if entry.get("success") else "❌"
        mode  = "🧪" if entry.get("dry_run") else "🦋"
        label = entry.get("label") or entry.get("post_type") or ""
        chars = entry.get("chars", 0)
        print(f"{st}{mode} {dt.strftime('%m/%d %H:%M')} [{label}] {chars}文字")


# ─────────────────────────────────────────
# 1件投稿
# ─────────────────────────────────────────
def post_now(force_type: str = None, x_text: str = None, test_mode: bool = False):
    post = generate_post(force_type=force_type, x_text=x_text)

    print(f"\n🦋 投稿タイプ: {post['label']} ({post['chars']}文字)")
    print(f"🕐 投稿時刻: {datetime.now().strftime('%Y/%m/%d %H:%M')}")

    has_credentials = bool(os.getenv("BSKY_HANDLE") and os.getenv("BSKY_APP_PASSWORD"))

    if test_mode or not has_credentials:
        result = dry_run(post["text"])
    else:
        result = post_to_bluesky(post["text"])

    save_log(post, result)
    return result


# ─────────────────────────────────────────
# 今日のスケジュール実行
# ─────────────────────────────────────────
def run_today_schedule(posts_per_day: int = 4, test_mode: bool = False):
    schedule = get_today_schedule(posts_per_day)
    random.seed(int(datetime.now().strftime("%Y%m%d")))
    types_cycle = random.choices(
        ["useful", "empathy", "useful", "trivia", "product"],
        weights=[3, 1, 2, 1, 1],
        k=posts_per_day
    )
    random.seed()

    mode = "🧪 DRY RUN" if test_mode else "🦋 LIVE"
    print(f"\n{'='*50}")
    print(f"🦋 Bluesky投稿スケジューラー [{mode}]")
    print(f"{'='*50}")
    for i, (t, pt) in enumerate(zip(schedule, types_cycle)):
        print(f"  {i+1}. {t.strftime('%H:%M')} [{pt}]")
    print()

    for i, (post_time, post_type) in enumerate(zip(schedule, types_cycle)):
        now = datetime.now()
        wait_sec = (post_time - now).total_seconds()
        if wait_sec > 60:
            print(f"⏳ 投稿{i+1}: {post_time.strftime('%H:%M')} まで {int(wait_sec//60)}分 待機...")
            time.sleep(wait_sec)
        elif wait_sec > 0:
            time.sleep(wait_sec)
        else:
            print(f"⏭️  投稿{i+1} ({post_time.strftime('%H:%M')}) は過去 → スキップ")
            continue

        print(f"\n🚀 投稿 {i+1}/{len(schedule)}")
        post_now(force_type=post_type, test_mode=test_mode)

    print(f"\n✅ 今日のBluesky全投稿完了！")


if __name__ == "__main__":
    load_env()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "test"

    if cmd == "test":
        print("🧪 テストモード（DRY RUN）\n")
        for pt in ["useful", "empathy", "trivia", "product"]:
            post = generate_post(force_type=pt)
            print(f"【{post['label']}】{post['chars']}文字")
            print("─" * 45)
            print(post["text"])
            print()

    elif cmd == "post":
        post_now(test_mode=True)

    elif cmd == "live":
        post_now(test_mode=False)

    elif cmd == "schedule":
        run_today_schedule(test_mode=True)

    elif cmd == "log":
        show_log()
