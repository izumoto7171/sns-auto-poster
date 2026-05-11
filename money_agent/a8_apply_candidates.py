"""
A8.net 未提携案件（status=candidate）を1件ずつブラウザで開く補助スクリプト

【フロー】
1. program_portfolio.json から status="candidate" の案件を列挙
2. A8.net にログイン（Cookie 再利用 → 期限切れなら手動ログイン）
3. 各案件の検索ページを Playwright (headless=False) で開く
4. ユーザーが申請ボタンをクリックしたら Enter で次へ
5. 全件完了後、URL 生成リストを表示

【実行】
  python3 money_agent/a8_apply_candidates.py           # 全 candidate を順番に開く
  python3 money_agent/a8_apply_candidates.py --dry-run # URL リストのみ表示
  python3 money_agent/a8_apply_candidates.py --no-login # ログインなし・公開検索のみ
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import urllib.parse
from pathlib import Path

ROOT_DIR       = Path(__file__).parent.parent
PORTFOLIO_PATH = Path(__file__).parent / "data" / "program_portfolio.json"
COOKIES_FILE   = ROOT_DIR / "a8_cookies.json"

A8_PUB_BASE        = "https://pub.a8.net"
A8_SEARCH_PROGRAMS = f"{A8_PUB_BASE}/a8v2/media/programListAction.do"  # 未提携プログラム検索
A8_LOGIN_URL       = f"{A8_PUB_BASE}/a8v2/media/loginAction.do"


def load_env():
    env_path = ROOT_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def load_candidates() -> list[dict]:
    """portfolio.json から status=candidate の案件を返す"""
    data = json.loads(PORTFOLIO_PATH.read_text(encoding="utf-8"))
    return [p for p in data.get("programs", []) if p.get("status") == "candidate"]


def build_search_url(name: str) -> str:
    """プログラム名でA8.net 未提携プログラム検索URLを生成"""
    params = {
        "act":     "search",
        "keyword": name,
    }
    return f"{A8_SEARCH_PROGRAMS}?{urllib.parse.urlencode(params, quote_via=urllib.parse.quote)}"


def print_url_list(candidates: list[dict]) -> None:
    """候補案件のURLリストを表示（--dry-run 用）"""
    print(f"\n=== candidate 案件 URL リスト ({len(candidates)}件) ===\n")
    for i, p in enumerate(candidates, 1):
        url = build_search_url(p["name"])
        print(f"[{i:02d}] {p['name']}")
        print(f"      {url}")
        print()


async def _load_cookies(context) -> bool:
    """Cookie ファイルが存在すれば読み込む。成功=True"""
    if not COOKIES_FILE.exists():
        return False
    try:
        cookies = json.loads(COOKIES_FILE.read_text())
        await context.add_cookies(cookies)
        print("[Cookie] 保存済み Cookie を読み込みました")
        return True
    except Exception as e:
        print(f"[Cookie] 読み込み失敗: {e}")
        return False


async def _save_cookies(context) -> None:
    """現在の Cookie をファイルへ保存"""
    try:
        cookies = await context.cookies()
        COOKIES_FILE.write_text(json.dumps(cookies, ensure_ascii=False, indent=2))
        print("[Cookie] Cookie を保存しました")
    except Exception as e:
        print(f"[Cookie] 保存失敗: {e}")


async def _check_logged_in(page) -> bool:
    """ログアウトリンクが存在するかでログイン状態を確認"""
    try:
        await page.goto(A8_PUB_BASE, timeout=15000)
        return await page.locator("text=ログアウト").count() > 0
    except Exception:
        return False


async def _manual_login(page, context) -> bool:
    """
    ブラウザを開いてユーザーに手動ログインさせる。
    ログイン検知後に Cookie を保存して True を返す。
    """
    print("\n[ログイン] ブラウザでA8.netにログインしてください")
    print("  → ログイン完了後、このターミナルで Enter を押してください")

    await page.goto(A8_LOGIN_URL, timeout=20000)
    input("  ログイン完了したら Enter キーを押してください ... ")

    logged_in = await _check_logged_in(page)
    if logged_in:
        await _save_cookies(context)
        print("[ログイン] 成功")
        return True
    else:
        print("[ログイン] 確認できませんでした。スクリプトを続行します。")
        return False


async def open_candidates(candidates: list[dict], no_login: bool = False) -> None:
    """Playwright で候補案件の申請ページを1件ずつ開く"""
    from playwright.async_api import async_playwright

    total = len(candidates)
    print(f"\n=== A8.net 提携申請補助 開始 ({total}件) ===")
    print("操作方法: ブラウザで申請ボタンをクリック後、ターミナルで Enter を押すと次へ進みます")
    print("スキップ: 's' を入力して Enter")
    print("中断:     'q' を入力して Enter\n")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
        )
        page = await context.new_page()

        # ログイン処理
        if not no_login:
            cookie_loaded = await _load_cookies(context)
            if not cookie_loaded or not await _check_logged_in(page):
                await _manual_login(page, context)

        # 案件を1件ずつ開く
        for i, program in enumerate(candidates, 1):
            name = program.get("name", "")
            url  = build_search_url(name)

            print(f"\n[{i}/{total}] {name}")
            print(f"  URL: {url}")

            try:
                await page.goto(url, timeout=20000)
                await page.wait_for_load_state("domcontentloaded", timeout=10000)
            except Exception as e:
                print(f"  ページ読み込み失敗: {e}")

            cmd = input("  申請完了 → Enter / スキップ → s / 中断 → q : ").strip().lower()
            if cmd == "q":
                print("中断しました。")
                break
            elif cmd == "s":
                print(f"  [{name}] をスキップ")
                continue

        await _save_cookies(context)
        await browser.close()

    print("\n=== 完了 ===")


def main():
    load_env()

    parser = argparse.ArgumentParser(description="A8.net candidate 案件の提携申請補助")
    parser.add_argument("--dry-run",  action="store_true", help="URLリストのみ表示（ブラウザ不使用）")
    parser.add_argument("--no-login", action="store_true", help="ログインなしで公開検索ページを開く")
    args = parser.parse_args()

    candidates = load_candidates()
    if not candidates:
        print("candidate 案件が見つかりません。program_portfolio.json を確認してください。")
        return

    print(f"candidate 案件: {len(candidates)}件")
    for p in candidates:
        print(f"  - {p['name']} ({p.get('category', '')})")

    if args.dry_run:
        print_url_list(candidates)
        return

    asyncio.run(open_candidates(candidates, no_login=args.no_login))


if __name__ == "__main__":
    main()
