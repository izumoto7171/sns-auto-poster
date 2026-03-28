"""
はてなブログ 自動投稿スクリプト
Playwright + Chrome Cookie で投稿（Googleログイン対応）
"""
import os
import sys
import json
import asyncio
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from hatena_article_generator import generate_article, preview_article

COOKIES_FILE = Path(__file__).parent / "hatena_cookies.json"
LOG_FILE     = Path(__file__).parent / "hatena_post_log.json"

HATENA_ID  = "pi-natu-butter"
BLOG_ID    = "smart-earn-life.hateblo.jp"
EDIT_URL   = f"https://blog.hatena.ne.jp/{HATENA_ID}/{BLOG_ID}/edit"


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
    # GitHub Actions: 環境変数 HATENA_COOKIES があればファイルに書き出す
    env_cookies = os.environ.get("HATENA_COOKIES", "")
    if env_cookies and not COOKIES_FILE.exists():
        try:
            with open(COOKIES_FILE, "w") as f:
                f.write(env_cookies)
            print(f"✅ HATENA_COOKIES環境変数からCookieを復元（{len(env_cookies)}文字）")
        except Exception as e:
            print(f"⚠️ Cookie書き出しエラー: {e}")


# ─────────────────────────────────────────
# Cookie取得（Chromeから）
# ─────────────────────────────────────────
def fetch_hatena_cookies():
    """ChromeからHatena関連のCookieを取得して保存"""
    try:
        import rookiepy
        cookies = rookiepy.chrome(domains=["hatena.ne.jp", "blog.hatena.ne.jp"])
        pw_cookies = [{
            "name":     c.get("name", ""),
            "value":    c.get("value", ""),
            "domain":   c.get("domain", ".hatena.ne.jp"),
            "path":     c.get("path", "/"),
            "secure":   bool(c.get("secure", False)),
            "httpOnly": bool(c.get("http_only", False)),
        } for c in cookies]

        with open(COOKIES_FILE, "w") as f:
            json.dump(pw_cookies, f, ensure_ascii=False, indent=2)
        print(f"✅ はてなCookie保存完了（{len(pw_cookies)}件）")
        return True
    except Exception as e:
        print(f"⚠️  Cookie取得失敗: {e}")
        return False


# ─────────────────────────────────────────
# Markdown → はてな記法変換
# ─────────────────────────────────────────
import re

def markdown_to_html(text: str) -> str:
    """Markdownをはてなブログ用HTMLに変換"""
    lines = text.split("\n")
    result = []
    in_ul = False

    for line in lines:
        if line.startswith("## "):
            if in_ul: result.append("</ul>"); in_ul = False
            result.append(f'<h2>{line[3:]}</h2>')
        elif line.startswith("### "):
            if in_ul: result.append("</ul>"); in_ul = False
            result.append(f'<h3>{line[4:]}</h3>')
        elif line.startswith("- "):
            if not in_ul: result.append("<ul>"); in_ul = True
            item = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line[2:])
            result.append(f"  <li>{item}</li>")
        elif re.match(r'^\d+\. ', line):
            if in_ul: result.append("</ul>"); in_ul = False
            item = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', re.sub(r'^\d+\. ', '', line))
            result.append(f"<p>{item}</p>")
        elif line.strip() == "---":
            if in_ul: result.append("</ul>"); in_ul = False
            result.append('<hr />')
        elif line.strip() == "":
            if in_ul: result.append("</ul>"); in_ul = False
            result.append("")
        else:
            if in_ul: result.append("</ul>"); in_ul = False
            line = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
            result.append(f"<p>{line}</p>")

    if in_ul:
        result.append("</ul>")
    return "\n".join(result)


# ─────────────────────────────────────────
# はてなブログに投稿（Playwright）
# ─────────────────────────────────────────
async def post_article_async(title: str, body: str, category: str = "", headless: bool = True) -> bool:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()

        # Cookie読み込み
        if COOKIES_FILE.exists():
            with open(COOKIES_FILE) as f:
                cookies = json.load(f)
            await context.add_cookies(cookies)
        else:
            print("⚠️  はてなのCookieなし → python hatena_poster.py cookies を先に実行")
            await browser.close()
            return False

        page = await context.new_page()

        # 記事編集ページを開く
        print("🌐 はてなブログ編集ページを開いています...")
        await page.goto(EDIT_URL)
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(3000)

        # ログインチェック
        if "login" in page.url or "sign_in" in page.url:
            print("⚠️  ログインが必要です。cookies コマンドを実行してください")
            await browser.close()
            return False

        print(f"   現在のURL: {page.url}")

        # タイトル入力
        print("✏️  タイトル入力中...")
        try:
            title_box = await page.wait_for_selector("#title", timeout=10000)
            await title_box.click()
            await title_box.fill(title)
            await page.wait_for_timeout(500)
            print(f"   タイトル: {title[:40]}")
        except Exception as e:
            print(f"⚠️  タイトル入力エラー: {e}")

        # 本文入力（ACEエディタ + textarea 両方に確実に書き込む）
        print("📝 本文入力中...")
        body_html = markdown_to_html(body)
        try:
            success = await page.evaluate(f"""
                (function() {{
                    var bodyContent = {json.dumps(body_html)};
                    var results = [];

                    // ① ACEエディタに値をセット（表示用）
                    try {{
                        var editors = document.querySelectorAll('.ace_editor');
                        if (editors.length > 0) {{
                            var aceInstance = editors[0].env && editors[0].env.editor;
                            if (aceInstance) {{
                                aceInstance.setValue(bodyContent, -1);
                                aceInstance.clearSelection();
                                results.push('ace_ok');
                            }}
                        }}
                    }} catch(e1) {{ results.push('ace_fail:' + e1.message); }}

                    // ② #body textarea（実際に送信される）に直接セット
                    var textarea = document.querySelector('#body');
                    if (textarea) {{
                        // React/VueのバインディングをバイパスしてDOM値を直接変更
                        var nativeSetter = Object.getOwnPropertyDescriptor(
                            window.HTMLTextAreaElement.prototype, 'value'
                        ).set;
                        nativeSetter.call(textarea, bodyContent);
                        textarea.dispatchEvent(new Event('input',  {{bubbles: true}}));
                        textarea.dispatchEvent(new Event('change', {{bubbles: true}}));
                        textarea.dispatchEvent(new Event('blur',   {{bubbles: true}}));
                        results.push('textarea_ok');
                    }} else {{
                        results.push('textarea_not_found');
                    }}

                    return results.join(',');
                }})()
            """)
            print(f"   本文入力完了（方式: {success}）")
            await page.wait_for_timeout(1500)

            # ③ 入力後にtextareaの値を確認
            actual_len = await page.evaluate("""
                (function() {
                    var ta = document.querySelector('#body');
                    return ta ? ta.value.length : 0;
                })()
            """)
            print(f"   textarea実際の文字数: {actual_len}文字")

        except Exception as e:
            print(f"⚠️  本文入力エラー: {e}")

        # カテゴリ設定（任意）
        if category:
            try:
                cat_box = await page.query_selector("#editor-sidebar-category_Input")
                if cat_box:
                    await cat_box.fill(category)
                    await page.keyboard.press("Enter")
                    await page.wait_for_timeout(500)
                    print(f"   カテゴリ: {category}")
            except Exception:
                pass

        # 投稿ボタンをクリック
        print("🚀 投稿ボタンをクリック...")
        try:
            publish_btn = await page.wait_for_selector("#submit-button", timeout=5000)
            await publish_btn.click()
            await page.wait_for_timeout(4000)

            current_url = page.url
            print(f"✅ はてなブログ投稿完了！")
            print(f"   URL: {current_url}")
            await browser.close()
            return True

        except Exception as e:
            print(f"⚠️  投稿ボタンエラー: {e}")
            await page.screenshot(path=str(Path(__file__).parent / "hatena_debug.png"))
            print("   デバッグ画像: hatena_debug.png")
            await browser.close()
            return False

        await browser.close()
        return True


def post_article(title: str, body: str, category: str = "", headless: bool = True) -> bool:
    return asyncio.run(post_article_async(title, body, category, headless))


# ─────────────────────────────────────────
# ログ管理
# ─────────────────────────────────────────
def save_log(article: dict, success: bool, url: str = ""):
    log = []
    if LOG_FILE.exists():
        with open(LOG_FILE) as f:
            log = json.load(f)
    log.append({
        "datetime": datetime.now().isoformat(),
        "title":    article["title"],
        "keyword":  article["keyword"],
        "category": article["category"],
        "chars":    article["chars"],
        "success":  success,
        "url":      url,
    })
    with open(LOG_FILE, "w") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def show_log(n: int = 10):
    if not LOG_FILE.exists():
        print("ログなし")
        return
    with open(LOG_FILE) as f:
        log = json.load(f)
    print(f"\n📊 はてなブログ投稿ログ（直近{n}件）")
    print("─" * 55)
    for entry in reversed(log[-n:]):
        dt = datetime.fromisoformat(entry["datetime"])
        st = "✅" if entry["success"] else "❌"
        print(f"{st} {dt.strftime('%m/%d %H:%M')} [{entry['category']}] {entry['title'][:35]}")
        if entry.get("url"):
            print(f"   → {entry['url']}")


# ─────────────────────────────────────────
# メイン
# ─────────────────────────────────────────
if __name__ == "__main__":
    load_env()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "preview"

    if cmd == "cookies":
        fetch_hatena_cookies()

    elif cmd == "preview":
        kw = sys.argv[2] if len(sys.argv) > 2 else None
        article = generate_article(force_keyword=kw)
        preview_article(article)
        out_dir = Path(__file__).parent / "drafts"
        out_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = out_dir / f"hatena_{ts}.md"
        with open(fname, "w", encoding="utf-8") as f:
            f.write(f"# {article['title']}\n\n")
            f.write(f"**キーワード**: {article['keyword']}\n\n")
            f.write(article["body"])
        print(f"\n💾 下書き保存: {fname}")

    elif cmd == "test":
        # ドライラン
        kw = sys.argv[2] if len(sys.argv) > 2 else None
        article = generate_article(force_keyword=kw)
        print(f"\n📝 [DRY RUN] はてなブログ投稿予定")
        print(f"{'─'*50}")
        print(f"タイトル : {article['title']}")
        print(f"キーワード: {article['keyword']}")
        print(f"文字数   : {article['chars']}文字")
        print(f"{'─'*50}")
        save_log(article, True)

    elif cmd == "post":
        # 実際に投稿（ヘッドレス）
        kw = sys.argv[2] if len(sys.argv) > 2 else None
        article = generate_article(force_keyword=kw)
        preview_article(article)
        print("\n📤 はてなブログに投稿します...")
        success = post_article(article["title"], article["body"], article["category"], headless=True)
        save_log(article, success)

    elif cmd == "post-visible":
        # ブラウザを表示して投稿
        kw = sys.argv[2] if len(sys.argv) > 2 else None
        article = generate_article(force_keyword=kw)
        preview_article(article)
        is_ci = os.getenv("CI", "false").lower() == "true"
        print("\n📤 はてなブログに投稿します...")
        success = post_article(article["title"], article["body"], article["category"], headless=is_ci)
        save_log(article, success)

    elif cmd == "log":
        show_log()

    else:
        print("使い方:")
        print("  python hatena_poster.py cookies        # Cookieを取得（初回のみ）")
        print("  python hatena_poster.py preview [kw]   # 記事プレビュー・下書き保存")
        print("  python hatena_poster.py test [kw]      # ドライラン")
        print("  python hatena_poster.py post [kw]      # 投稿（ヘッドレス）")
        print("  python hatena_poster.py post-visible [kw]  # 投稿（ブラウザ表示）")
        print("  python hatena_poster.py log            # 投稿ログ")
