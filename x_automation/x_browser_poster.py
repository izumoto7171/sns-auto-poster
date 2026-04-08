"""
X（Twitter）ブラウザ自動投稿
Playwrightでブラウザを操作してツイートを投稿（APIキー不要・完全無料）
"""
import os
import json
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

COOKIES_FILE = Path(__file__).parent / "x_browser_cookies.json"


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


STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'languages', { get: () => ['ja-JP', 'ja', 'en-US'] });
window.chrome = { runtime: {} };
"""


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
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
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
        username_el = await page.wait_for_selector('input[autocomplete="username"]', timeout=10000)
        await username_el.fill(username)
        await page.wait_for_timeout(500)

        # 「次へ」ボタンをクリック（test-idなしのテキストで探す）
        try:
            next_btn = await page.wait_for_selector('button:has-text("Next"), button:has-text("次へ")', timeout=3000)
            await next_btn.click()
        except Exception:
            await page.keyboard.press("Enter")
        await page.wait_for_timeout(2500)

        print(f"  現在のURL: {page.url}")

        # 中間認証（メール/電話番号確認）が求められる場合
        try:
            mid_el = await page.wait_for_selector(
                'input[data-testid="ocfEnterTextTextInput"]', timeout=5000
            )
            print("📧 中間認証画面 → メールアドレスを入力中...")
            await mid_el.fill(email)
            try:
                next_btn2 = await page.wait_for_selector('button:has-text("Next"), button:has-text("次へ")', timeout=2000)
                await next_btn2.click()
            except Exception:
                await page.keyboard.press("Enter")
            await page.wait_for_timeout(2000)
        except Exception:
            pass

        # パスワード入力（wait_for_selectorで確実に待機）
        print(f"  現在のURL: {page.url}")
        print("🔑 パスワードを入力中...")
        pw_el = await page.wait_for_selector('input[name="password"]', timeout=15000)
        await pw_el.fill(password)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(4000)

        # ログイン確認
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


async def post_tweet(text: str, headless=True) -> str:
    """保存済みCookieを使ってツイートを投稿。Cookieがなければ自動ログインを試みる"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )

        # Cookie読み込み（環境変数からの復元も試みる）
        _load_env_cookies()
        if COOKIES_FILE.exists():
            with open(COOKIES_FILE) as f:
                cookies = json.load(f)
            await context.add_cookies(cookies)
            print("✅ Cookie読み込み成功")
        else:
            # Cookie未設定 → 認証情報でログインを試みる
            username = os.environ.get("X_USERNAME", "")
            email    = os.environ.get("X_EMAIL", "")
            password = os.environ.get("X_PASSWORD", "")
            if not (username and password):
                print("⚠️ Cookie未保存かつX_USERNAME/X_PASSWORDも未設定")
                await browser.close()
                return None

            print("🔐 Cookie未設定 → 認証情報でログインを試みます...")
            page_login = await context.new_page()
            try:
                await page_login.goto("https://x.com/login")
                await page_login.wait_for_load_state("domcontentloaded")
                await page_login.wait_for_timeout(1500)

                # ユーザー名入力
                username_input = await page_login.wait_for_selector(
                    'input[autocomplete="username"]', timeout=10000
                )
                await username_input.fill(username)
                await page_login.keyboard.press("Enter")
                await page_login.wait_for_timeout(2000)

                # 中間認証（メール/電話番号確認）が出た場合は対応
                try:
                    mid_input = await page_login.wait_for_selector(
                        'input[data-testid="ocfEnterTextTextInput"]', timeout=4000
                    )
                    print("📧 中間認証画面 → メールアドレスを入力")
                    await mid_input.fill(email)
                    await page_login.keyboard.press("Enter")
                    await page_login.wait_for_timeout(2000)
                except Exception:
                    pass

                # パスワード入力（セレクタで待機）
                pw_input = await page_login.wait_for_selector(
                    'input[name="password"]', timeout=15000
                )
                await pw_input.fill(password)
                await page_login.keyboard.press("Enter")
                await page_login.wait_for_timeout(5000)

                current_url = page_login.url
                if "/login" in current_url or "/i/flow" in current_url:
                    print(f"❌ ログイン失敗（URL: {current_url}）。2FA/CAPTCHAの可能性")
                    await browser.close()
                    return None
                print(f"✅ ログイン成功（URL: {current_url}）")
            except Exception as e:
                print(f"❌ ログインエラー: {e}")
                await browser.close()
                return None
            finally:
                await page_login.close()

        page = await context.new_page()
        await page.goto("https://x.com/home")
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(2000)

        # ツイート入力欄をクリック（複数セレクタでフォールバック）
        print("✏️  ツイート入力中...")
        tweet_box = None
        for selector in [
            '[data-testid="tweetTextarea_0"]',
            '[data-testid="tweetTextarea_0Root"] div[contenteditable="true"]',
            'div[contenteditable="true"][data-testid]',
        ]:
            try:
                tweet_box = await page.wait_for_selector(selector, timeout=5000)
                break
            except Exception:
                continue

        if not tweet_box:
            print("❌ ツイート入力欄が見つかりません")
            await browser.close()
            return None

        await tweet_box.click()
        await page.wait_for_timeout(500)

        # テキストを入力（keyboard.typeでReactイベントを確実に発火）
        await page.keyboard.type(text, delay=30)
        await page.wait_for_timeout(1500)

        # 投稿ボタンをクリック（複数セレクタでフォールバック）
        print("🚀 投稿ボタンをクリック...")
        post_btn = None
        for selector in [
            '[data-testid="tweetButtonInline"]',
            '[data-testid="tweetButton"]',
            'button[data-testid="tweetButtonInline"]:not([disabled])',
        ]:
            try:
                post_btn = await page.wait_for_selector(selector, timeout=5000)
                break
            except Exception:
                continue

        if not post_btn:
            print("❌ 投稿ボタンが見つかりません")
            await browser.close()
            return None

        await post_btn.click()
        await page.wait_for_timeout(3000)

        print("✅ 投稿完了！")
        await browser.close()
        return "posted"


def post(text: str, headless=True) -> bool:
    """同期版の投稿関数（外部から呼びやすい）"""
    try:
        result = asyncio.run(post_tweet(text, headless=headless))
        return result is not None
    except Exception as e:
        print(f"❌ 投稿エラー: {e}")
        return False


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


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "login"

    if cmd == "login":
        print("🔐 初回ログイン（ブラウザが開きます）")
        first_login(headless=False)

    elif cmd == "test":
        print("🧪 テスト投稿")
        post(
            "スマホ1台でできる副業、3選。\n\n「パソコンないから副業できない」\n\nそんなことないです。\n\n① ポイ活（月5,000円〜）\n② アンケートモニター\n③ AI画像販売\n\n全部スマホだけでOK。\n\nまず1つ試すだけで感覚つかめます✅",
            headless=False  # テストはブラウザ表示で確認
        )
