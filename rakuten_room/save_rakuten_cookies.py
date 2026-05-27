"""
楽天ルーム Cookie 取得スクリプト（ローカル実行専用）

手順:
  1. python rakuten_room/save_rakuten_cookies.py
  2. 開いたブラウザで楽天にログインし、マイルームが表示されたら
  3. このターミナルで Enter を押す
  → rakuten_room/rakuten_cookies.json が生成される

生成後は GitHub Secrets (RAKUTEN_COOKIES) に登録してください:
  gh secret set RAKUTEN_COOKIES < rakuten_room/rakuten_cookies.json
"""

import asyncio
import os
from playwright.async_api import async_playwright


async def save_cookies():
    os.makedirs("rakuten_room", exist_ok=True)
    cookie_path = "rakuten_room/rakuten_cookies.json"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        print("楽天ルームのログイン画面を開きます...")
        await page.goto("https://room.rakuten.co.jp/")

        print("\n【重要】ブラウザで楽天にログインし、マイルームが表示されるまで進めてください。")
        print("完了したら、このターミナルに戻って Enter キーを押してください...")

        await asyncio.to_thread(input)

        await context.storage_state(path=cookie_path)
        print(f"Cookie を保存しました: {cookie_path}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(save_cookies())
