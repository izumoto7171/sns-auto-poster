"""
YouTube 自動アップロード（tiktok-lifehack用）
生成した縦型ショート動画をYouTube Shortsに自動投稿
"""
import os
import sys
import json
import pickle
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
TOKEN_FILE    = BASE_DIR / "token.pickle"
SECRETS_FILE  = BASE_DIR / "client_secrets.json"
LOG_FILE      = BASE_DIR / "upload_log.json"

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


# ─────────────────────────────────────────
# 認証
# ─────────────────────────────────────────
def authenticate():
    """OAuth2認証 → YouTube APIクライアントを返す"""
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        print("❌ 必要なライブラリをインストールしてください:")
        print("   pip install google-api-python-client google-auth-oauthlib google-auth-httplib2")
        sys.exit(1)

    creds = None

    if TOKEN_FILE.exists():
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            print("✅ トークン更新完了")
        else:
            if not SECRETS_FILE.exists():
                print(f"❌ {SECRETS_FILE} が見つかりません")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(str(SECRETS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
            print("✅ 新規認証完了")

        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)

    return build("youtube", "v3", credentials=creds)


# ─────────────────────────────────────────
# アップロード
# ─────────────────────────────────────────
def upload_video(
    video_path: str,
    title: str,
    description: str = "",
    tags: list = None,
    privacy: str = "public",
    category_id: str = "22",   # 22=People&Blogs, 28=Science&Tech
) -> str:
    """動画をYouTubeにアップロードしてvideo_idを返す"""
    from googleapiclient.http import MediaFileUpload

    if not Path(video_path).exists():
        print(f"❌ 動画ファイルなし: {video_path}")
        return None

    youtube = authenticate()

    print(f"\n📤 アップロード: {Path(video_path).name}")
    print(f"   タイトル: {title[:50]}")

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or [],
            "categoryId": category_id,
            "defaultLanguage": "ja",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=1024 * 1024 * 5  # 5MB
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )

    response = None
    retries = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"   進捗: {int(status.progress() * 100)}%", end="\r")
        except Exception as e:
            retries += 1
            if retries > 5:
                print(f"\n❌ アップロード失敗: {e}")
                return None
            wait = 2 ** retries
            print(f"\n⚠️  リトライ {retries}/5 ({wait}秒後): {e}")
            time.sleep(wait)

    video_id  = response["id"]
    video_url = f"https://www.youtube.com/shorts/{video_id}"
    print(f"\n✅ アップロード完了!")
    print(f"   URL: {video_url}")

    _save_log(video_path, title, video_id, video_url)
    return video_id


# ─────────────────────────────────────────
# ライフハック動画用ラッパー
# ─────────────────────────────────────────
def upload_lifehack_video(video_path: str, content: dict) -> str:
    """
    生成したライフハック動画をYouTube Shortsにアップロード

    Args:
        video_path: 動画ファイルパス
        content: main.pyが生成したコンテンツdict（keyword, hook, tips等）
    Returns:
        video_id or None
    """
    keyword = content.get("keyword", "AIライフハック")
    hook    = content.get("hook", "")
    tips    = content.get("tips", [])

    # タイトル（60文字以内推奨）
    title = f"【{keyword}】{hook[:30]}" if hook else f"【{keyword}】知らないと損するライフハック"
    if "#Shorts" not in title:
        title = title[:50] + " #Shorts"

    # 説明文
    tips_text = "\n".join(f"▶ {t}" for t in tips[:5])
    description = f"""{hook}

{tips_text}

━━━━━━━━━━━━
💡 AIライフハック・副業情報を毎日発信
チャンネル登録でお得な情報をGET！

#ライフハック #AI副業 #時短術 #お金の知識 #Shorts
"""

    tags = [keyword, "ライフハック", "AI副業", "時短術", "お金の知識",
            "Shorts", "shorts", "副業", "節約"]

    return upload_video(
        video_path=video_path,
        title=title,
        description=description,
        tags=tags,
        privacy="public",
        category_id="22",
    )


# ─────────────────────────────────────────
# ログ
# ─────────────────────────────────────────
def _save_log(video_path, title, video_id, url):
    log = []
    if LOG_FILE.exists():
        with open(LOG_FILE) as f:
            log = json.load(f)
    log.append({
        "datetime":   datetime.now().isoformat(),
        "video_path": str(video_path),
        "title":      title,
        "video_id":   video_id,
        "url":        url,
    })
    with open(LOG_FILE, "w") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def show_log(n: int = 10):
    if not LOG_FILE.exists():
        print("ログなし")
        return
    with open(LOG_FILE) as f:
        log = json.load(f)
    print(f"\n📊 YouTubeアップロードログ（直近{n}件）")
    print("─" * 55)
    for entry in reversed(log[-n:]):
        dt = datetime.fromisoformat(entry["datetime"])
        print(f"  {dt.strftime('%m/%d %H:%M')} {entry['title'][:35]}")
        print(f"    → {entry['url']}")


# ─────────────────────────────────────────
# メイン
# ─────────────────────────────────────────
if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "test"

    if cmd == "test":
        # 認証テスト（トークン更新のみ）
        print("🔑 YouTube認証テスト...")
        yt = authenticate()
        print("✅ 認証OK！アップロード準備完了")

    elif cmd == "upload" and len(sys.argv) >= 3:
        video_path = sys.argv[2]
        title = sys.argv[3] if len(sys.argv) >= 4 else "AIライフハック #Shorts"
        upload_video(video_path, title)

    elif cmd == "log":
        show_log()

    else:
        print("使い方:")
        print("  python youtube_uploader.py test              # 認証テスト")
        print("  python youtube_uploader.py upload <path> [title]  # 動画アップロード")
        print("  python youtube_uploader.py log              # ログ表示")
