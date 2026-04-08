"""
X（Twitter）自動投稿スクリプト
tweepy（公式API）または twikit（非公式・無料）で投稿
画像カード付き投稿でインプレッション向上
"""
import os
import sys
import json
import time
import tempfile
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


# ─────────────────────────────────────────
# 画像カード生成
# ─────────────────────────────────────────
def _generate_card_file(text: str, post_type: str) -> str:
    """投稿テキストからカード画像を生成してファイルパスを返す。失敗時は空文字列。"""
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from image_card_generator import extract_hook, generate_and_save

        username = os.getenv("X_USERNAME", "")
        hook     = extract_hook(text)
        tmp_path = os.path.join(tempfile.gettempdir(), f"x_card_{int(time.time())}.png")
        return generate_and_save(hook, post_type, username, output_path=tmp_path)
    except Exception as e:
        print(f"⚠️ カード生成スキップ: {e}")
        return ""


# ─────────────────────────────────────────
# tweepy（公式API v2 + v1.1 media upload）
# ─────────────────────────────────────────
def post_with_tweepy(text: str, image_path: str = "") -> bool:
    """tweepy（公式API v2）でXに投稿。画像があればv1.1でアップロードして添付。"""
    try:
        import tweepy

        api_key       = os.getenv("X_API_KEY")
        api_secret    = os.getenv("X_API_SECRET")
        access_token  = os.getenv("X_ACCESS_TOKEN")
        access_secret = os.getenv("X_ACCESS_TOKEN_SECRET")

        if not all([api_key, api_secret, access_token, access_secret]):
            print("⚠️ X APIキーが未設定")
            return False

        media_ids = []

        # 画像アップロード（v1.1 API）
        if image_path and os.path.exists(image_path):
            try:
                auth  = tweepy.OAuth1UserHandler(api_key, api_secret, access_token, access_secret)
                api_v1 = tweepy.API(auth)
                media = api_v1.media_upload(filename=image_path)
                media_ids = [media.media_id]
                print(f"画像アップロード成功: media_id={media.media_id}")
            except Exception as e:
                print(f"⚠️ 画像アップロード失敗（テキストのみで投稿）: {e}")
                media_ids = []

        client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret,
        )

        kwargs = {"text": text}
        if media_ids:
            kwargs["media_ids"] = media_ids

        resp     = client.create_tweet(**kwargs)
        tweet_id = resp.data["id"]
        print(f"投稿成功！ Tweet ID: {tweet_id}")
        return True

    except ImportError:
        print("⚠️ tweepy未インストール")
        return False
    except Exception as e:
        print(f"❌ tweepy投稿エラー: {e}")
        return False


# ─────────────────────────────────────────
# twikit（非公式・無料）
# ─────────────────────────────────────────
def post_with_twikit(text: str, image_path: str = "") -> bool:
    """twikit経由でXに投稿（公式APIキー不要・無料）"""
    try:
        from twikit import Client

        cookies_path = os.path.join(os.path.dirname(__file__), "x_cookies.json")

        env_cookies = os.getenv("X_COOKIES", "")
        if env_cookies and not os.path.exists(cookies_path):
            with open(cookies_path, "w") as f:
                f.write(env_cookies)
            print("X_COOKIES環境変数からCookieを復元")

        if not os.path.exists(cookies_path):
            print("⚠️ x_cookies.json なし")
            return False

        client = Client("ja")
        client.load_cookies(cookies_path)

        media_ids = []
        if image_path and os.path.exists(image_path):
            try:
                with open(image_path, "rb") as f:
                    img_data = f.read()
                media = client.upload_media(img_data, media_type="image/png")
                media_ids = [media.media_id]
                print("twikit 画像アップロード成功")
            except Exception as e:
                print(f"⚠️ twikit 画像アップロード失敗（テキストのみ）: {e}")

        tweet = client.create_tweet(text=text, media_ids=media_ids if media_ids else None)
        print(f"投稿成功！ Tweet ID: {tweet.id}")
        print(f"   URL: https://x.com/{os.getenv('X_USERNAME', 'user')}/status/{tweet.id}")
        return True

    except ImportError:
        print("⚠️ twikit未インストール")
        return False
    except Exception as e:
        print(f"❌ 投稿エラー: {e}")
        return False


# ─────────────────────────────────────────
# ブラウザフォールバック
# ─────────────────────────────────────────
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
# Amazonスレッド投稿（tweet1 → reply tweet2 → reply tweet3）
# ─────────────────────────────────────────
def post_amazon_thread(thread: dict) -> bool:
    """Amazonアフィリエイトスレッドを3ツイートで投稿する（tweepy → twikit フォールバック）"""
    tweet1 = thread.get("tweet1", "")
    tweet2 = thread.get("tweet2", "")
    tweet3 = thread.get("tweet3", "")
    if not tweet1:
        print("❌ スレッドのtweet1が空")
        return False

    # tweepy でスレッド投稿
    try:
        import tweepy

        api_key       = os.getenv("X_API_KEY")
        api_secret    = os.getenv("X_API_SECRET")
        access_token  = os.getenv("X_ACCESS_TOKEN")
        access_secret = os.getenv("X_ACCESS_TOKEN_SECRET")

        if all([api_key, api_secret, access_token, access_secret]):
            client = tweepy.Client(
                consumer_key=api_key,
                consumer_secret=api_secret,
                access_token=access_token,
                access_token_secret=access_secret,
            )
            resp1 = client.create_tweet(text=tweet1)
            id1   = resp1.data["id"]
            print(f"Tweet1投稿成功: {id1}")

            if tweet2:
                resp2 = client.create_tweet(text=tweet2, in_reply_to_tweet_id=id1)
                id2   = resp2.data["id"]
                print(f"Tweet2投稿成功: {id2}")
            else:
                id2 = id1

            if tweet3:
                resp3 = client.create_tweet(text=tweet3, in_reply_to_tweet_id=id2)
                print(f"Tweet3投稿成功（アフィリンク）: {resp3.data['id']}")

            return True
    except Exception as e:
        print(f"⚠️ tweepy スレッド投稿失敗: {e}")

    # twikit でフォールバック
    try:
        import asyncio
        from twikit import Client

        cookies_path = os.path.join(os.path.dirname(__file__), "x_cookies.json")
        env_cookies = os.getenv("X_COOKIES", "")
        if env_cookies and not os.path.exists(cookies_path):
            with open(cookies_path, "w") as f:
                f.write(env_cookies)

        if not os.path.exists(cookies_path):
            print("⚠️ x_cookies.json なし")
            return False

        c = Client("ja")
        c.load_cookies(cookies_path)
        t1 = c.create_tweet(text=tweet1)
        print(f"Tweet1(twikit)成功: {t1.id}")
        reply_id = t1.id
        if tweet2:
            t2 = c.create_tweet(text=tweet2, reply_to=reply_id)
            reply_id = t2.id
            print(f"Tweet2(twikit)成功: {t2.id}")
        if tweet3:
            t3 = c.create_tweet(text=tweet3, reply_to=reply_id)
            print(f"Tweet3(twikit)成功: {t3.id}")
        return True
    except Exception as e:
        print(f"❌ twikit スレッド投稿エラー: {e}")

    # ブラウザフォールバック（tweet1のみ・スレッド不可）
    print("⚠️ ブラウザフォールバック（tweet1のみ投稿）...")
    return post_with_browser(tweet1)


# ─────────────────────────────────────────
# ドライラン
# ─────────────────────────────────────────
def dry_run(text: str, image_path: str = "") -> bool:
    print("\n" + "━" * 50)
    print("[DRY RUN] 以下を投稿予定:")
    print("━" * 50)
    print(text)
    print("━" * 50)
    print(f"文字数: {len(text)}")
    if image_path:
        print(f"添付画像: {image_path}")
    return True


# ─────────────────────────────────────────
# メイン投稿関数
# ─────────────────────────────────────────
def post_now(force_type: str = None, test_mode: bool = False) -> bool:
    """投稿文を生成してXに投稿（画像カード付き）"""
    from x_post_generator import generate_amazon_product_post

    post = generate_post(force_type)

    print(f"\n投稿タイプ: {post['label']} ({post['chars']}文字)")
    print(f"投稿時刻: {datetime.now().strftime('%Y/%m/%d %H:%M')}")

    # Amazon商品タイプはスレッド投稿
    if post["type"] == "product":
        amazon_post = generate_amazon_product_post()
        if amazon_post and amazon_post.get("thread"):
            thread = amazon_post["thread"]
            product_title = amazon_post.get("product", {}).get("title", "")
            print(f"Amazon商品: {product_title}")
            if test_mode:
                print("\n[DRY RUN] Amazonスレッド投稿プレビュー:")
                print("── Tweet1 ──")
                print(thread.get("tweet1", ""))
                print("── Tweet2 ──")
                print(thread.get("tweet2", ""))
                print("── Tweet3 ──")
                print(thread.get("tweet3", ""))
                success = True
            else:
                success = post_amazon_thread(thread)
            save_log({
                "datetime": datetime.now().isoformat(),
                "type":     "amazon_thread",
                "label":    "Amazon商品紹介",
                "chars":    len(thread.get("tweet1", "")),
                "text":     thread.get("tweet1", ""),
                "success":  success,
                "mode":     "dry_run" if test_mode else "live",
                "has_image": False,
            })
            return success
        else:
            print("⚠️ Amazon商品取得失敗、通常投稿にフォールバック")

    text = post["text"]

    # 画像カード生成（テストモードでも生成して確認）
    image_path = _generate_card_file(text, post["type"])

    # 投稿実行（tweepy → twikit → browser の順でフォールバック）
    if test_mode:
        success = dry_run(text, image_path)
    else:
        success = post_with_tweepy(text, image_path)
        if not success:
            print("⚠️ tweepy失敗、twikitで再試行...")
            success = post_with_twikit(text, image_path)
        if not success:
            print("⚠️ twikit失敗、ブラウザで再試行（画像なし）...")
            success = post_with_browser(text)

    # 一時ファイル削除
    if image_path and os.path.exists(image_path):
        try:
            os.remove(image_path)
        except Exception:
            pass

    # ログ保存
    save_log({
        "datetime":   datetime.now().isoformat(),
        "type":       post["type"],
        "label":      post["label"],
        "chars":      post["chars"],
        "text":       text,
        "success":    success,
        "mode":       "dry_run" if test_mode else "live",
        "has_image":  bool(image_path),
    })

    return success


# ─────────────────────────────────────────
# 今日のスケジュール実行
# ─────────────────────────────────────────
def run_today_schedule(test_mode: bool = False):
    """今日の4投稿スケジュールを実行"""
    schedule = get_today_schedule()
    types_cycle = ["useful", "empathy", "useful", "trivia"]

    print("=" * 50)
    print("今日のX投稿スケジュール")
    print("=" * 50)
    for i, t in enumerate(schedule):
        print(f"  {i+1}. {t.strftime('%H:%M')}  [{types_cycle[i]}]")
    print()

    for i, post_time in enumerate(schedule):
        now      = datetime.now()
        wait_sec = (post_time - now).total_seconds()

        if wait_sec > 0:
            print(f"投稿{i+1}: {post_time.strftime('%H:%M')} まで {int(wait_sec//60)}分待機中...")
            time.sleep(wait_sec)

        print(f"\n投稿{i+1}/{len(schedule)} 実行!")
        post_now(force_type=types_cycle[i], test_mode=test_mode)

    print("\n今日の全投稿完了！")


# ─────────────────────────────────────────
# 投稿履歴を表示
# ─────────────────────────────────────────
def show_log(days: int = 7):
    """過去N日分の投稿ログを表示"""
    log = load_log()
    if not log:
        print("ログなし")
        return

    print(f"\n直近{days}日間の投稿ログ ({len(log)}件)")
    print("─" * 50)
    from datetime import timedelta
    cutoff = datetime.now() - timedelta(days=days)

    for entry in reversed(log):
        dt = datetime.fromisoformat(entry["datetime"])
        if dt < cutoff:
            continue
        status = "✅" if entry["success"] else "❌"
        mode   = "🧪" if entry.get("mode") == "dry_run" else "🚀"
        img    = "🖼" if entry.get("has_image") else "  "
        print(f"{status}{mode}{img} {dt.strftime('%m/%d %H:%M')} [{entry['label']}] {entry['chars']}文字")


if __name__ == "__main__":
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
        print("テストモード（各タイプ1件ずつ生成）\n")
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
