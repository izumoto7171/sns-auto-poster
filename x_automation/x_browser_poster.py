"""
X（Twitter）ブラウザ自動投稿
Playwrightでブラウザを操作してツイートを投稿（APIキー不要・完全無料）

スレッド投稿はreply方式:
  1. tweet1を投稿
  2. プロフィールページから最新ツイートURLを取得
  3. そのURLに返信としてtweet2を投稿
  4. 同様にtweet3を投稿

安定性設計:
  - GitHub Actionsのヘッドレス環境ではネットワーク・描画が遅い
    → HEADLESS_WAIT_MS ですべての操作後にタメを入れる
  - Xはdata-testidを残しながら内部クラスを頻繁に変えてくる
    → 各操作で複数のセレクタを順番に試すフォールバック構造
"""
from __future__ import annotations

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

# GitHub Actionsのヘッドレス環境向けに余裕を持たせた待機時間（ms）
# CI環境（X_CI=true or CI=true）では待機時間を長くする
import os as _os_wait
_IS_CI = _os_wait.getenv("CI") == "true" or _os_wait.getenv("X_CI") == "true"
HEADLESS_WAIT_MS = 2000 if _IS_CI else 1200   # 各操作後の基本タメ
PAGE_LOAD_MS     = 5000 if _IS_CI else 3500   # ページロード後の描画待ち
PROFILE_LOAD_MS  = 7000 if _IS_CI else 4000   # プロフィールページ（タイムライン描画が重い）
AFTER_POST_MS    = 8000 if _IS_CI else 4000   # 投稿後に反映されるまで待つ時間（CI：X APIの反映遅延考慮）
TYPE_DELAY_MS    = 30                          # keyboard.typeの1文字あたりの遅延（ms）


# ─────────────────────────────────────────────────────────
# 内部ユーティリティ
# ─────────────────────────────────────────────────────────

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


async def _new_context(p, headless: bool = True):
    """ブラウザとstealthコンテキストを生成して返す"""
    browser = await p.chromium.launch(
        headless=headless,
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


async def _load_cookies(context) -> bool:
    """Cookieを環境変数またはファイルから読み込む。成功可否を返す"""
    _load_env_cookies()
    if COOKIES_FILE.exists():
        with open(COOKIES_FILE) as f:
            cookies = json.load(f)
        await context.add_cookies(cookies)
        print(f"✅ Cookie読み込み成功（{len(cookies)}件）")
        return True
    print("❌ Cookieファイルが見つかりません（X_BROWSER_COOKIES 未設定）")
    return False


async def _type_tweet(page, text: str, testid_index: int = 0):
    """
    ツイート入力欄にテキストを入力する。
    data-testidベースの複数セレクタでフォールバック。
    Xがクラス名を変えてもdata-testidが残っている限り動作する。
    """
    selectors = [
        f'[data-testid="tweetTextarea_{testid_index}"]',
        f'[data-testid="tweetTextarea_{testid_index}Root"] div[contenteditable="true"]',
        # data-testidが変わった場合の汎用フォールバック
        'div[role="textbox"][contenteditable="true"]',
        'div[contenteditable="true"]',
    ]
    tweet_box = None
    for sel in selectors:
        try:
            tweet_box = await page.wait_for_selector(sel, timeout=6000)
            if tweet_box:
                print(f"  入力欄を発見: {sel}")
                break
        except Exception:
            continue

    if not tweet_box:
        raise RuntimeError("ツイート入力欄が見つかりません（全セレクタ失敗）")

    await tweet_box.click()
    await page.wait_for_timeout(HEADLESS_WAIT_MS)
    await page.keyboard.type(text, delay=TYPE_DELAY_MS)
    # 入力後: Reactのstate更新を待つ
    await page.wait_for_timeout(HEADLESS_WAIT_MS)
    return tweet_box


async def _click_post_button(page, testid: str = "tweetButtonInline"):
    """
    投稿/返信ボタンをクリックする。
    まず指定testidを試し、失敗したら他のボタンセレクタにフォールバック。
    """
    selectors = [
        f'[data-testid="{testid}"]',
        '[data-testid="tweetButtonInline"]',
        '[data-testid="tweetButton"]',
        'button[aria-label="ポストする"]',
        'button[aria-label="Post"]',
        'button[aria-label="返信"]',
        'button[aria-label="Reply"]',
        'button[aria-label="ポスト"]',
        'button[aria-label="post"]',
        # 2026年以降のUI変更対応
        'div[role="button"][data-testid="tweetButtonInline"]',
        'div[role="button"][data-testid="tweetButton"]',
        'button:has-text("ポストする")',
        'button:has-text("Post")',
    ]
    post_btn = None
    for sel in selectors:
        try:
            btn = await page.wait_for_selector(sel, timeout=4000)
            if btn:
                # disabled な場合はスキップ
                is_disabled = await btn.get_attribute("disabled")
                if is_disabled is not None:
                    continue
                post_btn = btn
                print(f"  投稿ボタンを発見: {sel}")
                break
        except Exception:
            continue

    if not post_btn:
        raise RuntimeError("投稿ボタンが見つかりません（全セレクタ失敗）")

    # オーバーレイ・ドロップダウンを閉じてからクリック
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(400)

    try:
        await post_btn.click(timeout=10000)
    except Exception:
        print("⚠️ ネイティブクリック失敗 → JSクリック")
        await page.evaluate("btn => btn.click()", post_btn)

    # 投稿リクエストが飛んで画面が更新されるまで待つ
    await page.wait_for_timeout(AFTER_POST_MS)


async def _get_latest_tweet_url(page, username: str) -> str | None:
    """
    プロフィールページから自分の最新ツイートのURLを取得する。
    article タグ内の /status/ リンクを最初に発見したものを返す。
    """
    profile_url = f"https://x.com/{username.lstrip('@')}"
    print(f"  プロフィールページへ移動: {profile_url}")
    await page.goto(profile_url)
    await page.wait_for_load_state("domcontentloaded")
    # タイムラインはSPAの遅延描画があるため、networkidleではなく固定待機
    await page.wait_for_timeout(PROFILE_LOAD_MS)

    # セレクタ優先順:
    #   1. article内のstatus URLリンク（最も確実）
    #   2. time要素の親リンク（タイムスタンプリンクはstatus URLを持つ）
    selectors = [
        'article a[href*="/status/"]',
        'time[datetime] ~ a[href*="/status/"]',
        'a[href*="/status/"][role="link"]',
    ]
    for sel in selectors:
        try:
            tweet_link = await page.wait_for_selector(sel, timeout=8000)
            href = await tweet_link.get_attribute("href")
            if href and "/status/" in href:
                tweet_url = (
                    f"https://x.com{href}" if href.startswith("/") else href
                ).split("?")[0]
                print(f"  最新ツイートURL取得: {tweet_url}")
                return tweet_url
        except Exception:
            continue

    print("  ⚠️ 最新ツイートURLを取得できませんでした")
    return None


async def _reply_to_tweet(page, tweet_url: str, reply_text: str) -> None:
    """
    指定URLのツイートに返信を投稿する。
    ツイート詳細ページでは返信テキストエリアが最初から表示されていることが多いが、
    ない場合はReplyボタンをクリックして開く。
    """
    print(f"  返信先へ移動: {tweet_url}")
    await page.goto(tweet_url)
    await page.wait_for_load_state("domcontentloaded")
    await page.wait_for_timeout(PAGE_LOAD_MS)

    # 返信入力欄を開く試行
    try:
        await _type_tweet(page, reply_text, testid_index=0)
    except Exception as e:
        # 入力欄が最初から出ていない → Replyボタンをクリックして展開
        print(f"  入力欄なし → Replyボタンをクリック: {e}")
        reply_btn_selectors = [
            '[data-testid="reply"]',
            'button[aria-label="返信"]',
            'button[aria-label="Reply"]',
        ]
        opened = False
        for sel in reply_btn_selectors:
            try:
                btn = await page.wait_for_selector(sel, timeout=5000)
                await btn.click()
                await page.wait_for_timeout(HEADLESS_WAIT_MS)
                opened = True
                break
            except Exception:
                continue

        if not opened:
            raise RuntimeError("Replyボタンが見つかりませんでした")

        # ダイアログが開いてから再度入力欄を探す
        await _type_tweet(page, reply_text, testid_index=0)

    # 返信投稿ボタン（ダイアログ内は "tweetButton"、インラインは "tweetButtonInline"）
    await _click_post_button(page, testid="tweetButton")
    print("  ✅ 返信投稿完了")


# ─────────────────────────────────────────────────────────
# スレッド投稿（メイン）
# ─────────────────────────────────────────────────────────

async def post_thread_async(tweets: list, headless: bool = True) -> bool:
    """
    3ツイートスレッドをPlaywrightで投稿する（返信チェーン方式）。

    手順:
      1. tweet1 をホームページから投稿
      2. X_USERNAME プロフィールから最新ツイートURLを取得
      3. そのURLに tweet2 を返信として投稿
      4. 同様に tweet3 を投稿

    X_USERNAME が未設定の場合は tweet1 のみ投稿して True を返す。
    """
    if not tweets:
        print("❌ tweetsが空です")
        return False

    username = os.environ.get("X_USERNAME", "")
    if not username:
        print("⚠️ X_USERNAME 未設定 → tweet1のみ投稿します")

    async with async_playwright() as p:
        browser, context = await _new_context(p, headless=headless)

        try:
            if not await _load_cookies(context):
                await browser.close()
                return False

            page = await context.new_page()

            # ── Tweet 1 ─────────────────────────────────
            print("📝 Tweet1 を投稿中...")
            await page.goto("https://x.com/home")
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(PAGE_LOAD_MS)

            await _type_tweet(page, tweets[0], testid_index=0)
            await _click_post_button(page, testid="tweetButtonInline")
            print("✅ Tweet1 投稿完了")

            if len(tweets) < 2 or not username:
                await browser.close()
                return True

            # 投稿が X サーバーに反映されるまで少し待つ
            await page.wait_for_timeout(AFTER_POST_MS)

            # ── Tweet 1 の URL 取得 ─────────────────────
            tweet1_url = await _get_latest_tweet_url(page, username)
            if not tweet1_url:
                # CI環境では反映遅延で失敗することがある → もう一度待機してリトライ
                print("  ⚠️ Tweet1 URL取得失敗 → 5秒待機してリトライ...")
                await page.wait_for_timeout(5000)
                tweet1_url = await _get_latest_tweet_url(page, username)
            if not tweet1_url:
                print("⚠️ Tweet1 URLが取得できず、Tweet2/3をスキップ（tweet1のみ投稿済み）")
                await browser.close()
                return True  # tweet1は成功

            # ── Tweet 2 （reply to tweet1） ─────────────
            print("📝 Tweet2 を返信投稿中...")
            await _reply_to_tweet(page, tweet1_url, tweets[1])

            if len(tweets) < 3:
                await browser.close()
                return True

            # 返信が反映されるまで待ってからプロフィールを再取得
            await page.wait_for_timeout(AFTER_POST_MS)
            tweet2_url = await _get_latest_tweet_url(page, username)
            if not tweet2_url:
                print("  ⚠️ Tweet2 URL取得失敗 → 5秒待機してリトライ...")
                await page.wait_for_timeout(5000)
                tweet2_url = await _get_latest_tweet_url(page, username)
            if not tweet2_url:
                print("⚠️ Tweet2 URLが取得できず、Tweet3をスキップ（tweet1/2のみ投稿済み）")
                await browser.close()
                return True  # tweet1/2は成功

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

async def post_tweet(text: str, headless: bool = True) -> str | None:
    """保存済みCookieを使って単体ツイートを投稿する（後方互換）

    Returns:
        tweet ID文字列（例: "1234567890"）、失敗時は None
    """
    username = os.environ.get("X_USERNAME", "")

    async with async_playwright() as p:
        browser, context = await _new_context(p, headless=headless)

        if not await _load_cookies(context):
            await browser.close()
            return None

        try:
            page = await context.new_page()
            await page.goto("https://x.com/home")
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(PAGE_LOAD_MS)

            print("✏️  ツイート入力中...")
            await _type_tweet(page, text, testid_index=0)

            print("🚀 投稿ボタンをクリック...")
            await _click_post_button(page, testid="tweetButtonInline")

            print("✅ 投稿完了！")

            # tweet IDをプロフィールページから取得
            tweet_id = None
            if username:
                await page.wait_for_timeout(AFTER_POST_MS)
                tweet_url = await _get_latest_tweet_url(page, username)
                if tweet_url and "/status/" in tweet_url:
                    tweet_id = tweet_url.rstrip("/").split("/status/")[-1]
                    print(f"  tweet ID取得: {tweet_id}")

            await browser.close()
            return tweet_id or "posted"

        except Exception as e:
            print(f"❌ 投稿エラー: {e}")
            try:
                await browser.close()
            except Exception:
                pass
            return None


def post(text: str, headless: bool = True) -> str | None:
    """同期版の単体ツイート投稿関数。tweet IDを返す（失敗時はNone）"""
    try:
        return asyncio.run(post_tweet(text, headless=headless))
    except Exception as e:
        print(f"❌ 投稿エラー: {e}")
        return None


# ─────────────────────────────────────────────────────────
# 初回ログイン
# ─────────────────────────────────────────────────────────

async def login_and_save(username: str, email: str, password: str, headless: bool = False):
    """ブラウザでXにログインしてCookieを保存する"""
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
        await page.wait_for_timeout(PAGE_LOAD_MS)

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
        await page.wait_for_timeout(HEADLESS_WAIT_MS * 2)

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
            await page.wait_for_timeout(HEADLESS_WAIT_MS * 2)
        except Exception:
            pass

        # パスワード入力
        print(f"  現在のURL: {page.url}")
        print("🔑 パスワードを入力中...")
        pw_el = await page.wait_for_selector('input[name="password"]', timeout=15000)
        await pw_el.fill(password)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(HEADLESS_WAIT_MS * 4)

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


def first_login(headless: bool = False):
    """初回ログイン（.envから認証情報を読んでブラウザを起動）"""
    env_path = Path(__file__).parent.parent / ".env"
    env = {}
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()

    asyncio.run(login_and_save(
        username=env.get("X_USERNAME", ""),
        email=env.get("X_EMAIL", ""),
        password=env.get("X_PASSWORD", ""),
        headless=headless,
    ))


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
        result = post_thread_sync(
            tweets=[
                "一人暮らし始めてから、充電器の数が増えすぎた。\n\nスマホ・PC・イヤホン…気づいたら3個持ち歩いてた。\n\nGaN充電器1台に統合したら荷物が劇的に減った話。",
                "これを選んだ理由は3つ：\n✅ 純正より30%以上コンパクト\n✅ 67Wでノート・スマホを同時充電\n✅ 出張・カフェでも恥ずかしくないデザイン\n\n参考価格: ¥2,480（通常比24%OFF想定）",
                "Amazonで最安値を確認→",
            ],
            headless=False,
        )
        print(f"結果: {'成功' if result else '失敗'}")
