"""
ショート動画コンテンツをX・Bluesky・noteに自動投稿
"""
import os
import sys
import json
from datetime import datetime
from pathlib import Path

LOG_FILE = Path(__file__).parent / "post_log.json"


def load_log() -> list:
    if LOG_FILE.exists():
        with open(LOG_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_log(entry: dict):
    log = load_log()
    log.append(entry)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def post_to_bluesky(text: str) -> bool:
    try:
        from atproto import Client
        client = Client()
        client.login(
            os.environ["BLUESKY_USERNAME"],
            os.environ["BLUESKY_PASSWORD"],
        )
        # 300文字制限
        if len(text) > 295:
            text = text[:292] + "..."
        client.send_post(text=text)
        print("✅ Bluesky投稿成功")
        return True
    except Exception as e:
        print(f"❌ Bluesky投稿エラー: {e}")
        return False


def post_to_x(text: str) -> bool:
    try:
        import asyncio
        from twikit import Client

        cookies_path = Path(__file__).parent.parent / "x_automation" / "x_cookies.json"

        # GitHub Actions: X_COOKIES env var から復元
        env_cookies = os.getenv("X_COOKIES", "")
        if env_cookies and not cookies_path.exists():
            with open(cookies_path, "w") as f:
                f.write(env_cookies)
            print("✅ X_COOKIES env から復元")

        if not cookies_path.exists():
            print("⚠️ X Cookieなし、スキップ")
            return False

        # 140文字制限（URL含む）
        if len(text) > 270:
            text = text[:267] + "..."

        async def _post():
            client = Client("ja")
            client.load_cookies(str(cookies_path))
            tweet = await client.create_tweet(text=text)
            return tweet.id

        tweet_id = asyncio.run(_post())
        print(f"✅ X投稿成功 (ID: {tweet_id})")
        return True
    except Exception as e:
        print(f"❌ X投稿エラー: {e}")
        return False


def post_to_note(title: str, body: str) -> bool:
    """note投稿（既存のnote_poster.pyを流用）"""
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent / "note_automation"))
        import asyncio
        from note_poster import post_article
        result = asyncio.run(post_article(title, body))
        return result
    except Exception as e:
        print(f"❌ note投稿エラー: {e}")
        return False


def commit_output_files():
    """生成した動画・画像をGitHubにコミット（Actions上で実行）"""
    try:
        output_dir = Path(__file__).parent / "output"
        # 今日の生成物のみ対象
        today = datetime.now().strftime("%Y%m%d")
        new_files = list(output_dir.glob(f"video_{today}*.mp4")) + \
                    list(output_dir.glob(f"character_{today}*.png"))

        if not new_files:
            print("📁 コミット対象ファイルなし")
            return

        import subprocess as sp
        sp.run(["git", "config", "user.name", "github-actions[bot]"], check=False)
        sp.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=False)
        for f in new_files:
            sp.run(["git", "add", str(f)], check=False)
        result = sp.run(
            ["git", "commit", "-m", f"feat: ショート動画自動生成 {today}"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            sp.run(["git", "push"], check=False)
            print(f"✅ {len(new_files)}件のファイルをGitHubにコミット")
            for f in new_files:
                # GitHub上のダウンロードURLを表示
                print(f"   📥 {f.name}")
        else:
            print("ℹ️ コミット不要（変更なし）")
    except Exception as e:
        print(f"⚠️ コミットスキップ: {e}")


def run(test_mode: bool = False):
    """ショート動画コンテンツ生成→画像・動画生成→SNS投稿"""
    sys.path.insert(0, str(Path(__file__).parent))
    from script_generator import generate, load_env, save_output
    from video_generator import generate_full_video
    load_env()

    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    post = generate()
    short_text = post["short_text"]
    title = f"【ライフハック】{post['theme']['topic']}"

    print(f"\n📱 投稿テキスト（{len(short_text)}文字）:")
    print(short_text[:100] + "..." if len(short_text) > 100 else short_text)

    # 画像生成
    print("\n🖼️  キャラクター画像生成中...")
    save_output(post, generate_image=True)

    # 動画生成（画像 + 音声）
    print("\n🎬 動画生成中...")
    video_path = generate_full_video(post, date_str)
    if video_path:
        post["video_path"] = str(video_path)
        print(f"✅ 動画完成: {video_path.name}")
    else:
        print("⚠️ 動画生成スキップ")

    if test_mode:
        print("\n🧪 [テストモード] 実際には投稿しません")
        success_x = True
        success_bsky = True
    else:
        print("\n🚀 SNS投稿開始...")
        success_x    = post_to_x(short_text)
        success_bsky = post_to_bluesky(short_text)

    # 生成ファイルをGitHubにコミット（iPhoneからダウンロード用）
    if os.getenv("CI"):
        commit_output_files()

    save_log({
        "datetime": datetime.now().isoformat(),
        "theme": post["theme"],
        "hook": post["script"]["hook"],
        "image_prompt": post["image_prompt"],
        "affiliate": post["affiliate"],
        "success_x": success_x,
        "success_bsky": success_bsky,
        "mode": "test" if test_mode else "live",
    })

    # 画像プロンプトは毎回出力（手動でNano Banana 2等に貼る用）
    print("\n" + "=" * 50)
    print("🖼️  画像生成プロンプト（コピーして画像生成ツールへ）:")
    print("=" * 50)
    print(post["image_prompt"])
    print("=" * 50)


if __name__ == "__main__":
    # .env読み込み
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

    cmd = sys.argv[1] if len(sys.argv) > 1 else "test"
    run(test_mode=(cmd == "test"))
