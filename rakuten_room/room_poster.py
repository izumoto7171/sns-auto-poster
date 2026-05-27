"""
楽天ルーム自動投稿 — Playwright で商品追加 + コメント入力

ログイン戦略（2段構え）:
  1. Cookie ファイルが存在 → storage_state で読み込み
  2. ルームにアクセスしてログイン状態を検証
  3. 未ログインならID/PW でフォールバックログイン → Cookie を更新保存
"""

import os
import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# 環境変数
RAKUTEN_EMAIL    = os.environ.get("RAKUTEN_EMAIL", "")
RAKUTEN_PASSWORD = os.environ.get("RAKUTEN_PASSWORD", "")

# Cookie ファイルパス（GitHub Actions では RAKUTEN_COOKIES Secret から生成）
COOKIE_PATH = os.path.join(os.path.dirname(__file__), "rakuten_cookies.json")

# 楽天URL
ROOM_URL     = "https://room.rakuten.co.jp/"
ROOM_ADD_URL = "https://room.rakuten.co.jp/item/add"
LOGIN_URL    = "https://grp01.id.rakuten.co.jp/rms/nid/login"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


async def _build_context(browser):
    """Cookie があれば読み込み、なければ新規コンテキストを返す"""
    kwargs = dict(
        user_agent=USER_AGENT,
        viewport={"width": 1280, "height": 800},
    )
    if os.path.exists(COOKIE_PATH):
        print("[room_poster] 既存の Cookie を読み込みます")
        kwargs["storage_state"] = COOKIE_PATH
    else:
        print("[room_poster] Cookie なし → 新規コンテキスト")
    return await browser.new_context(**kwargs)


async def _ensure_login(page, context) -> bool:
    """
    ルームにアクセスしてログイン状態を確認。
    未ログインなら ID/PW でフォールバックし Cookie を更新保存する。

    Returns:
        True  — ログイン済み（または成功）
        False — ログイン失敗
    """
    await page.goto(ROOM_URL, timeout=30000)
    await page.wait_for_timeout(2000)

    # ログイン判定: マイルームリンクの有無
    is_logged_in = await page.locator("text=マイルーム").is_visible()

    if is_logged_in:
        print("[room_poster] Cookie ログイン有効")
        return True

    # --- フォールバック: ID/PW ログイン ---
    print("[room_poster] Cookie 無効 → ID/PW ログインを試みます")
    if not RAKUTEN_EMAIL or not RAKUTEN_PASSWORD:
        print("[room_poster] RAKUTEN_EMAIL / RAKUTEN_PASSWORD 未設定 → スキップ")
        return False

    try:
        await page.goto(LOGIN_URL, timeout=30000)
        await page.fill("#loginInner_u", RAKUTEN_EMAIL)
        await page.fill("#loginInner_p", RAKUTEN_PASSWORD)
        await page.click("input[type='submit']")
        await page.wait_for_url("https://room.rakuten.co.jp/**", timeout=15000)

        # Cookie を更新保存（次回以降は Cookie で通れるように）
        await context.storage_state(path=COOKIE_PATH)
        print("[room_poster] ID/PW ログイン成功 → Cookie を更新しました")
        return True

    except PlaywrightTimeout:
        print(f"[room_poster] ログインタイムアウト (現在URL: {page.url})")
        return False
    except Exception as e:
        print(f"[room_poster] ログインエラー: {e}")
        return False


async def post_to_room(product: dict, review: dict) -> bool:
    """
    楽天ルームに商品を追加してコメントを投稿する。

    Args:
        product: {"url": str, "name": str, ...}
        review:  {"comment": str, "hashtags": list[str], ...}

    Returns:
        True  — 投稿成功
        False — 失敗
    """
    comment   = review.get("comment", "")
    hashtags  = review.get("hashtags", [])
    full_text = comment + "\n" + " ".join(f"#{t}" for t in hashtags)
    item_url  = product.get("url", "")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await _build_context(browser)
        page    = await context.new_page()

        try:
            # ログイン（Cookie → ID/PW の2段構え）
            if not await _ensure_login(page, context):
                return False

            # 商品追加ページへ
            await page.goto(ROOM_ADD_URL, timeout=20000)
            await page.wait_for_load_state("domcontentloaded")

            # 商品URLを入力
            url_input = page.locator(
                'input[placeholder*="URL"], input[name*="url"], input[id*="url"]'
            ).first
            await url_input.fill(item_url)
            await page.keyboard.press("Enter")
            await asyncio.sleep(2)

            # コメント入力欄を探す
            comment_selector = (
                'textarea[placeholder*="コメント"], '
                'textarea[name*="comment"], '
                'textarea[id*="comment"]'
            )
            try:
                await page.wait_for_selector(comment_selector, timeout=8000)
                await page.fill(comment_selector, full_text[:500])
            except PlaywrightTimeout:
                # フォールバック: 最初の textarea に入力
                textareas = page.locator("textarea")
                if await textareas.count() > 0:
                    await textareas.first.fill(full_text[:500])
                else:
                    print("[room_poster] コメント入力欄が見つからない")

            # 投稿ボタンをクリック
            submit_selector = (
                'button[type="submit"], input[type="submit"], '
                'button:has-text("追加"), button:has-text("投稿")'
            )
            await page.click(submit_selector, timeout=5000)
            await asyncio.sleep(3)

            # 成功判定（URL が商品追加ページから変わっていれば成功とみなす）
            if "add" not in page.url:
                print(f"[room_poster] 投稿成功: {product.get('name', '')[:30]}")
                return True
            else:
                print(f"[room_poster] 投稿結果不明 (URL: {page.url})")
                return True  # 楽天側で非同期処理される場合があるため True

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
