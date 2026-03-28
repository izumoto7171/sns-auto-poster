"""
X（Twitter）自動投稿スクリプト
tweepy（公式API）または twikit（非公式・無料）で投稿
"""
import os
import sys
import json
import time
from datetime import datetime
from x_post_generator import generate_post, get_today_schedule

LOG_FILE = os.path.join(os.path.dirname(__file__), "post_log.json")


# ─────────────────────────────────────────
# ログ管理
# ─────────────────────────────────────────
def load_log() -> list:
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_log(entry: dict):
    log = load_log()
    log.append(entry)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    print(f"📝 ログ保存: {LOG_FILE}")


# ─────────────────────────────────────────
# Playwright ブラウザ自動投稿（Chrome Cookie使用）
# ─────────────────────────────────────────
def post_with_tweepy(text: str) -> bool:
    """tweepy（公式API v2）でXに投稿"""
    try:
        import tweepy

        api_key        = os.getenv("X_API_KEY")
        api_secret     = os.getenv("X_API_SECRET")
        access_token   = os.getenv("X_ACCESS_TOKEN")
        access_secret  = os.getenv("X_ACCESS_TOKEN_SECRET")

        if not all([api_key, api_secret, access_token, access_secret]):
            print("⚠️ X APIキーが未設定（X_API_KEY / X_API_SECRET / X_ACCESS_TOKEN / X_ACCESS_TOKEN_SECRET）")
            return False

        client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret,
        )
        resp = client.create_tweet(text=text)
        tweet_id = resp.data["id"]
        print(f"✅ 投稿成功！ Tweet ID: {tweet_id}")
        return True

    except ImportError:
        print("⚠️ tweepy未インストール: pip install tweepy")
        return False
    except Exception as e:
        print(f"❌ tweepy投稿エラー: {e}")
        return False


def post_with_browser(text: str) -> bool:
    """ChromeのCookieを使いPlaywrightで投稿（API不要・完全無料）"""
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from x_browser_poster import post as browser_post
        return browser_post(text, headless=True)
    except Exception as e:
        print(f"❌ ブラウザ投稿エラー: {e}")
        return False


# ─────────────────────────────────────────
# twikit（非公式・無料）で投稿
# ─────────────────────────────────────────
def post_with_twikit(text: str) -> bool:
    """twikit経由でXに投稿（公式APIキー不要・無料）"""
    try:
        import asyncio
        from twikit import Client

        cookies_path = os.path.join(os.path.dirname(__file__), "x_cookies.json")

        # GitHub Actions: X_COOKIES env var からファイルに復元
        env_cookies = os.getenv("X_COOKIES", "")
        if env_cookies and not os.path.exists(cookies_path):
            with open(cookies_path, "w") as f:
                f.write(env_cookies)
            print(f"✅ X_COOKIES環境変数からCookieを復元")

        if not os.path.exists(cookies_path):
            print("⚠️ x_cookies.json なし。python3.11 x_automation/fetch_x_cookies.py を実行してください")
            return False

        async def _post():
            client = Client("ja")
            client.load_cookies(cookies_path)
            tweet = await client.create_tweet(text=text)
            return tweet.id

        tweet_id = asyncio.run(_post())
        print(f"✅ 投稿成功！ Tweet ID: {tweet_id}")
        print(f"   URL: https://x.com/{os.getenv('X_USERNAME', 'user')}/status/{tweet_id}")
        return True

    except ImportError:
        print("⚠️ twikit未インストール: pip3 install twikit")
        return False
    except Exception as e:
        print(f"❌ 投稿エラー: {e}")
        return False


# ─────────────────────────────────────────
# ドライラン（テスト表示のみ）
# ─────────────────────────────────────────
def dry_run(text: str) -> bool:
    """実際には投稿せず、内容だけ表示"""
    print("\n" + "━" * 50)
    print("📝 [DRY RUN] 以下を投稿予定:")
    print("━" * 50)
    print(text)
    print("━" * 50)
    print(f"📊 文字数: {len(text)}")
    return True


# ─────────────────────────────────────────
# メイン投稿関数
# ─────────────────────────────────────────
def post_now(force_type: str = None, test_mode: bool = False) -> bool:
    """投稿文を生成してXに投稿"""
    post = generate_post(force_type)
    text = post["text"]

    print(f"\n🎯 投稿タイプ: {post['label']} ({post['chars']}文字)")
    print(f"🕐 投稿時刻: {datetime.now().strftime('%Y/%m/%d %H:%M')}")

    # 投稿実行（tweepy → twikit → browser の順でフォールバック）
    if test_mode:
        success = dry_run(text)
    else:
        success = post_with_tweepy(text)
        if not success:
            print("⚠️ tweepy失敗、twikitで再試行...")
            success = post_with_twikit(text)
        if not success:
            print("⚠️ twikit失敗、ブラウザで再試行...")
            success = post_with_browser(text)

    # ログ保存
    save_log({
        "datetime": datetime.now().isoformat(),
        "type":     post["type"],
        "label":    post["label"],
        "chars":    post["chars"],
        "text":     text,
        "success":  success,
        "mode":     "dry_run" if test_mode else "live",
    })

    return success


# ─────────────────────────────────────────
# 今日のスケジュール実行
# ─────────────────────────────────────────
def run_today_schedule(test_mode: bool = False):
    """今日の4投稿スケジュールを実行（時間になったら投稿）"""
    schedule = get_today_schedule()
    types_cycle = ["useful", "empathy", "useful", "trivia"]  # 今日の順番

    print("=" * 50)
    print("📅 今日のX投稿スケジュール")
    print("=" * 50)
    for i, t in enumerate(schedule):
        print(f"  {i+1}. {t.strftime('%H:%M')}  [{types_cycle[i]}]")
    print()

    for i, post_time in enumerate(schedule):
        now = datetime.now()
        wait_sec = (post_time - now).total_seconds()

        if wait_sec > 0:
            print(f"⏳ 投稿{i+1}: {post_time.strftime('%H:%M')} まで {int(wait_sec//60)}分待機中...")
            time.sleep(wait_sec)

        print(f"\n🚀 投稿{i+1}/{len(schedule)} 実行!")
        post_now(force_type=types_cycle[i], test_mode=test_mode)

    print("\n✅ 今日の全投稿完了！")


# ─────────────────────────────────────────
# 投稿履歴を表示
# ─────────────────────────────────────────
def show_log(days: int = 7):
    """過去N日分の投稿ログを表示"""
    log = load_log()
    if not log:
        print("ログなし")
        return

    print(f"\n📊 直近{days}日間の投稿ログ ({len(log)}件)")
    print("─" * 50)
    from datetime import timedelta
    cutoff = datetime.now() - timedelta(days=days)

    for entry in reversed(log):
        dt = datetime.fromisoformat(entry["datetime"])
        if dt < cutoff:
            continue
        status = "✅" if entry["success"] else "❌"
        mode = "🧪" if entry.get("mode") == "dry_run" else "🚀"
        print(f"{status}{mode} {dt.strftime('%m/%d %H:%M')} [{entry['label']}] {entry['chars']}文字")


if __name__ == "__main__":
    import sys

    # .envを読み込む
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

    cmd = sys.argv[1] if len(sys.argv) > 1 else "test"

    if cmd == "test":
        # テスト：全タイプのプレビュー
        print("🧪 テストモード（各タイプ1件ずつ生成）\n")
        for pt in ["useful", "empathy", "trivia", "product"]:
            post = generate_post(force_type=pt)
            print(f"【{post['label']}】{post['chars']}文字")
            print("─" * 45)
            print(post["text"])
            print()

    elif cmd == "post":
        # 今すぐ1件投稿（テスト）
        post_now(test_mode=True)

    elif cmd == "live":
        # 今すぐ1件投稿（本番・GitHub Actions用）
        post_now(test_mode=False)

    elif cmd == "schedule":
        # 今日のスケジュール実行
        run_today_schedule(test_mode=True)

    elif cmd == "log":
        show_log()
