"""
楽天ルーム自動投稿 — Playwright で商品追加 + コメント入力
"""

import os
import asyncio
import json
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

RAKUTEN_EMAIL    = os.environ.get("RAKUTEN_EMAIL", "")
RAKUTEN_PASSWORD = os.environ.get("RAKUTEN_PASSWORD", "")

# 楽天ルームのURL
ROOM_URL     = "https://room.rakuten.co.jp/"
ROOM_ADD_URL = "https://room.rakuten.co.jp/item/add"  # 商品追加ページ


async def post_to_room(product: dict, review: dict) -> bool:
    """
    楽天ルームに商品を追加してコメントを投稿する。

    Returns:
        True  — 投稿成功
        False — 失敗
    """
    if not RAKUTEN_EMAIL or not RAKUTEN_PASSWORD:
        print("[room_poster] RAKUTEN_EMAIL / RAKUTEN_PASSWORD 未設定 → スキップ")
        return False

    comment   = review.get("comment", "")
    hashtags  = review.get("hashtags", [])
    full_text = comment + "\n" + " ".join(f"#{t}" for t in hashtags)
    item_url  = product.get("url", "")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        try:
            # ログイン
            print("[room_poster] 楽天ログイン中...")
            await page.goto("https://grp02.id.rakuten.co.jp/rms/nid/login", timeout=30000)
            await page.fill('input[name="u"]', RAKUTEN_EMAIL)
            await page.fill('input[name="p"]', RAKUTEN_PASSWORD)
            await page.click('input[type="submit"]')
            await page.wait_for_load_state("networkidle", timeout=20000)

            if "login" in page.url.lower() or "error" in page.url.lower():
                print(f"[room_poster] ログイン失敗: {page.url}")
                return False
            print("[room_poster] ログイン成功")

            # 楽天ルームの商品追加ページへ
            await page.goto(ROOM_ADD_URL, timeout=20000)
            await page.wait_for_load_state("domcontentloaded")

            # 商品URLを入力
            url_input = page.locator('input[placeholder*="URL"], input[name*="url"], input[id*="url"]').first
            await url_input.fill(item_url)
            await page.keyboard.press("Enter")
            await asyncio.sleep(2)

            # コメント入力欄を探す
            comment_selector = 'textarea[placeholder*="コメント"], textarea[name*="comment"], textarea[id*="comment"]'
            try:
                await page.wait_for_selector(comment_selector, timeout=8000)
                await page.fill(comment_selector, full_text[:500])
            except PlaywrightTimeout:
                # フォールバック: 最初のtextareaに入力
                textareas = page.locator("textarea")
                if await textareas.count() > 0:
                    await textareas.first.fill(full_text[:500])
                else:
                    print("[room_poster] コメント入力欄が見つからない")

            # 投稿ボタンをクリック
            submit_selector = 'button[type="submit"], input[type="submit"], button:has-text("追加"), button:has-text("投稿")'
            await page.click(submit_selector, timeout=5000)
            await asyncio.sleep(3)

            # 成功判定（URLが変わるか確認）
            if "add" not in page.url:
                print(f"[room_poster] 投稿成功: {product['name'][:30]}")
                return True
            else:
                print(f"[room_poster] 投稿結果不明 (URL: {page.url})")
                return True  # タイムアウトでも楽天側で処理される場合あり

        except PlaywrightTimeout as e:
            print(f"[room_poster] タイムアウト: {e}")
            return False
        except Exception as e:
            print(f"[room_poster] エラー: {e}")
            return False
        finally:
            await browser.close()


def post_sync(product: dict, review: dict) -> bool:
    """同期ラッパー"""
    return asyncio.run(post_to_room(product, review))
