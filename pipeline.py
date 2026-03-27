"""
🚀 フルパイプライン
トレンド取得 → コンテンツ生成 → 動画作成 → YouTube投稿 → X/Bluesky投稿

使い方:
  python pipeline.py            # 通常実行（全工程）
  python pipeline.py --dry-run  # 動画生成まで（SNS投稿なし）
  python pipeline.py --skip-video  # 動画スキップ（SNS投稿のみ）
  python pipeline.py --keyword "節約術"  # キーワード指定
"""
import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent

# .env 読み込み
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

# ─────────────────────────────────────────────────────────────────
# ステップ1: トレンドキーワード取得
# ─────────────────────────────────────────────────────────────────
def step_get_keyword(force_keyword: str = None) -> str:
    if force_keyword:
        print(f"🔑 キーワード（指定）: {force_keyword}")
        return force_keyword

    print("📈 トレンドキーワード取得中...")
    try:
        sys.path.insert(0, str(BASE_DIR))
        from trend_fetcher import get_trending_keywords
        keywords = get_trending_keywords()
        if keywords:
            kw = keywords[0]
            print(f"✅ トレンドキーワード: {kw}")
            return kw
    except Exception as e:
        print(f"⚠️  トレンド取得失敗: {e}")

    # フォールバック：ローテーション
    fallbacks = [
        "AI副業", "節約術", "時短テクニック", "スマホ活用術",
        "副業初心者", "投資入門", "生産性アップ", "ChatGPT活用"
    ]
    import random
    kw = random.choice(fallbacks)
    print(f"✅ フォールバックキーワード: {kw}")
    return kw


# ─────────────────────────────────────────────────────────────────
# ステップ2: コンテンツ生成
# ─────────────────────────────────────────────────────────────────
def step_generate_content(keyword: str) -> dict:
    print(f"\n✍️  コンテンツ生成中（{keyword}）...")
    try:
        from content_generator import generate_content
        content = generate_content(keyword)
        print(f"✅ コンテンツ生成完了: {content.get('hook', '')[:40]}")
        return content
    except Exception as e:
        print(f"⚠️  コンテンツ生成失敗: {e}")
        # フォールバック
        return {
            "keyword": keyword,
            "title":   f"知らないと損する{keyword}",
            "hook":    f"知らないと損する{keyword}の真実",
            "tips": [
                f"{keyword}で月3万円稼ぐ方法",
                "初心者でも今日から始められる",
                "必要なのはスマホだけ",
                "1日15分で副収入",
                "無料ツールで完結する"
            ],
            "cta": "チャンネル登録で毎日お得な情報をGET！"
        }


# ─────────────────────────────────────────────────────────────────
# ステップ3: 動画生成
# ─────────────────────────────────────────────────────────────────
def step_create_video(content: dict) -> str:
    keyword = content.get("keyword", "lifehack")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = BASE_DIR / "output"
    output_dir.mkdir(exist_ok=True)
    output_path = str(output_dir / f"{keyword}_{ts}.mp4")

    print(f"\n🎬 動画生成中...")
    try:
        from video_creator import create_video
        bgm_path = str(BASE_DIR / "bgm_chord.mp3")
        if not Path(bgm_path).exists():
            bgm_path = None
        create_video(content, output_path, duration=15, bgm_path=bgm_path)
        size_mb = Path(output_path).stat().st_size / 1024 / 1024
        print(f"✅ 動画生成完了: {output_path} ({size_mb:.1f}MB)")
        return output_path
    except Exception as e:
        print(f"❌ 動画生成失敗: {e}")
        return None


# ─────────────────────────────────────────────────────────────────
# ステップ4: YouTube投稿
# ─────────────────────────────────────────────────────────────────
def step_upload_youtube(video_path: str, content: dict) -> str:
    print(f"\n📺 YouTube投稿中...")
    try:
        sys.path.insert(0, str(BASE_DIR / "youtube_automation"))
        from youtube_uploader import upload_lifehack_video
        video_id = upload_lifehack_video(video_path, content)
        if video_id:
            url = f"https://www.youtube.com/shorts/{video_id}"
            print(f"✅ YouTube投稿完了: {url}")
            return url
    except Exception as e:
        print(f"❌ YouTube投稿失敗: {e}")
    return None


# ─────────────────────────────────────────────────────────────────
# ステップ5: X投稿
# ─────────────────────────────────────────────────────────────────
def step_post_x(content: dict, youtube_url: str = None) -> bool:
    print(f"\n🐦 X投稿中...")
    try:
        sys.path.insert(0, str(BASE_DIR / "x_automation"))
        from x_post_generator import generate_post
        from x_poster import post_now

        post = generate_post(force_type="useful")
        text = post["text"]

        # YouTube URLがあれば追記
        if youtube_url:
            text = text.rstrip() + f"\n\n▶ {youtube_url}"

        result = post_now(force_type="useful", test_mode=False)
        if result.get("success"):
            print(f"✅ X投稿完了")
            return True
    except Exception as e:
        print(f"❌ X投稿失敗: {e}")
    return False


# ─────────────────────────────────────────────────────────────────
# ステップ6: Bluesky投稿
# ─────────────────────────────────────────────────────────────────
def step_post_bluesky(content: dict, youtube_url: str = None) -> bool:
    print(f"\n🦋 Bluesky投稿中...")
    try:
        sys.path.insert(0, str(BASE_DIR / "bluesky_automation"))
        from bsky_poster import post_now as bsky_post_now

        result = bsky_post_now(force_type="useful", test_mode=False)
        if result.get("success"):
            print(f"✅ Bluesky投稿完了")
            return True
    except Exception as e:
        print(f"❌ Bluesky投稿失敗: {e}")
    return False


# ─────────────────────────────────────────────────────────────────
# ログ保存
# ─────────────────────────────────────────────────────────────────
def save_pipeline_log(data: dict):
    log_path = BASE_DIR / "pipeline_log.json"
    log = []
    if log_path.exists():
        with open(log_path) as f:
            log = json.load(f)
    log.append(data)
    with open(log_path, "w") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────────────────────────
# メイン
# ─────────────────────────────────────────────────────────────────
def run_pipeline(keyword=None, dry_run=False, skip_video=False):
    start = datetime.now()
    print("\n" + "="*55)
    print(f"🚀 パイプライン開始 [{start.strftime('%Y/%m/%d %H:%M')}]")
    print("="*55)

    result = {
        "datetime":    start.isoformat(),
        "keyword":     None,
        "video_path":  None,
        "youtube_url": None,
        "x_posted":    False,
        "bsky_posted": False,
        "dry_run":     dry_run,
    }

    # Step 1: キーワード
    kw = step_get_keyword(force_keyword=keyword)
    result["keyword"] = kw

    # Step 2: コンテンツ生成
    content = step_generate_content(kw)

    # Step 3: 動画生成
    if not skip_video:
        video_path = step_create_video(content)
        result["video_path"] = video_path
    else:
        video_path = None
        print("\n⏭️  動画生成スキップ")

    youtube_url = None

    if not dry_run:
        # Step 4: YouTube投稿
        if video_path:
            youtube_url = step_upload_youtube(video_path, content)
            result["youtube_url"] = youtube_url

        # Step 5: X投稿
        result["x_posted"] = step_post_x(content, youtube_url)

        # Step 6: Bluesky投稿
        result["bsky_posted"] = step_post_bluesky(content, youtube_url)
    else:
        print("\n⏭️  DRY RUN: SNS投稿スキップ")

    # 完了
    elapsed = (datetime.now() - start).seconds
    print("\n" + "="*55)
    print(f"✅ パイプライン完了！（{elapsed}秒）")
    print(f"   キーワード : {kw}")
    if video_path:
        print(f"   動画       : {Path(video_path).name}")
    if youtube_url:
        print(f"   YouTube    : {youtube_url}")
    print(f"   X投稿      : {'✅' if result['x_posted'] else '❌'}")
    print(f"   Bluesky    : {'✅' if result['bsky_posted'] else '❌'}")
    print("="*55)

    save_pipeline_log(result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ライフハック動画 フルパイプライン")
    parser.add_argument("--keyword",    "-k", default=None,      help="キーワード指定")
    parser.add_argument("--dry-run",    "-d", action="store_true", help="SNS投稿しない")
    parser.add_argument("--skip-video", "-s", action="store_true", help="動画生成スキップ")
    args = parser.parse_args()

    run_pipeline(
        keyword=args.keyword,
        dry_run=args.dry_run,
        skip_video=args.skip_video,
    )
