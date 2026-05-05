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
from x_post_generator import generate_post, get_today_schedule, generate_value_thread

# Supabase クライアント・リトライユーティリティ（プロジェクトルートから import）
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from db_client import db
from retry_utils import with_retry


# ─────────────────────────────────────────
# ログ管理（DB版）
# ─────────────────────────────────────────
def load_log() -> list:
    """過去ログを取得する（show_log 用）"""
    try:
        return db.get_posts(platform="x", limit=200)
    except Exception as e:
        print(f"⚠️ DB読み込みエラー: {e}")
        return []


_LOCAL_LOG_FILE = os.path.join(os.path.dirname(__file__), "post_log.json")
_LOCAL_LOG_MAX  = 200  # ローカルログの最大保持件数


def _save_log_local(entry: dict):
    """ローカルJSONにもログを書く（Supabase不要・dedup用）"""
    now = datetime.now().isoformat()
    record = {
        "datetime":  now,
        "type":      entry.get("type", ""),
        "label":     entry.get("label", ""),
        "chars":     entry.get("chars", 0),
        "text":      entry.get("text", ""),
        "success":   entry.get("success", False),
        "mode":      entry.get("mode", "live"),
    }
    try:
        if os.path.exists(_LOCAL_LOG_FILE):
            with open(_LOCAL_LOG_FILE, encoding="utf-8") as f:
                log = json.load(f)
        else:
            log = []
        log.append(record)
        # 上限超えたら古いものから削除
        if len(log) > _LOCAL_LOG_MAX:
            log = log[-_LOCAL_LOG_MAX:]
        with open(_LOCAL_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ ローカルログ書き込みエラー: {e}")


def save_log(entry: dict):
    """投稿ログを DB に INSERT する。DB未設定時はローカルJSONにフォールバック。"""
    db_ok = False
    try:
        db.insert_post(
            platform  = "x",
            post_type = entry.get("type", ""),
            label     = entry.get("label", ""),
            chars     = entry.get("chars", 0),
            text      = entry.get("text", ""),
            success   = entry.get("success", False),
            mode      = entry.get("mode", "live"),
            has_image = entry.get("has_image", False),
        )
        db_ok = True
    except Exception as e:
        print(f"⚠️ DB書き込みエラー（ログ保存失敗）: {e}")
    # Supabase成否にかかわらずローカルにも書く（dedup用）
    _save_log_local(entry)


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
            # tweet1: 重複投稿防止のためリトライなし（1回のみ）
            resp1 = client.create_tweet(text=tweet1)
            id1   = resp1.data["id"]
            print(f"Tweet1投稿成功: {id1}")

            if tweet2:
                @with_retry(api="x", context="tweet2", log_on_giveup=True)
                def _post_tweet2():
                    return client.create_tweet(text=tweet2, in_reply_to_tweet_id=id1)
                resp2 = _post_tweet2()
                id2   = resp2.data["id"] if resp2 else id1
                if resp2:
                    print(f"Tweet2投稿成功: {id2}")
            else:
                id2 = id1

            if tweet3:
                @with_retry(api="x", context="tweet3", log_on_giveup=True)
                def _post_tweet3():
                    return client.create_tweet(text=tweet3, in_reply_to_tweet_id=id2)
                resp3 = _post_tweet3()
                if resp3:
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
        # tweet1 成功後は例外が出ても再投稿しない
        reply_id = str(t1.id)
        try:
            if tweet2:
                t2 = c.create_tweet(text=tweet2, reply_to=reply_id)
                reply_id = str(t2.id)
                print(f"Tweet2(twikit)成功: {t2.id}")
            if tweet3:
                t3 = c.create_tweet(text=tweet3, reply_to=reply_id)
                print(f"Tweet3(twikit)成功: {t3.id}")
        except Exception as e2:
            print(f"⚠️ twikit tweet2/3エラー（tweet1は投稿済み）: {e2}")
        return True  # tweet1 が投稿できていれば成功とみなす

    except Exception as e:
        print(f"❌ twikit スレッド投稿エラー（tweet1未投稿）: {e}")

    # ブラウザフォールバック（Playwright・3ツイートスレッド対応）
    print("⚠️ ブラウザフォールバック（Playwright スレッド投稿）...")
    try:
        from x_browser_poster import post_thread_sync
        tweets = [t for t in [tweet1, tweet2, tweet3] if t]
        return post_thread_sync(tweets)
    except Exception as e:
        print(f"⚠️ スレッド投稿失敗 → tweet1のみフォールバック: {e}")
        return post_with_browser(tweet1)


# ─────────────────────────────────────────
# 価値スレッド投稿（脱ボット化）
# tweet1: 価値コンテンツ（リンクなし）→ アルゴリズムリーチ最大化
# tweet2: リプライでプロフィールリンク案内
# ─────────────────────────────────────────
def post_value_thread(post_type: str = "useful") -> bool:
    """
    スレッド形式で投稿（リンクは2ツイート目のリプライに分離）。
    Xのアルゴリズムはリンク付き投稿のリーチを下げるため、
    1ツイート目はリンクなしにしてインプレッションを最大化する。
    """
    thread = generate_value_thread(post_type)
    tweet1 = thread.get("tweet1", "")
    tweet2 = thread.get("tweet2", "")

    if not tweet1:
        print("⚠️ スレッドのtweet1が空")
        return False

    # tweet1を通常投稿（tweepy → twikit → browser）
    image_path = _generate_card_file(tweet1, post_type)
    success1 = post_with_tweepy(tweet1, image_path)
    if not success1:
        success1 = post_with_twikit(tweet1, image_path)
    if not success1:
        success1 = post_with_browser(tweet1)

    if image_path and os.path.exists(image_path):
        try:
            os.remove(image_path)
        except Exception:
            pass

    if not success1 or not tweet2:
        return success1

    # tweet2をリプライとして投稿（twikit 経由）
    # tweepyはリプライIDが必要なため twikit を優先
    try:
        from twikit import Client
        cookies_path = os.path.join(os.path.dirname(__file__), "x_cookies.json")
        env_cookies = os.getenv("X_COOKIES", "")
        if env_cookies and not os.path.exists(cookies_path):
            with open(cookies_path, "w") as f:
                f.write(env_cookies)

        if os.path.exists(cookies_path):
            # tweet1のIDを取得するため、post_log から最新エントリを参照
            # twikit は create_tweet の戻り値から ID を取得できないため
            # tweet2はベストエフォートで投稿（失敗してもtweet1は残る）
            c = Client("ja")
            c.load_cookies(cookies_path)
            c.create_tweet(text=tweet2)
            print("✅ スレッドtweet2投稿成功（リプライ）")
    except Exception as e:
        print(f"⚠️ tweet2リプライ失敗（tweet1は投稿済み）: {e}")

    return True


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
            # 静的データで再試行（Gemini/PA-APIが使えない場合）
            print("⚠️ Amazon商品取得失敗、静的データで再試行")
            amazon_post = generate_amazon_product_post(force_refresh=True)
            if amazon_post and amazon_post.get("thread"):
                thread = amazon_post["thread"]
                product_title = amazon_post.get("product", {}).get("title", "")
                print(f"Amazon商品（静的）: {product_title}")
                if test_mode:
                    print("\n[DRY RUN] Amazonスレッド投稿プレビュー（静的）:")
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
                    "label":    "Amazon商品紹介（静的）",
                    "chars":    len(thread.get("tweet1", "")),
                    "text":     thread.get("tweet1", ""),
                    "success":  success,
                    "mode":     "dry_run" if test_mode else "live",
                    "has_image": False,
                })
                return success
            print("❌ Amazon商品取得完全失敗、投稿スキップ")
            return False

    # A8タイプはスレッド投稿（tweet1=本文リンクなし、tweet2=短縮URL）
    if post["type"] == "a8" and post.get("thread", {}).get("tweet2"):
        thread = post["thread"]
        print(f"A8スレッド投稿: {thread.get('tweet1', '')[:40]}...")
        if test_mode:
            print("\n[DRY RUN] A8スレッド投稿プレビュー:")
            print("── Tweet1（リンクなし）──")
            print(thread.get("tweet1", ""))
            print("── Tweet2（リプライ・リンク）──")
            print(thread.get("tweet2", ""))
            success = True
        else:
            success = post_amazon_thread(thread)
        save_log({
            "datetime": datetime.now().isoformat(),
            "type":     "a8",
            "label":    "A8アフィリエイト",
            "chars":    len(thread.get("tweet1", "")),
            "text":     thread.get("tweet1", ""),
            "success":  success,
            "mode":     "dry_run" if test_mode else "live",
            "has_image": False,
        })
        return success

    # 楽天タイプはスレッド投稿（tweet1=本文、tweet2=URL）
    if post["type"] == "rakuten" and post.get("thread", {}).get("tweet2"):
        thread = post["thread"]
        print(f"楽天商品スレッド投稿: {thread.get('tweet1', '')[:40]}...")
        if test_mode:
            print("\n[DRY RUN] 楽天スレッド投稿プレビュー:")
            print("── Tweet1 ──")
            print(thread.get("tweet1", ""))
            print("── Tweet2 ──")
            print(thread.get("tweet2", ""))
            success = True
        else:
            success = post_amazon_thread(thread)  # 同じスレッド投稿ロジックを流用
        save_log({
            "datetime": datetime.now().isoformat(),
            "type":     "rakuten_thread",
            "label":    "楽天商品紹介",
            "chars":    len(thread.get("tweet1", "")),
            "text":     thread.get("tweet1", ""),
            "success":  success,
            "mode":     "dry_run" if test_mode else "live",
            "has_image": False,
        })
        return success

    text = post["text"]

    # useful / empathy タイプはスレッド形式（脱ボット化）
    # リンクなし tweet1 → リプライで詳細案内 の2ツイート構成
    if not test_mode and post["type"] in ("useful", "empathy"):
        print("📌 スレッド形式で投稿（リンク分離でリーチ最大化）")
        success = post_value_thread(post["type"])
        save_log({
            "datetime":  datetime.now().isoformat(),
            "type":      post["type"],
            "label":     post["label"],
            "chars":     post["chars"],
            "text":      text,
            "success":   success,
            "mode":      "live_thread",
            "has_image": True,
        })
        return success

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
    types_cycle = ["product", "product", "product", "product"]

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

    for entry in log:  # get_posts は降順なのでそのまま
        dt_str = entry.get("datetime") or entry.get("created_at", "")
        if not dt_str:
            continue
        try:
            dt = datetime.fromisoformat(dt_str.replace("Z", "").split("+")[0])
        except ValueError:
            continue
        if dt < cutoff:
            continue
        status = "✅" if entry.get("success") else "❌"
        mode   = "🧪" if entry.get("mode") == "dry_run" else "🚀"
        img    = "🖼" if entry.get("has_image") else "  "
        label  = entry.get("label") or entry.get("post_type") or ""
        chars  = entry.get("chars", 0)
        print(f"{status}{mode}{img} {dt.strftime('%m/%d %H:%M')} [{label}] {chars}文字")


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
