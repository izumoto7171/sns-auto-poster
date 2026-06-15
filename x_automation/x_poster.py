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
from typing import Optional
from x_post_generator import generate_post, get_today_schedule, generate_value_thread

# Supabase クライアント・リトライユーティリティ（プロジェクトルートから import）
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from db_client import db
from retry_utils import with_retry
from utils.notifier import notify as _discord_notify

# 直近の投稿で取得した tweet_id（ブログ連動リプライ用）
_last_tweet_id: Optional[str] = None


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
        "posted_at": now,   # 日付フィルタ用（posted_at で統一）
        "datetime":  now,
        "platform":  "x",
        "type":      entry.get("type", ""),
        "label":     entry.get("label", ""),
        "chars":     entry.get("chars", 0),
        "content":   entry.get("text", ""),
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
    try:
        db.insert_post(
            platform       = "x",
            post_type      = entry.get("type", ""),
            label          = entry.get("label", ""),
            chars          = entry.get("chars", 0),
            text           = entry.get("text", ""),
            success        = entry.get("success", False),
            mode           = entry.get("mode", "live"),
            has_image      = entry.get("has_image", False),
            tweet1_id      = entry.get("tweet1_id") or _last_tweet_id or "",
            genre          = entry.get("genre", ""),
            writing_style  = entry.get("writing_style", ""),
            posted_at_hour = entry.get("posted_at_hour", datetime.now().hour),
        )
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


def _generate_review_image(product: dict) -> str:
    """
    商品情報からスマホ編集風レビュー画像を生成してファイルパスを返す。
    楽天・Amazon商品投稿で呼び出す。失敗時は空文字列。

    Args:
        product: {"name"/"title": 商品名, "image_url": 画像URL,
                  "category": カテゴリ, "price": 価格}
    """
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from image_editor import create_review_image
        from x_post_generator import generate_review_text_for_image

        # Amazon/楽天どちらでも動くように name/title を吸収
        name     = product.get("name") or product.get("title", "")
        img_url  = product.get("image_url", "")
        category = product.get("category", "")
        # price は数値（楽天）またはdict {"amount": N, ...}（静的商品）の両方に対応
        price_raw = product.get("price", 0)
        if isinstance(price_raw, dict):
            price = int(price_raw.get("amount", 0))
        else:
            try:
                price = int(price_raw)
            except (TypeError, ValueError):
                price = 0

        if not name:
            print("⚠️  商品名が取得できないためレビュー画像をスキップ")
            return ""

        # Gemini でレビューテキストを生成
        review_text = generate_review_text_for_image(name, category, price)

        tmp_path = os.path.join(
            tempfile.gettempdir(),
            f"review_card_{int(time.time())}.jpg",
        )
        return create_review_image(name, review_text, img_url, output_path=tmp_path)
    except Exception as e:
        print(f"⚠️ レビュー画像生成スキップ: {e}")
        return ""


def _download_image_from_url(image_url: str) -> str:
    """
    商品の image_url から画像をダウンロードして一時ファイルに保存し、パスを返す。
    ダウンロード失敗・URL未設定の場合は空文字列を返す（フォールバック用）。

    楽天サムネイル（?_ex=128x128）は自動的に 400x400 に拡大して取得する。

    Returns:
        一時ファイルパス（str）。失敗時は ""。
    """
    if not image_url or not image_url.startswith("http"):
        return ""

    # 楽天サムネイルのサイズパラメータを拡大（X推奨最低解像度に合わせる）
    import re as _re
    image_url = _re.sub(r'[?&]_ex=\d+x\d+', lambda m: m.group(0).replace(
        m.group(0).split("_ex=")[1], "400x400"
    ), image_url)

    try:
        import requests

        headers = {"User-Agent": "Mozilla/5.0 (compatible; SNSBot/1.0)"}
        resp = requests.get(image_url, headers=headers, timeout=10)
        resp.raise_for_status()

        # Content-Type から拡張子を決定
        content_type = resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
        ext_map = {
            "image/jpeg": ".jpg",
            "image/jpg":  ".jpg",
            "image/png":  ".png",
            "image/gif":  ".gif",
            "image/webp": ".webp",
        }
        ext = ext_map.get(content_type, ".jpg")

        # X は webp を受け付けないため jpg に変換
        if ext == ".webp":
            try:
                from PIL import Image
                import io
                img = Image.open(io.BytesIO(resp.content)).convert("RGB")
                tmp_path = os.path.join(tempfile.gettempdir(), f"product_img_{int(time.time())}.jpg")
                img.save(tmp_path, "JPEG", quality=90)
                print(f"画像ダウンロード成功（webp→jpg変換）: {image_url[:60]}")
                return tmp_path
            except Exception as conv_err:
                print(f"⚠️ webp変換失敗: {conv_err}")
                return ""

        tmp_path = os.path.join(tempfile.gettempdir(), f"product_img_{int(time.time())}{ext}")
        with open(tmp_path, "wb") as f:
            f.write(resp.content)

        # 最低サイズチェック（1KB未満は壊れ画像の可能性）
        if os.path.getsize(tmp_path) < 1024:
            print("⚠️ ダウンロードした画像が小さすぎるためスキップ")
            os.remove(tmp_path)
            return ""

        print(f"画像ダウンロード成功: {image_url[:60]} → {tmp_path}")
        return tmp_path

    except Exception as e:
        print(f"⚠️ 画像ダウンロード失敗（テキストのみで投稿）: {e}")
        return ""


# ─────────────────────────────────────────
# Amazon URL をフルURL形式に正規化（短縮リンク不使用）
# amzn.to / bit.ly など短縮URL経由だとX上でアソシエイトIDが消えるため、
# ASINを抽出して https://www.amazon.co.jp/dp/{ASIN}?tag={TAG} に組み直す
# ─────────────────────────────────────────
def _build_full_amazon_url(url: str) -> str:
    import re
    tag = os.getenv("AMAZON_ASSOCIATE_TAG", "smartearn22-22")
    m = re.search(r'/dp/([A-Z0-9]{10})', url)
    if m:
        return f"https://www.amazon.co.jp/dp/{m.group(1)}?tag={tag}"
    return url


# ─────────────────────────────────────────
# Bitly URL短縮（BITLY_TOKEN 未設定時は元URLをそのまま返す）
# ─────────────────────────────────────────
def _shorten_url_bitly(url: str) -> str:
    """
    Bitly API で URL を短縮する。
    環境変数 BITLY_TOKEN が未設定の場合は元URLをそのまま返す（フォールバック）。
    """
    token = os.getenv("BITLY_TOKEN", "")
    if not token or not url.startswith("http"):
        return url
    try:
        import requests as _req
        resp = _req.post(
            "https://api-ssl.bitly.com/v4/shorten",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"long_url": url},
            timeout=5,
        )
        resp.raise_for_status()
        short = resp.json().get("link", url)
        print(f"Bitly短縮: {url[:50]} → {short}")
        return short
    except Exception as e:
        print(f"⚠️ Bitly短縮失敗（元URLを使用）: {e}")
        return url


# ─────────────────────────────────────────
# 子ポスト（アフィリエイトリプライ）テキスト生成
# ─────────────────────────────────────────
def _build_affiliate_reply(thread: dict, post_type: str = "amazon_thread") -> str:
    """
    親ポストへのリプライ（子ポスト）テキストを生成する。

    thread["tweet3"] からアフィリエイトURLを抽出し、
    雑誌スタイルの導線文 + Bitly短縮URL + ハッシュタグ + PR開示 で構成する。

    Args:
        thread:    generate_thread() が返したスレッド dict
        post_type: "amazon_thread" | "rakuten_thread" | "amazon"

    Returns:
        子ポスト用テキスト（str）。URLが取れなければ最低限の開示文のみ。
    """
    import re

    # tweet4 → tweet3 → tweet2 の順でアフィリエイトURLを探す
    url = ""
    for key in ("tweet4", "tweet3", "tweet2"):
        m = re.search(r'https?://\S+', thread.get(key, ""))
        if m:
            url = m.group(0).rstrip(".,)")  # 末尾の句読点を除去
            break

    # Amazon URL はフルURLに正規化（短縮リンク禁止: X上でアソシエイトIDが消えるため）
    short_url = _build_full_amazon_url(url) if url else ""

    if "rakuten" in post_type.lower():
        intro       = "紹介したアイテムの詳細・購入リンクはこちら（楽天市場）👇"
        disclosure  = "※楽天アフィリエイトに参加しています"
    else:
        intro       = "紹介したアイテムの詳細・購入リンクはこちら（Amazon）👇"
        disclosure  = "※Amazonアソシエイトに参加しています"

    parts = [intro]
    if short_url:
        parts.append(short_url)
    parts.append("#一人暮らし #便利グッズ")
    parts.append("#PR")
    parts.append(disclosure)

    return "\n".join(parts)


# ─────────────────────────────────────────
# 親ポスト（画像付き）→ 子ポスト（アフィリエイトリプライ）ツリー投稿
# ─────────────────────────────────────────
def post_parent_and_reply(
    parent_text: str,
    image_path:  str = "",
    reply_text:  str = "",
) -> bool:
    """
    「親ポスト（雑誌風文章＋商品画像）→ 子ポスト（アフィリエイトリンク）」の
    ツリー形式で X に投稿する。tweepy v2 + v1.1 media upload を使用。

    フロー:
        1. 画像があれば v1.1 media_upload でアップロード → media_id 取得
        2. v2 create_tweet で親ポストを投稿（画像添付）→ tweet_id 取得
        3. reply_text がある場合、in_reply_to_tweet_id を指定して子ポストを投稿
        4. 親ポスト失敗 → False を返す（呼び出し元でフォールバック）
           子ポスト失敗 → ログ出力のみ、親成功扱い（True を返す）

    Args:
        parent_text: 親ポストのテキスト（リンクなし・雑誌風）
        image_path:  商品画像のローカルパス（なければ空文字）
        reply_text:  子ポストのテキスト（アフィリエイトURL含む）

    Returns:
        True: 親ポスト成功（子ポストの成否は問わない）
        False: 親ポスト失敗 または tweepy 設定不備
    """
    try:
        import tweepy

        api_key       = os.getenv("X_API_KEY")
        api_secret    = os.getenv("X_API_SECRET")
        access_token  = os.getenv("X_ACCESS_TOKEN")
        access_secret = os.getenv("X_ACCESS_TOKEN_SECRET")

        if not all([api_key, api_secret, access_token, access_secret]):
            print("⚠️ X APIキーが未設定（post_parent_and_reply をスキップ）")
            return False

        # v1.1 API（メディアアップロード専用）
        auth   = tweepy.OAuth1UserHandler(api_key, api_secret, access_token, access_secret)
        api_v1 = tweepy.API(auth)

        # v2 Client（ツイート投稿）
        client = tweepy.Client(
            consumer_key        = api_key,
            consumer_secret     = api_secret,
            access_token        = access_token,
            access_token_secret = access_secret,
        )

        # ── ① 画像アップロード ────────────────────────
        media_ids = []
        if image_path and os.path.exists(image_path):
            try:
                media     = api_v1.media_upload(filename=image_path)
                media_ids = [media.media_id]
                print(f"画像アップロード成功: media_id={media.media_id}")
            except Exception as e:
                print(f"⚠️ 画像アップロード失敗（テキストのみで親ポスト）: {e}")
                media_ids = []

        # ── ② 親ポスト投稿 ────────────────────────────
        parent_kwargs: dict = {"text": parent_text}
        if media_ids:
            parent_kwargs["media_ids"] = media_ids

        resp      = client.create_tweet(**parent_kwargs)
        parent_id = str(resp.data["id"])
        print(f"✅ 親ポスト成功: ID={parent_id} | 画像={'あり' if media_ids else 'なし'}")
        print(f"   URL: https://x.com/{os.getenv('X_USERNAME', 'user')}/status/{parent_id}")

        global _last_tweet_id
        _last_tweet_id = parent_id

        # ── ③ 子ポスト（リプライ）投稿 ──────────────────
        if reply_text and parent_id:
            try:
                time.sleep(2)  # 連投ペナルティ回避
                reply_resp = client.create_tweet(
                    text                  = reply_text,
                    in_reply_to_tweet_id  = parent_id,
                )
                reply_id = str(reply_resp.data["id"])
                print(f"✅ 子ポスト（リプライ）成功: ID={reply_id}")
            except Exception as e:
                print(f"⚠️ 子ポスト失敗（親ポストは成功済み・ログのみ）: {e}")

        return True

    except ImportError:
        print("⚠️ tweepy 未インストール")
        return False
    except Exception as e:
        print(f"❌ 親ポスト失敗: {e}")
        return False


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
        global _last_tweet_id
        _last_tweet_id = str(tweet_id)
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
    """twikit経由でXに投稿 — code 344 (daily limit) が頻発するため常時スキップ"""
    print("⏭️  twikit をスキップ（daily limit 344 回避）→ ブラウザへ")
    return False
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
        global _last_tweet_id
        _last_tweet_id = str(tweet.id)
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
    """Amazonアフィリエイトスレッドを最大4ツイートで投稿する（browser直行）"""
    tweet1 = thread.get("tweet1", "")
    tweet2 = thread.get("tweet2", "")
    tweet3 = thread.get("tweet3", "")
    tweet4 = thread.get("tweet4", "")
    if not tweet1:
        print("❌ スレッドのtweet1が空")
        return False

    # Playwright ブラウザで直接投稿（twikit は code 344 頻発のためスキップ）
    print("🌐 ブラウザ（Playwright）でスレッド投稿...")
    try:
        from x_browser_poster import post_thread_sync
        tweets = [t for t in [tweet1, tweet2, tweet3, tweet4] if t]
        # 最終ツイートにURLが含まれているか事前チェック（アフィリエイト欠落防止）
        if tweets and "http" not in tweets[-1]:
            print(f"⚠️ 最終ツイートにURLが含まれていません。内容: {tweets[-1][:80]}")
        return post_thread_sync(tweets)
    except Exception as e:
        print(f"⚠️ スレッド投稿（Playwright）失敗: {e}")
        # tweet1のみのフォールバックはアフィリエイトURLが失われるため行わない
        return False


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

    # tweet1を投稿: tweepy（ID取得できてリプライ可）→ browser の順
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

    # tweet2: tweepy でリプライ（twikit は daily limit 344 頻発のためスキップ）
    if _last_tweet_id:
        try:
            import tweepy
            api_key       = os.getenv("X_API_KEY")
            api_secret    = os.getenv("X_API_SECRET")
            access_token  = os.getenv("X_ACCESS_TOKEN")
            access_secret = os.getenv("X_ACCESS_TOKEN_SECRET")
            if all([api_key, api_secret, access_token, access_secret]):
                client = tweepy.Client(
                    consumer_key        = api_key,
                    consumer_secret     = api_secret,
                    access_token        = access_token,
                    access_token_secret = access_secret,
                )
                time.sleep(2)
                client.create_tweet(text=tweet2, in_reply_to_tweet_id=_last_tweet_id)
                print("✅ tweet2リプライ成功（tweepy）")
            else:
                print("⚠️ X APIキー未設定のためtweet2リプライをスキップ")
        except Exception as e:
            print(f"⚠️ tweet2リプライ失敗（無視）: {e}")
    else:
        print("⚠️ tweet1のID未取得のためtweet2リプライをスキップ")

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
# ブログ連動パイプライン起動
# ─────────────────────────────────────────
def _post_x_info_from_queue() -> bool:
    """
    pending_tasks から x_info タスクを1件ポップして投稿する。
    Gemini で有益ツイートを生成し、tweepy → twikit でポスト。
    """
    from x_post_generator import generate_info_post

    tasks = db.pop_pending_batch(n=1, post_type="x_info")
    if not tasks:
        print("[X-Info] キューにタスクなし。スキップ。")
        return False

    task    = tasks[0]
    task_id = task["id"]
    raw     = task.get("raw_data", {})
    keyword = raw.get("keyword", "節約")

    try:
        result = generate_info_post(task)
        text   = result["text"]
        label  = result["label"]
        chars  = result["chars"]
        print(f"\n[X-Info] {label} ({chars}文字)")
        print("─" * 45)
        print(text)
        print()

        image_path = _generate_card_file(text, "useful")
        success    = post_with_twikit(text, image_path)
        if not success:
            success = post_with_browser(text)

        if image_path and os.path.exists(image_path):
            try:
                os.remove(image_path)
            except Exception:
                pass

        if success:
            db.mark_task_done(task_id)
        else:
            db.mark_task_failed(task_id, "全投稿手段が失敗")
            _discord_notify(
                "x_automation/x_poster.py",
                "X投稿(x_info)：全手段が失敗（投稿スキップ）",
                f"keyword={keyword} twikit/Playwright すべて失敗",
            )

        save_log({
            "datetime":  datetime.now().isoformat(),
            "type":      "x_info",
            "label":     label,
            "chars":     chars,
            "text":      text,
            "success":   success,
            "mode":      "live",
            "has_image": bool(image_path),
        })
        return success
    except Exception as e:
        db.mark_task_failed(task_id, str(e))
        print(f"❌ x_info 投稿エラー: {e}")
        return False


def _trigger_blog_pipeline(tweet_id: str, keyword: str, post_type: str = "a8") -> None:
    """
    A8 / 高優先度投稿の成功後にブログ記事生成 → はてな公開 → Xリプライを行う。
    reply_funnel_linker.py を subprocess として非同期で起動する。
    """
    import subprocess
    script = os.path.join(os.path.dirname(__file__), "..", "reply_funnel_linker.py")
    if not os.path.exists(script):
        print("⚠️ reply_funnel_linker.py が見つかりません。ブログ連動をスキップ。")
        return
    cmd = [
        sys.executable, script,
        "--tweet-id",  tweet_id,
        "--keyword",   keyword,
        "--post-type", post_type,
    ]
    try:
        print(f"[BlogPipeline] 起動: tweet_id={tweet_id} keyword={keyword}")
        subprocess.Popen(cmd, cwd=os.path.dirname(__file__))
    except Exception as e:
        print(f"⚠️ BlogPipeline 起動失敗: {e}")


# ─────────────────────────────────────────
# メイン投稿関数
# ─────────────────────────────────────────
def post_now(force_type: str = None, test_mode: bool = False) -> bool:
    """投稿文を生成してXに投稿（画像カード付き）"""
    from x_post_generator import generate_amazon_product_post

    post = generate_post(force_type)

    print(f"\n投稿タイプ: {post['label']} ({post['chars']}文字)")
    print(f"投稿時刻: {datetime.now().strftime('%Y/%m/%d %H:%M')}")

    # Amazon商品タイプはスレッド投稿（+ レビュー画像添付）
    if post["type"] == "product":
        amazon_post = generate_amazon_product_post()
        if not amazon_post or not amazon_post.get("thread"):
            # 静的データで再試行（Gemini/PA-APIが使えない場合）
            print("⚠️ Amazon商品取得失敗、静的データで再試行")
            amazon_post = generate_amazon_product_post(force_refresh=True)

        if amazon_post and amazon_post.get("thread"):
            thread        = amazon_post["thread"]
            product_info  = amazon_post.get("product", {})
            product_title = product_info.get("title", "")
            print(f"Amazon商品: {product_title}")

            # 投稿直前URLチェック: 商品直リンクがない・404・検索URLはスキップ
            amazon_url = product_info.get("amazon_url", "")
            import re as _re
            if not amazon_url or "/s?" in amazon_url:
                print(f"⚠️ 商品直リンクなし（検索URL or 空）→ 投稿スキップ: {amazon_url[:60]}")
                return False
            if not test_mode:
                from fetch_amazon_deals import check_amazon_url_alive
                if not check_amazon_url_alive(amazon_url):
                    m = _re.search(r'/dp/([A-Z0-9]{10})', amazon_url)
                    if m:
                        deactivated = db.deactivate_amazon_product_by_asin(m.group(1))
                        print(f"⚠️ 商品ページが存在しません（ASIN={m.group(1)}）→ Supabaseから{deactivated}件を無効化して投稿スキップ")
                    else:
                        print(f"⚠️ 商品URLが無効（ASIN不明）→ 投稿スキップ: {amazon_url[:60]}")
                    return False

            if test_mode:
                reply_preview = _build_affiliate_reply(thread, "amazon_thread")
                print("\n[DRY RUN] Amazonツリー投稿プレビュー:")
                print("── 親ポスト（雑誌風文章＋画像）──")
                print(thread.get("tweet1", ""))
                print("── 子ポスト（アフィリエイトリプライ）──")
                print(reply_preview)
                success = True
                image_path = ""
            else:
                # 画像取得: レビューカード生成 → image_url直接DL → なし の優先順
                image_path = _generate_review_image(product_info)
                if not image_path:
                    image_path = _download_image_from_url(product_info.get("image_url", ""))

                tweet1_text = thread.get("tweet1", "")
                reply_text  = _build_affiliate_reply(thread, "amazon_thread")

                # 親ポスト（画像付き）→ 子ポスト（アフィリエイトリプライ）ツリー投稿
                success = post_parent_and_reply(tweet1_text, image_path, reply_text)
                if not success:
                    # tweepy 完全失敗 → ブラウザ経由スレッド投稿にフォールバック
                    print("⚠️ tweepy失敗、ブラウザスレッド投稿にフォールバック")
                    success = post_amazon_thread(thread)

            if image_path and os.path.exists(image_path):
                try:
                    os.remove(image_path)
                except Exception:
                    pass

            save_log({
                "datetime":      datetime.now().isoformat(),
                "type":          "amazon_thread",
                "label":         "Amazon商品紹介",
                "chars":         len(thread.get("tweet1", "")),
                "text":          thread.get("tweet1", ""),
                "success":       success,
                "mode":          "dry_run" if test_mode else "live",
                "has_image":     bool(image_path),
                "genre":         "gadget",
                "writing_style": "Amazon",
                "posted_at_hour": datetime.now().hour,
            })
            return success

        print("❌ Amazon商品取得完全失敗、投稿スキップ")
        return False

    # Amazonプールタイプはスレッド投稿（tweet1=本文、tweet2=アフィリエイトURL）
    if post["type"] == "amazon_pool" and post.get("thread", {}).get("tweet2"):
        thread       = post["thread"]
        product_info = post.get("product", {})
        print(f"Amazonプール商品スレッド投稿: {thread.get('tweet1', '')[:40]}...")

        # 投稿直前URLチェック: 商品直リンクがない・404・検索URLはスキップ
        amazon_url = product_info.get("amazon_url", "")
        import re as _re
        if not amazon_url or "/s?" in amazon_url:
            print(f"⚠️ 商品直リンクなし（検索URL or 空）→ 投稿スキップ: {amazon_url[:60]}")
            return False
        if not test_mode:
            from fetch_amazon_deals import check_amazon_url_alive
            if not check_amazon_url_alive(amazon_url):
                m = _re.search(r'/dp/([A-Z0-9]{10})', amazon_url)
                if m:
                    deactivated = db.deactivate_amazon_product_by_asin(m.group(1))
                    print(f"⚠️ 商品ページが存在しません（ASIN={m.group(1)}）→ Supabaseから{deactivated}件を無効化して投稿スキップ")
                else:
                    print(f"⚠️ 商品URLが無効（ASIN不明）→ 投稿スキップ: {amazon_url[:60]}")
                return False

        if test_mode:
            print("\n[DRY RUN] Amazonプールツリー投稿プレビュー:")
            print("── 親ポスト（体験談）──")
            print(thread.get("tweet1", ""))
            print("── 子ポスト（アフィリエイトリプライ）──")
            print(thread.get("tweet2", ""))
            success    = True
            image_path = ""
        else:
            image_path = _generate_review_image(product_info)
            if not image_path:
                image_path = _download_image_from_url(product_info.get("image_url", ""))

            tweet1_text = thread.get("tweet1", "")
            reply_text  = thread.get("tweet2", "")

            success = post_parent_and_reply(tweet1_text, image_path, reply_text)
            if not success:
                print("⚠️ tweepy失敗、ブラウザスレッド投稿にフォールバック")
                success = post_amazon_thread(thread)

            if image_path and os.path.exists(image_path):
                try:
                    os.remove(image_path)
                except Exception:
                    pass

        save_log({
            "datetime":      datetime.now().isoformat(),
            "type":          "amazon_pool",
            "label":         "Amazon商品紹介（プール）",
            "chars":         len(thread.get("tweet1", "")),
            "text":          thread.get("tweet1", ""),
            "success":       success,
            "mode":          "dry_run" if test_mode else "live",
            "has_image":     bool(image_path) if not test_mode else False,
            "genre":         "gadget",
            "writing_style": "amazon_pool",
            "posted_at_hour": datetime.now().hour,
        })
        return success

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
            "datetime":      datetime.now().isoformat(),
            "type":          "a8",
            "label":         "A8アフィリエイト",
            "chars":         len(thread.get("tweet1", "")),
            "text":          thread.get("tweet1", ""),
            "success":       success,
            "mode":          "dry_run" if test_mode else "live",
            "has_image":     False,
            "genre":         post.get("genre", ""),
            "writing_style": post.get("writing_style", ""),
            "posted_at_hour": datetime.now().hour,
        })
        # A8投稿成功 → ブログ連動パイプライン起動
        if success and not test_mode and _last_tweet_id:
            _trigger_blog_pipeline(
                tweet_id  = _last_tweet_id,
                keyword   = post.get("keyword", post.get("label", "副業")),
                post_type = "a8",
            )
        return success

    # 楽天タイプはスレッド投稿（tweet1=本文、tweet2=URL）+ レビュー画像添付
    if post["type"] == "rakuten" and post.get("thread", {}).get("tweet2"):
        thread       = post["thread"]
        product_info = post.get("product", {})
        print(f"楽天商品スレッド投稿: {thread.get('tweet1', '')[:40]}...")
        if test_mode:
            reply_preview = _build_affiliate_reply(thread, "rakuten_thread")
            print("\n[DRY RUN] 楽天ツリー投稿プレビュー:")
            print("── 親ポスト（雑誌風文章＋画像）──")
            print(thread.get("tweet1", ""))
            print("── 子ポスト（アフィリエイトリプライ）──")
            print(reply_preview)
            success    = True
            image_path = ""
        else:
            # 画像取得: レビューカード生成 → image_url直接DL → なし の優先順
            image_path  = _generate_review_image(product_info)
            if not image_path:
                image_path = _download_image_from_url(product_info.get("image_url", ""))

            tweet1_text = thread.get("tweet1", "")
            reply_text  = _build_affiliate_reply(thread, "rakuten_thread")

            # 親ポスト（画像付き）→ 子ポスト（アフィリエイトリプライ）ツリー投稿
            success = post_parent_and_reply(tweet1_text, image_path, reply_text)
            if not success:
                print("⚠️ tweepy失敗、ブラウザスレッド投稿にフォールバック")
                success = post_amazon_thread(thread)

            if image_path and os.path.exists(image_path):
                try:
                    os.remove(image_path)
                except Exception:
                    pass

        save_log({
            "datetime":      datetime.now().isoformat(),
            "type":          "rakuten_thread",
            "label":         "楽天商品紹介",
            "chars":         len(thread.get("tweet1", "")),
            "text":          thread.get("tweet1", ""),
            "success":       success,
            "mode":          "dry_run" if test_mode else "live",
            "has_image":     bool(image_path),
            "genre":         post.get("genre", "daily_goods"),
            "writing_style": post.get("writing_style", "楽天"),
            "posted_at_hour": datetime.now().hour,
        })
        return success

    text = post["text"]

    # useful / empathy タイプはスレッド形式（脱ボット化）
    # リンクなし tweet1 → リプライで詳細案内 の2ツイート構成
    if not test_mode and post["type"] in ("useful", "empathy"):
        print("📌 スレッド形式で投稿（リンク分離でリーチ最大化）")
        success = post_value_thread(post["type"])
        save_log({
            "datetime":      datetime.now().isoformat(),
            "type":          post["type"],
            "label":         post["label"],
            "chars":         post["chars"],
            "text":          text,
            "success":       success,
            "mode":          "live_thread",
            "has_image":     True,
            "genre":         post.get("genre", "saving"),
            "writing_style": post.get("writing_style", ""),
            "posted_at_hour": datetime.now().hour,
        })
        return success

    # 画像カード生成（テストモードでも生成して確認）
    image_path = _generate_card_file(text, post["type"])

    # 投稿実行（twikit → browser の順でフォールバック）
    if test_mode:
        success = dry_run(text, image_path)
    else:
        success = post_with_twikit(text, image_path)
        if not success:
            print("⚠️ twikit失敗、ブラウザで再試行（画像なし）...")
            success = post_with_browser(text)
        if not success:
            _discord_notify(
                "x_automation/x_poster.py",
                "X投稿：全手段が失敗（投稿スキップ）",
                f"type={post['type']} label={post['label']} tweepy/twikit/Playwright すべて失敗",
            )

    # 一時ファイル削除
    if image_path and os.path.exists(image_path):
        try:
            os.remove(image_path)
        except Exception:
            pass

    # ログ保存
    save_log({
        "datetime":      datetime.now().isoformat(),
        "type":          post["type"],
        "label":         post["label"],
        "chars":         post["chars"],
        "text":          text,
        "success":       success,
        "mode":          "dry_run" if test_mode else "live",
        "has_image":     bool(image_path),
        "genre":         post.get("genre", ""),
        "writing_style": post.get("writing_style", ""),
        "posted_at_hour": datetime.now().hour,
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

    cmd       = sys.argv[1] if len(sys.argv) > 1 else "test"
    # --type x_info などのオプションを簡易パース
    force_post_type: Optional[str] = None
    for i, arg in enumerate(sys.argv[2:], start=2):
        if arg == "--type" and i + 1 < len(sys.argv):
            force_post_type = sys.argv[i + 1]

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
        if force_post_type == "x_info":
            _post_x_info_from_queue()
        else:
            post_now(test_mode=False)

    elif cmd == "schedule":
        run_today_schedule(test_mode=True)

    elif cmd == "log":
        show_log()
