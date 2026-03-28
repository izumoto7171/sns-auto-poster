"""
note 自動投稿スクリプト
Playwrightでnote.comにログインして記事を投稿
"""
import os
import sys
import json
import asyncio
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).parent))
from note_article_generator import generate_article, preview_article

COOKIES_FILE = Path(__file__).parent / "note_cookies.json"
LOG_FILE     = Path(__file__).parent / "note_post_log.json"


# ─────────────────────────────────────────
# .env読み込み
# ─────────────────────────────────────────
def load_env():
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
    # GitHub Actions: 環境変数 NOTE_COOKIES があればファイルに書き出す
    env_cookies = os.environ.get("NOTE_COOKIES", "")
    if env_cookies and not COOKIES_FILE.exists():
        try:
            with open(COOKIES_FILE, "w") as f:
                f.write(env_cookies)
            print(f"✅ NOTE_COOKIES環境変数からCookieを復元（{len(env_cookies)}文字）")
        except Exception as e:
            print(f"⚠️ Cookie書き出しエラー: {e}")


# ─────────────────────────────────────────
# Cookie取得（Chromeから）
# ─────────────────────────────────────────
def fetch_note_cookies():
    """ChromeからNote.comのCookieを取得して保存"""
    try:
        import rookiepy
        cookies = rookiepy.chrome(domains=["note.com"])
        pw_cookies = [{
            "name":     c.get("name", ""),
            "value":    c.get("value", ""),
            "domain":   c.get("domain", ".note.com"),
            "path":     c.get("path", "/"),
            "secure":   bool(c.get("secure", False)),
            "httpOnly": bool(c.get("http_only", False)),
        } for c in cookies]

        with open(COOKIES_FILE, "w") as f:
            json.dump(pw_cookies, f, ensure_ascii=False, indent=2)
        print(f"✅ note Cookie保存完了（{len(pw_cookies)}件）")
        return True
    except Exception as e:
        print(f"⚠️ Cookie取得失敗: {e}")
        return False


# ─────────────────────────────────────────
# note投稿
# ─────────────────────────────────────────
async def post_article_async(title: str, body: str, headless: bool = True) -> bool:
    """noteに記事を投稿"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()

        # Cookie読み込み
        if COOKIES_FILE.exists():
            with open(COOKIES_FILE) as f:
                cookies = json.load(f)
            await context.add_cookies(cookies)
        else:
            print("⚠️ noteのCookieなし → fetch_note_cookies()を先に実行してください")
            await browser.close()
            return False

        page = await context.new_page()

        # note投稿ページを開く（editor.note.comを直接使用）
        print("🌐 note投稿ページを開いています...")
        await page.goto("https://editor.note.com/new", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(1000)

        # /new → /notes/xxx/edit/ へのリダイレクト完了を待つ
        print("   ページ読み込み待機中...")
        try:
            await page.wait_for_url("**/notes/**/edit/**", timeout=15000)
        except Exception:
            pass
        await page.wait_for_timeout(1500)

        # textareaが完全に描画されるまで待つ
        try:
            await page.wait_for_selector("textarea", timeout=15000)
        except Exception:
            pass
        await page.wait_for_timeout(500)

        # ログインチェック
        if "login" in page.url or "signup" in page.url:
            print("⚠️ ログインが必要です。fetch_note_cookies()を実行してください")
            await browser.close()
            return False

        print(f"   現在のURL: {page.url}")

        # ① タイトル入力
        print("✏️  タイトル入力中...")
        try:
            title_box = await page.wait_for_selector("textarea", timeout=10000)
            await title_box.click()
            await title_box.fill(title)
            await page.wait_for_timeout(500)
            print(f"   タイトル: {title}")
        except Exception as e:
            print(f"⚠️ タイトル入力エラー: {e}")
            await page.screenshot(path=str(Path(__file__).parent / "note_debug.png"))
            await browser.close()
            return False

        # ② 本文入力
        print("📝 本文入力中...")
        try:
            body_box = await page.wait_for_selector(".ProseMirror", timeout=10000)
            await body_box.click()
            await page.wait_for_timeout(300)
            await page.evaluate(f"""
                (() => {{
                    const el = document.querySelector('.ProseMirror');
                    if (el) {{
                        el.focus();
                        document.execCommand('insertText', false, {json.dumps(body)});
                    }}
                }})()
            """)
            await page.wait_for_timeout(1000)
            print("   本文入力完了")
        except Exception as e:
            print(f"⚠️ 本文入力エラー: {e}")

        # ③ 下書き保存（サーバーにタイトル・本文を確定させてからクロップを行う）
        print("💾 下書き保存中...")
        try:
            draft_btn = await page.wait_for_selector('button:has-text("下書き保存")', timeout=5000)
            await draft_btn.click()
            await page.wait_for_timeout(2000)
            print("   下書き保存完了")
        except Exception as e:
            print(f"   ⚠️ 下書き保存スキップ（{e}）")

        # ④ ヘッダー画像を「記事にあう画像を選ぶ」で設定
        print("🖼️  ヘッダー画像を選択中...")
        try:
            add_image_btn = await page.wait_for_selector(
                'button[aria-label="画像を追加"]',
                timeout=5000
            )
            await add_image_btn.click()
            await page.wait_for_timeout(1000)

            suggest_btn = await page.wait_for_selector(
                'button:has-text("記事にあう画像を選ぶ")',
                timeout=5000
            )
            await suggest_btn.click()
            await page.wait_for_timeout(4000)

            first_fig = await page.wait_for_selector('figure', timeout=8000)
            await first_fig.click()
            await page.wait_for_timeout(2000)

            insert_btn = await page.wait_for_selector(
                'button:has-text("この画像を挿入")',
                timeout=5000
            )
            await insert_btn.click()
            await page.wait_for_timeout(2000)

            # クロップモーダルの「保存」をJSでクリック
            try:
                await page.wait_for_selector('.CropModal__overlay', timeout=5000)
                clicked = await page.evaluate("""
                    (() => {
                        const modal = document.querySelector('.CropModal__overlay');
                        if (!modal) return false;
                        const btns = Array.from(modal.querySelectorAll('button'));
                        const saveBtn = btns.find(b => b.textContent.trim() === '保存');
                        if (saveBtn) { saveBtn.click(); return true; }
                        return false;
                    })()
                """)
                await page.wait_for_timeout(2000)
                if clicked:
                    print("   クロップ確定完了")
            except Exception:
                pass

            print("   ヘッダー画像設定完了")

            # クロップ後にReact stateがリセットされるため、ページをリロードして復元
            print("   ページリロードして状態を復元中...")
            current_url = page.url
            await page.goto(current_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_selector("textarea", timeout=20000)
            await page.wait_for_timeout(3000)
            print("   リロード完了")

        except Exception as e:
            print(f"   ⚠️ 画像選択スキップ（{e}）")

        # 公開に進むボタン
        print("🚀 公開ボタンをクリック...")
        try:
            publish_btn = await page.wait_for_selector(
                'button:has-text("公開に進む"), button:has-text("公開"), button:has-text("投稿")',
                timeout=8000
            )
            await publish_btn.click()
            await page.wait_for_timeout(2000)

            # 公開確認ダイアログ
            confirm_btn = await page.wait_for_selector(
                'button:has-text("公開する"), button:has-text("投稿する"), button:has-text("note投稿")',
                timeout=8000
            )
            await confirm_btn.click()
            await page.wait_for_timeout(3000)

            print("✅ 記事投稿完了！")
            url = page.url
            print(f"   URL: {url}")
            await browser.close()
            return True

        except Exception as e:
            print(f"⚠️ 公開ボタンエラー: {e}")
            await page.screenshot(path=str(Path(__file__).parent / "note_debug.png"))
            print("   デバッグ画像: note_debug.png")
            await browser.close()
            return False


def post_article(title: str, body: str, headless: bool = True) -> bool:
    return asyncio.run(post_article_async(title, body, headless))


# ─────────────────────────────────────────
# ログ管理
# ─────────────────────────────────────────
def save_log(article: dict, success: bool):
    log = []
    if LOG_FILE.exists():
        with open(LOG_FILE) as f:
            log = json.load(f)
    log.append({
        "datetime": datetime.now().isoformat(),
        "title":    article["title"],
        "theme":    article["label"],
        "chars":    article["chars"],
        "success":  success,
    })
    with open(LOG_FILE, "w") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def show_log():
    if not LOG_FILE.exists():
        print("ログなし")
        return
    with open(LOG_FILE) as f:
        log = json.load(f)
    print(f"\n📊 note投稿ログ（{len(log)}件）")
    print("─" * 50)
    for entry in reversed(log[-10:]):
        dt = datetime.fromisoformat(entry["datetime"])
        st = "✅" if entry["success"] else "❌"
        print(f"{st} {dt.strftime('%m/%d %H:%M')} [{entry['theme']}] {entry['title'][:25]}...")


# ─────────────────────────────────────────
# メイン
# ─────────────────────────────────────────
if __name__ == "__main__":
    load_env()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "preview"

    if cmd == "cookies":
        # ChromeからCookieを取得
        fetch_note_cookies()

    elif cmd == "preview":
        # 記事を生成してプレビュー（投稿はしない）
        article = generate_article()
        preview_article(article)

        # 下書きとして保存
        out_dir = Path(__file__).parent / "drafts"
        out_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = out_dir / f"article_{ts}.md"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(f"# {article['title']}\n\n{article['body']}")
        print(f"\n💾 下書き保存: {out_path}")

    elif cmd == "post":
        # 記事生成 → noteに投稿
        article = generate_article()
        preview_article(article)
        print("\n📤 noteに投稿します...")
        # CI環境（GitHub Actions）では自動的にheadless=True
        is_ci = os.getenv("CI", "false").lower() == "true"
        success = post_article(article["title"], article["body"], headless=is_ci)
        save_log(article, success)

    elif cmd == "log":
        show_log()
