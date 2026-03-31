"""
AI雑学ショート フルパイプライン
コンテンツ生成 → 動画生成 → YouTube Shorts自動アップロード

使い方:
  python3 trivia_pipeline.py live        # 本番実行（1本）
  python3 trivia_pipeline.py test        # テスト（YouTube投稿なし）
  python3 trivia_pipeline.py live 3      # 3本連続生成・投稿
  python3 trivia_pipeline.py live 1 危険 # カテゴリ指定
"""
import os
import sys
import json
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


def upload_to_youtube(video_path: str, content: dict) -> str:
    """YouTube Shortsにアップロードして動画URLを返す"""
    try:
        sys.path.insert(0, str(BASE_DIR / "youtube_automation"))
        from youtube_uploader import upload_trivia_video
        video_id = upload_trivia_video(video_path, content)
        if video_id:
            url = f"https://www.youtube.com/shorts/{video_id}"
            print(f"✅ YouTube投稿完了: {url}")
            return url
        return None
    except Exception as e:
        print(f"❌ YouTube投稿エラー: {e}")
        return None


def save_log(entry: dict):
    log = []
    if LOG_FILE.exists():
        with open(LOG_FILE, encoding="utf-8") as f:
            log = json.load(f)
    log.append(entry)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def run_once(test_mode: bool, category: str = None) -> dict:
    from trivia_content_generator import generate_trivia
    from trivia_video_creator import create_trivia_video

    # Step1: 台本生成
    print("\n✍️  台本生成中...")
    content = generate_trivia(category)
    cat = content.get("category", "雑学")
    print(f"   [{cat}] {content.get('hook', '')[:40]}")

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

    # Step3: YouTube Shorts アップロード
    youtube_url = None
    if test_mode:
        print("\n🧪 [テストモード] YouTube投稿スキップ")
    else:
        print("\n📺 YouTube Shortsにアップロード中...")
        youtube_url = upload_to_youtube(video_path, content)

    result = {
        "datetime":    datetime.now().isoformat(),
        "category":    cat,
        "hook":        content.get("hook", ""),
        "video_path":  video_path,
        "youtube_url": youtube_url,
        "test_mode":   test_mode,
    }
    save_log(result)
    return result


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

    print("\n" + "=" * 55)
    print(f"✅ 完了！{len(results)}本の雑学ショートを処理")
    for r in results:
        yt_icon = "✅" if r.get("youtube_url") else "❌"
        print(f"  [{r['category']}] {r['hook'][:30]}")
        print(f"    YouTube:{yt_icon}", end="")
        if r.get("youtube_url"):
            print(f"  → {r['youtube_url']}", end="")
        print()
    print("=" * 55)


if __name__ == "__main__":
    main()
