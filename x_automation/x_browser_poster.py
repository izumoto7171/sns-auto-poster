"""
X（Twitter）ブラウザ自動投稿
Playwrightでブラウザを操作してツイートを投稿（APIキー不要・完全無料）

スレッド投稿はreply方式:
  1. tweet1を投稿
  2. プロフィールページから最新ツイートURLを取得
  3. そのURLに返信としてtweet2を投稿
  4. 同様にtweet3を投稿
"""
import os
import json
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

COOKIES_FILE = Path(__file__).parent / "x_browser_cookies.json"

# Headlessでも検知されにくいUser-Agent（HeadlessChromeを含まない）
UA_MAC = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'languages', { get: () => ['ja-JP', 'ja', 'en-US'] });
window.chrome = { runtime: {} };
"""


def _load_env_cookies():
    """GitHub Actions: X_BROWSER_COOKIES環境変数からCookieファイルを復元"""
    env_cookies = os.environ.get("X_BROWSER_COOKIES", "")
    if env_cookies and not COOKIES_FILE.exists():
        try:
            with open(COOKIES_FILE, "w") as f:
                f.write(env_cookies)
            print(f"✅ X_BROWSER_COOKIES環境変数からCookieを復元（{len(env_cookies)}文字）")
        except Exception as e:
            print(f"⚠️ Cookie書き出しエラー: {e}")


def _make_browser_context(p):
    """ブラウザ + コンテキストを返す（stealth設定済み）"""
    browser = p.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ],
    )
    return browser


async def _new_context(p):
    """ブラウザとstealthコンテキストを返す"""
    browser = await p.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ],
    )
    context = await browser.new_context(
        user_agent=UA_MAC,
        viewport={"width": 1280, "height": 800},
        locale="ja-JP",
        timezone_id="Asia/Tokyo",
    )
    await context.add_init_script(STEALTH_SCRIPT)
    return browser, context


async def _load_cookies(context):
    """Cookieを環境変数またはファイルから読み込む。成功可否を返す"""
    _load_env_cookies()
    if COOKIES_FILE.exists():
        with open(COOKIES_FILE) as f:
            cookies = json.load(f)
        await context.add_cookies(cookies)
        print("✅ Cookie読み込み成功")
        return True
    print("❌ Cookieファイルが見つかりません（X_BROWSER_COOKIES 未設定）")
    return False


async def _type_tweet(page, text: str, testid_index: int = 0):
    """
    ツイート入力欄（tweetTextarea_{index}）にテキストを入力する。
    複数のセレクタでフォールバック。
    """
    selectors = [
        f'[data-testid="tweetTextarea_{testid_index}"]',
        f'[data-testid="tweetTextarea_{testid_index}Root"] div[contenteditable="true"]',
        'div[contenteditable="true"][data-testid]',
        'div[contenteditable="true"]',
    ]
    tweet_box = None
    for sel in selectors:
        try:
            tweet_box = await page.wait_for_selector(sel, timeout=5000)
            if tweet_box:
                break
        except Exception:
            continue

    if not tweet_box:
        raise RuntimeError("ツイート入力欄が見つかりません")

    await tweet_box.click()
    await page.wait_for_timeout(400)
    await page.keyboard.type(text, delay=25)
    await page.wait_for_timeout(800)
    return tweet_box


async def _click_post_button(page, testid: str = "tweetButtonInline"):
    """
    投稿/返信ボタンをクリックする。
    testid: 'tweetButtonInline'（ホーム）または 'tweetButton'（返信ダイアログ）
    """
    selectors = [
        f'[data-testid="{testid}"]',
        '[data-testid="tweetButtonInline"]',
        '[data-testid="tweetButton"]',
    ]
    post_btn = None
    for sel in selectors:
        try:
            post_btn = await page.wait_for_selector(sel, timeout=5000)
            if post_btn:
                break
        except Exception:
            continue

    if not post_btn:
        raise RuntimeError("投稿ボタンが見つかりません")

    # オーバーレイを閉じてからクリック
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(300)

    try:
        await post_btn.click(timeout=8000)
    except Exception:
        print("⚠️ ネイティブクリック失敗 → JSクリック")
        await page.evaluate("btn => btn.click()", await post_btn.element_handle())

    await page.wait_for_timeout(3000)


async def _get_latest_tweet_url(page, username: str) -> str | None:
    """
    プロフィールページから最新ツイートのURLを取得する。
    失敗した場合は None を返す。
    """
    profile_url = f"https://x.com/{username.lstrip('@')}"
    print(f"  プロフィールページに移動: {profile_url}")
    await page.goto(profile_url)
    await page.wait_for_load_state("domcontentloaded")
    await page.wait_for_timeout(3000)

    # タイムラインから最初のツイートリンクを取得
    # article > a[href*="/status/"] を探す
    try:
        tweet_link = await page.wait_for_selector(
            'article a[href*="/status/"]', timeout=8000
        )
        href = await tweet_link.get_attribute("href")
        if href and "/status/" in href:
            # 相対URLなら絶対URLに変換
            if href.startswith("/"):
                tweet_url = f"https://x.com{href}"
            else:
                tweet_url = href
            # URLにクエリパラメータがあれば除去
            tweet_url = tweet_url.split("?")[0]
            print(f"  最新ツイートURL取得: {tweet_url}")
            return tweet_url
    except Exception as e:
        print(f"  ⚠️ 最新ツイートURL取得エラー: {e}")

    return None


async def _reply_to_tweet(page, tweet_url: str, reply_text: str) -> str | None:
    """
    指定URLのツイートに返信を投稿する。
    返信後、自分の返信ツイートのURLを返す（取得できない場合はNone）。
    """
    print(f"  返信先へ移動: {tweet_url}")
    await page.goto(tweet_url)
    await page.wait_for_load_state("domcontentloaded")
    await page.wait_for_timeout(2500)

    # 返信入力欄を探す（ツイート詳細ページの返信テキストエリア）
    # data-testid="tweetTextarea_0" は返信欄にも使われる
    try:
        await _type_tweet(page, reply_text, testid_index=0)
    except Exception as e:
        # 入力欄が見つからない場合はReplyボタンをクリックして開く
        print(f"  入力欄が見つかりません、Replyボタンをクリック: {e}")
        try:
            reply_btn = await page.wait_for_selector(
                '[data-testid="reply"]', timeout=5000
            )
            await reply_btn.click()
            await page.wait_for_timeout(1500)
            await _type_tweet(page, reply_text, testid_index=0)
        except Exception as e2:
            raise RuntimeError(f"返信入力欄を開けませんでした: {e2}")

    # 返信投稿ボタンのtestidは 'tweetButton' または 'tweetButtonInline'
    await _click_post_button(page, testid="tweetButton")

    print("  ✅ 返信投稿完了")

    # 返信後のURLを取得（プロフィールから最新ツイートを拾う方法は
    # 少し待ってからもう一度プロフィールを見るか、現在のURLを確認する）
    # ここでは tweet_url の会話ページで最新の自分の返信URLを特定するのが
    # 複雑なため、Noneを返してもスレッドは成立している
    return None


async def post_thread_async(tweets: list, headless: bool = True) -> bool:
    """
    3ツイートスレッドをPlaywrightで投稿する（返信チェーン方式）。

    手順:
      1. tweet1 をホームページから投稿
      2. X_USERNAME プロフィールから最新ツイートURLを取得
      3. そのURLに tweet2 を返信として投稿
      4. プロフィールから最新ツイートURLを再取得して tweet3 を返信投稿
    """
    username = os.environ.get("X_USERNAME", "")
    if not username:
        print("⚠️ X_USERNAME が設定されていません。tweet1のみ投稿します")
        return await post_tweet(tweets[0] if tweets else "", headless=headless) is not None

    async with async_playwright() as p:
        browser, context = await _new_context(p)

        try:
            if not await _load_cookies(context):
                await browser.close()
                return False

            page = await context.new_page()

            # ── Tweet 1 ─────────────────────────────────
            print("📝 Tweet1 を投稿中...")
            await page.goto("https://x.com/home")
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(2000)

            await _type_tweet(page, tweets[0], testid_index=0)
            await _click_post_button(page, testid="tweetButtonInline")
            print("✅ Tweet1 投稿完了")

            if len(tweets) < 2:
                await browser.close()
                return True

            # ── Tweet 1 のURL取得 ───────────────────────
            await page.wait_for_timeout(2000)  # 投稿が反映されるまで待機
            tweet1_url = await _get_latest_tweet_url(page, username)
            if not tweet1_url:
                print("⚠️ Tweet1のURLが取得できませんでした。Tweet2/3をスキップ")
                await browser.close()
                return True  # tweet1は投稿できた

            # ── Tweet 2 （reply to tweet1） ─────────────
            print("📝 Tweet2 を返信投稿中...")
            await _reply_to_tweet(page, tweet1_url, tweets[1])

            if len(tweets) < 3:
                await browser.close()
                return True

            # ── Tweet 2 のURL取得（tweet1の会話ページから） ──
            await page.wait_for_timeout(2000)
            tweet2_url = await _get_latest_tweet_url(page, username)
            if not tweet2_url:
                print("⚠️ Tweet2のURLが取得できませんでした。Tweet3をスキップ")
                await browser.close()
                return True  # tweet1/2は投稿できた

            # ── Tweet 3 （reply to tweet2） ─────────────
            print("📝 Tweet3 を返信投稿中...")
            await _reply_to_tweet(page, tweet2_url, tweets[2])

            print("✅ 3ツイートスレッド投稿完了")
            await browser.close()
            return True

        except Exception as e:
            print(f"❌ スレッド投稿エラー: {e}")
            try:
                await browser.close()
            except Exception:
                pass
            return False


def post_thread_sync(tweets: list, headless: bool = True) -> bool:
    """
    同期版スレッド投稿関数（外部から呼びやすい）。
    tweets: [tweet1テキスト, tweet2テキスト, tweet3テキスト]
    """
    try:
        return asyncio.run(post_thread_async(tweets, headless=headless))
    except Exception as e:
        print(f"❌ スレッド投稿エラー（sync）: {e}")
        return False


# ─────────────────────────────────────────────────────────
# 後方互換: 単体ツイート投稿
# ─────────────────────────────────────────────────────────
async def post_tweet(text: str, headless=True) -> str | None:
    """保存済みCookieを使って単体ツイートを投稿する"""
    async with async_playwright() as p:
        browser, context = await _new_context(p)

        if not await _load_cookies(context):
            await browser.close()
            return None

        try:
            page = await context.new_page()
            await page.goto("https://x.com/home")
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(2000)

            print("✏️  ツイート入力中...")
            await _type_tweet(page, text, testid_index=0)

            print("🚀 投稿ボタンをクリック...")
            await _click_post_button(page, testid="tweetButtonInline")

            print("✅ 投稿完了！")
            await browser.close()
            return "posted"

        except Exception as e:
            print(f"❌ 投稿エラー: {e}")
            try:
                await browser.close()
            except Exception:
                pass
            return None


def post(text: str, headless=True) -> bool:
    """同期版の単体ツイート投稿関数（後方互換）"""
    try:
        result = asyncio.run(post_tweet(text, headless=headless))
        return result is not None
    except Exception as e:
        print(f"❌ 投稿エラー: {e}")
        return False


# ─────────────────────────────────────────────────────────
# 初回ログイン
# ─────────────────────────────────────────────────────────
async def login_and_save(username, email, password, headless=False):
    """ブラウザでXにログインしてCookieを保存"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context = await browser.new_context(
            user_agent=UA_MAC,
            viewport={"width": 1280, "height": 800},
        )
        await context.add_init_script(STEALTH_SCRIPT)
        page = await context.new_page()

        print("🌐 X.comを開いています...")
        await page.goto("https://x.com/login")
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(1500)

        # ユーザー名入力
        print("📝 ユーザー名を入力中...")
        username_el = await page.wait_for_selector(
            'input[autocomplete="username"]', timeout=10000
        )
        await username_el.fill(username)
        await page.wait_for_timeout(500)

        try:
            next_btn = await page.wait_for_selector(
                'button:has-text("Next"), button:has-text("次へ")', timeout=3000
            )
            await next_btn.click()
        except Exception:
            await page.keyboard.press("Enter")
        await page.wait_for_timeout(2500)

        print(f"  現在のURL: {page.url}")

        # 中間認証（メール/電話番号確認）
        try:
            mid_el = await page.wait_for_selector(
                'input[data-testid="ocfEnterTextTextInput"]', timeout=5000
            )
            print("📧 中間認証画面 → メールアドレスを入力中...")
            await mid_el.fill(email)
            try:
                next_btn2 = await page.wait_for_selector(
                    'button:has-text("Next"), button:has-text("次へ")', timeout=2000
                )
                await next_btn2.click()
            except Exception:
                await page.keyboard.press("Enter")
            await page.wait_for_timeout(2000)
        except Exception:
            pass

        # パスワード入力
        print(f"  現在のURL: {page.url}")
        print("🔑 パスワードを入力中...")
        pw_el = await page.wait_for_selector('input[name="password"]', timeout=15000)
        await pw_el.fill(password)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(4000)

        current_url = page.url
        if "/login" in current_url or "/i/flow" in current_url:
            print(f"⚠️ ログイン確認できませんでした。URL: {current_url}")
            print("  → 2FA / CAPTCHA / 不審なログイン検知の可能性")
        else:
            print(f"✅ ログイン成功！Cookieを保存... (URL: {current_url})")
            cookies = await context.cookies()
            with open(COOKIES_FILE, "w") as f:
                json.dump(cookies, f)
            print(f"   保存先: {COOKIES_FILE}")
            print(f"   Cookie数: {len(cookies)}")

        await browser.close()


def first_login(headless=False):
    """初回ログイン（ブラウザを表示して実行）"""
    env_path = Path(__file__).parent.parent / ".env"
    env = {}
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()

    username = env.get("X_USERNAME", "")
    email    = env.get("X_EMAIL", "")
    password = env.get("X_PASSWORD", "")

    asyncio.run(login_and_save(username, email, password, headless=headless))


# ─────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "login"

    if cmd == "login":
        print("🔐 初回ログイン（ブラウザが開きます）")
        first_login(headless=False)

    elif cmd == "test":
        print("🧪 テスト単体投稿")
        post(
            "スマホ1台でできる副業、3選。\n\n「パソコンないから副業できない」\n\nそんなことないです。",
            headless=False,
        )

    elif cmd == "test-thread":
        print("🧪 テストスレッド投稿（3ツイート返信チェーン）")
        tweets = [
            "一人暮らし始めてから、充電器の数が増えすぎた。\n\nスマホ・PC・イヤホン…気づいたら3個持ち歩いてた。\n\nGaN充電器1台に統合したら荷物が劇的に減った話。",
            "これを選んだ理由は3つ：\n✅ 純正より30%以上コンパクト\n✅ 67Wでノート・スマホを同時充電\n✅ 出張・カフェでも恥ずかしくないデザイン\n\n参考価格: ¥2,480（通常比24%OFF想定）",
            "Amazonで最安値を確認→",
        ]
        result = post_thread_sync(tweets, headless=False)
        print(f"結果: {'成功' if result else '失敗'}")
