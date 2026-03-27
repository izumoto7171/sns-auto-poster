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


async def login_and_save(username, email, password, headless=False):
    """ブラウザでXにログインしてCookieを保存"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()

        print("🌐 X.comを開いています...")
        await page.goto("https://x.com/login")
        await page.wait_for_load_state("domcontentloaded")

        # ユーザー名入力
        print("📝 ユーザー名を入力中...")
        await page.fill('input[autocomplete="username"]', username)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(2000)

        # メールアドレス確認が求められる場合
        try:
            email_input = await page.wait_for_selector(
                'input[data-testid="ocfEnterTextTextInput"]',
                timeout=3000
            )
            print("📧 メール確認入力中...")
            await email_input.fill(email)
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(2000)
        except Exception:
            pass

        # パスワード入力
        print("🔑 パスワードを入力中...")
        await page.fill('input[name="password"]', password)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(3000)

        # ログイン確認
        if "home" in page.url or "x.com" in page.url:
            print("✅ ログイン成功！Cookieを保存...")
            cookies = await context.cookies()
            with open(COOKIES_FILE, "w") as f:
                json.dump(cookies, f)
            print(f"   保存先: {COOKIES_FILE}")
        else:
            print(f"⚠️ ログイン確認できませんでした。URL: {page.url}")

        await browser.close()


async def post_tweet(text: str, headless=True) -> str:
    """保存済みCookieを使ってツイートを投稿"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()

        # Cookie読み込み
        if COOKIES_FILE.exists():
            with open(COOKIES_FILE) as f:
                cookies = json.load(f)
            await context.add_cookies(cookies)
        else:
            print("⚠️ Cookie未保存。先にログインしてください")
            await browser.close()
            return None

        page = await context.new_page()
        await page.goto("https://x.com/home")
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(2000)

        # ツイート入力欄をクリック
        print("✏️  ツイート入力中...")
        tweet_box = await page.wait_for_selector(
            '[data-testid="tweetTextarea_0"]',
            timeout=10000
        )
        await tweet_box.click()
        await page.wait_for_timeout(500)

        # テキストを入力（改行対応）
        await tweet_box.fill(text)
        await page.wait_for_timeout(1000)

        # 投稿ボタンをクリック
        print("🚀 投稿ボタンをクリック...")
        post_btn = await page.wait_for_selector(
            '[data-testid="tweetButtonInline"]',
            timeout=5000
        )
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
