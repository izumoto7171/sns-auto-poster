"""
AI雑学ショート フルパイプライン
コンテンツ生成 → 動画生成 → X/Bluesky投稿 → GitHubにコミット（ダウンロード用）

使い方:
  python3 trivia_pipeline.py live        # 本番実行（1本）
  python3 trivia_pipeline.py test        # テスト（SNS投稿なし）
  python3 trivia_pipeline.py live 3      # 3本連続生成・投稿
  python3 trivia_pipeline.py live 1 危険 # カテゴリ指定
"""
import os
import sys
import json
import asyncio
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
LOG_FILE = BASE_DIR / "trivia_pipeline_log.json"


def load_env():
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


load_env()


# ─────────────────────────────────────────
# SNS投稿ヘルパー
# ─────────────────────────────────────────
def post_to_x(text: str) -> bool:
    try:
        import asyncio
        from twikit import Client

        cookies_path = BASE_DIR / "x_automation" / "x_cookies.json"
        env_cookies = os.getenv("X_COOKIES", "")
        if env_cookies and not cookies_path.exists():
            with open(cookies_path, "w") as f:
                f.write(env_cookies)

        if not cookies_path.exists():
            print("⚠️  X Cookieなし、スキップ")
            return False

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


def post_to_bluesky(text: str) -> bool:
    try:
        from atproto import Client
        client = Client()
        client.login(
            os.environ["BSKY_HANDLE"],
            os.environ["BSKY_APP_PASSWORD"],
        )
        if len(text) > 295:
            text = text[:292] + "..."
        client.send_post(text=text)
        print("✅ Bluesky投稿成功")
        return True
    except Exception as e:
        print(f"❌ Bluesky投稿エラー: {e}")
        return False


def build_sns_text(content: dict) -> str:
    """X/Bluesky用テキストを組み立てる"""
    hook = content.get("hook_display", content.get("hook", ""))
    explanation = content.get("explanation", "")
    punchline = content.get("punchline", "")
    category = content.get("category", "雑学")

    # 短く切る
    exp_short = explanation[:60] + "..." if len(explanation) > 60 else explanation

    text = f"""❗{hook}

{exp_short}

💡 {punchline}

#{category} #雑学 #知識 #Shorts"""
    return text


def commit_video(video_path: str):
    """生成した動画をGitHubにコミット（CI上でiPhoneからダウンロード用）"""
    if not os.getenv("CI"):
        return
    try:
        import subprocess as sp
        sp.run(["git", "config", "user.name", "github-actions[bot]"], check=False)
        sp.run(["git", "config", "user.email",
                "github-actions[bot]@users.noreply.github.com"], check=False)
        sp.run(["git", "add", video_path], check=False)
        result = sp.run(
            ["git", "commit", "-m",
             f"feat: 雑学ショート自動生成 {datetime.now().strftime('%Y-%m-%d %H:%M')}"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            sp.run(["git", "push"], check=False)
            print(f"✅ 動画をGitHubにコミット: {Path(video_path).name}")
        else:
            print("ℹ️  コミット不要（変更なし）")
    except Exception as e:
        print(f"⚠️  コミットスキップ: {e}")


def save_log(entry: dict):
    log = []
    if LOG_FILE.exists():
        with open(LOG_FILE, encoding="utf-8") as f:
            log = json.load(f)
    log.append(entry)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────
# メインパイプライン（1本分）
# ─────────────────────────────────────────
def run_once(test_mode: bool, category: str = None) -> dict:
    from trivia_content_generator import generate_trivia
    from trivia_video_creator import create_trivia_video

    # Step1: コンテンツ生成
    print("\n✍️  台本生成中...")
    content = generate_trivia(category)
    hook_short = content.get("hook", "")[:40]
    cat = content.get("category", "雑学")
    print(f"   [{cat}] {hook_short}")

    # Step2: 動画生成
    print("🎬 動画生成中...")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    cat_slug = cat.replace(" ", "_").replace("の", "")
    output_dir = BASE_DIR / "output" / "trivia"
    output_dir.mkdir(parents=True, exist_ok=True)
    video_path = str(output_dir / f"{cat_slug}_{ts}.mp4")

    bgm_path = str(BASE_DIR / "bgm_chord.mp3")
    if not Path(bgm_path).exists():
        bgm_path = None

    create_trivia_video(content, video_path, duration=15, bgm_path=bgm_path)

    # Step3: SNS投稿
    sns_text = build_sns_text(content)
    print(f"\n📱 投稿テキスト:\n{sns_text[:120]}...")

    x_ok = False
    bsky_ok = False

    if test_mode:
        print("\n🧪 [テストモード] SNS投稿スキップ")
        x_ok = True
        bsky_ok = True
    else:
        print("\n🚀 SNS投稿...")
        x_ok    = post_to_x(sns_text)
        bsky_ok = post_to_bluesky(sns_text)

    # Step4: 動画をGitHubにコミット（CI上）
    commit_video(video_path)

    result = {
        "datetime":   datetime.now().isoformat(),
        "category":   cat,
        "hook":       content.get("hook", ""),
        "video_path": video_path,
        "x_posted":   x_ok,
        "bsky_posted": bsky_ok,
        "test_mode":  test_mode,
    }
    save_log(result)
    return result


# ─────────────────────────────────────────
# エントリーポイント
# ─────────────────────────────────────────
def main():
    cmd      = sys.argv[1] if len(sys.argv) > 1 else "test"
    count    = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    category = sys.argv[3] if len(sys.argv) > 3 else None

    test_mode = (cmd != "live")

    print("=" * 55)
    print(f"🧠 AI雑学ショート パイプライン")
    print(f"   モード: {'テスト' if test_mode else '本番'} | "
          f"本数: {count} | カテゴリ: {category or 'ランダム'}")
    print("=" * 55)

    results = []
    for i in range(count):
        print(f"\n━━━ {i+1}/{count} ━━━")
        result = run_once(test_mode=test_mode, category=category)
        results.append(result)

    # サマリー
    print("\n" + "=" * 55)
    print(f"✅ 完了！{len(results)}本の雑学ショートを処理")
    for r in results:
        x_icon    = "✅" if r["x_posted"]    else "❌"
        bsky_icon = "✅" if r["bsky_posted"] else "❌"
        print(f"  [{r['category']}] {r['hook'][:30]}")
        print(f"    X:{x_icon}  Bluesky:{bsky_icon}  → {Path(r['video_path']).name}")
    print("=" * 55)


if __name__ == "__main__":
    main()
