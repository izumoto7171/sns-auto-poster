"""
Xのブラウザ操作でCookieを手動保存
1回だけ手動でログイン → Cookie保存 → 以降は自動投稿
"""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

COOKIES_FILE = Path(__file__).parent / "x_browser_cookies.json"


async def manual_login_and_save():
    """ブラウザを開いてユーザーが手動ログイン → Cookieを保存"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        print("=" * 50)
        print("🌐 ブラウザが開きます")
        print("=" * 50)
        print("【手順】")
        print("1. ブラウザでXにログインしてください")
        print("2. ホーム画面が表示されたら、")
        print("   このターミナルで Enter を押してください")
        print("=" * 50)

        await page.goto("https://x.com/login")

        print("\n⏳ ログイン完了を自動検知中（最大300秒）...")
        print("   ブラウザでXにログインしてください！")

        # ホーム画面が表示されるまで待機（最大300秒）
        try:
            await page.wait_for_url("**/home", timeout=300000)
            print("✅ ログイン検知！")
        except Exception:
            # URLで検知できなくても、ツイートボタンで判定
            try:
                await page.wait_for_selector(
                    '[data-testid="tweetButtonInline"], [data-testid="SideNav_NewTweet_Button"]',
                    timeout=300000
                )
                print("✅ ログイン検知（ボタン確認）！")
            except Exception:
                print("⚠️ タイムアウト。現在のCookieで保存します。")

        # Cookie保存
        cookies = await context.cookies()
        with open(COOKIES_FILE, "w") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)

        print(f"\n✅ Cookie保存完了！({len(cookies)}件)")
        print(f"   保存先: {COOKIES_FILE}")
        print("\n次回からは自動でログイン状態が維持されます🎉")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(manual_login_and_save())
