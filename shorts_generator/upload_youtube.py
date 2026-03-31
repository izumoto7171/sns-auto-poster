"""
YouTube Shorts アップロード
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "youtube_automation"))
from youtube_uploader import upload_video


def upload_shorts(video_path: str, script: dict, privacy: str = "public") -> str:
    """
    生成した動画をYouTube Shortsにアップロード

    Args:
        video_path: 動画ファイルパス
        script: generate_script.pyの出力dict
        privacy: "public" / "private" / "unlisted"
    Returns:
        YouTube URL or None
    """
    title = script.get("title", "AI雑学ショート")
    if "#Shorts" not in title:
        title = f"{title[:50]} #Shorts"

    hashtags = " ".join(script.get("hashtags", ["#雑学", "#豆知識", "#Shorts"]))
    hook = script.get("hook", "")
    sections_text = "\n".join(
        f"▶ {s['text']}" for s in script.get("sections", [])
    )

    description = f"""{hook}

{sections_text}

{script.get('cta', '')}

━━━━━━━━━━━━
🧠 毎日「知らなかった！」な雑学を発信中
チャンネル登録して賢くなろう！

{hashtags}
"""

    tags = [t.lstrip("#") for t in script.get("hashtags", [])]
    tags += ["Shorts", "shorts", "雑学", "豆知識"]

    video_id = upload_video(
        video_path=video_path,
        title=title,
        description=description,
        tags=tags,
        privacy=privacy,
        category_id="27",  # Education
    )

    if video_id:
        url = f"https://www.youtube.com/shorts/{video_id}"
        print(f"✅ YouTube投稿完了: {url}")
        return url
    return None
