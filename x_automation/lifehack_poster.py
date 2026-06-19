"""
一人暮らしライフハック 自動投稿スクリプト
使い方:
  python lifehack_poster.py                        # テーマ自動選択
  python lifehack_poster.py "tower 収納ラック..."   # テーマ指定
  python lifehack_poster.py --dry-run              # 画像生成のみ（X投稿しない）
"""
import os
import sys
import time
import tempfile
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from lifehack_post_generator import generate_post_data
from lifehack_image_generator import generate_all


def _upload_and_post(images: list, post_text: str, dry_run: bool) -> bool:
    """4枚画像 + 投稿本文をXに投稿する"""
    if dry_run:
        print("[dry-run] X投稿をスキップ")
        return True

    api_key        = os.getenv("X_API_KEY")
    api_secret     = os.getenv("X_API_SECRET")
    access_token   = os.getenv("X_ACCESS_TOKEN")
    access_secret  = os.getenv("X_ACCESS_TOKEN_SECRET")

    if not all([api_key, api_secret, access_token, access_secret]):
        print("⚠️ X API キーが未設定（X_API_KEY / X_API_SECRET / X_ACCESS_TOKEN / X_ACCESS_TOKEN_SECRET）")
        return False

    try:
        import tweepy

        auth = tweepy.OAuth1UserHandler(api_key, api_secret, access_token, access_secret)
        api_v1 = tweepy.API(auth)
        client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret,
        )

        media_ids = []
        tmp_paths = []
        for i, img_bytes in enumerate(images[:4], 1):
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp.write(img_bytes)
            tmp.close()
            tmp_paths.append(tmp.name)
            try:
                media = api_v1.media_upload(filename=tmp.name)
                media_ids.append(media.media_id)
                print(f"  画像{i}アップロード完了: media_id={media.media_id}")
                time.sleep(0.5)
            except Exception as upload_err:
                err_str = str(upload_err)
                if "402" in err_str or "Payment Required" in err_str:
                    print(f"  画像アップロード失敗（APIクレジット不足）: テキストのみで続行")
                    media_ids = []
                    break
                raise

        tweet_kwargs = {"text": post_text}
        if media_ids:
            tweet_kwargs["media_ids"] = media_ids

        resp = client.create_tweet(**tweet_kwargs)
        tweet_id = resp.data["id"]
        username = os.getenv("X_USERNAME", "user")
        print(f"✅ 投稿完了: https://x.com/{username}/status/{tweet_id}")

        for p in tmp_paths:
            try:
                os.unlink(p)
            except Exception:
                pass

        return True

    except ImportError:
        print("⚠️ tweepy 未インストール: pip install tweepy")
        return False
    except Exception as e:
        err_str = str(e)
        if "402" in err_str or "Payment Required" in err_str:
            print(f"⚠️ tweepy APIクレジット不足 → Playwrightブラウザ投稿にフォールバック")
            try:
                from x_browser_poster import post as browser_post
                return browser_post(post_text)
            except Exception as browser_err:
                print(f"❌ ブラウザ投稿も失敗: {browser_err}")
                return False
        print(f"❌ X投稿エラー: {e}")
        import traceback
        traceback.print_exc()
        return False


def _save_images_locally(images: list, data: dict) -> str:
    """デバッグ・確認用にローカル保存"""
    out_dir = Path(__file__).parent.parent / "output" / "lifehack"
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    for i, img_bytes in enumerate(images, 1):
        path = out_dir / f"{ts}_card{i}.png"
        path.write_bytes(img_bytes)
        print(f"  保存: {path}")

    # 投稿テキストも保存
    text_path = out_dir / f"{ts}_post.txt"
    text_path.write_text(data.get("x_post", ""), encoding="utf-8")
    print(f"  保存: {text_path}")

    return str(out_dir)


def run(theme=None, dry_run=False):
    print(f"=== ライフハック投稿 開始 {'[dry-run]' if dry_run else ''} ===")

    # ① テキスト生成
    print("\n[1/3] テキスト生成中（Gemini）...")
    data = generate_post_data(theme)
    if not data:
        print("❌ テキスト生成失敗。終了。")
        return False

    print(f"  タイトル: {data.get('cover', {}).get('title', '')[:40]}")

    # ② 画像生成
    print("\n[2/3] 画像生成中（Pillow）...")
    images = generate_all(data)
    if len(images) < 4:
        print(f"⚠️ 画像生成が不完全（{len(images)}枚）。終了。")
        return False
    print(f"  {len(images)}枚生成完了")

    # ローカル保存（常に実行）
    _save_images_locally(images, data)

    # ③ X投稿
    print("\n[3/3] X投稿中...")
    post_text = data.get("x_post", "")
    print(f"  投稿テキスト（先頭50文字）: {post_text[:50]}...")

    success = _upload_and_post(images, post_text, dry_run)

    print(f"\n=== {'✅ 完了' if success else '❌ 失敗'} ===")
    return success


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    theme = args[0] if args else None
    ok = run(theme=theme, dry_run=dry_run)
    sys.exit(0 if ok else 1)
