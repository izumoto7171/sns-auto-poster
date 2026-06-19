"""
A8.net 高単価案件 自動提携申請スクリプト（CI対応・headless）

program_portfolio.json から status="candidate" の案件をヘッドレスPlaywrightで
A8.netにログイン → プログラム検索 → 提携申請を自動実行する。

【前提条件】
- A8_MEDIA_ID / A8_PASSWORD が環境変数に設定されていること
- Playwrightのchromiumがインストール済みであること

【実行】
  python3 money_agent/a8_auto_apply.py           # 自動申請（最大5件）
  python3 money_agent/a8_auto_apply.py --dry-run # 対象リスト表示のみ
  python3 money_agent/a8_auto_apply.py --count 3 # 最大3件

【高単価ジャンル自動候補追加】
  --discover オプションで、program_portfolioに未登録の高単価ジャンルを
  A8.netから自動検索し、candidate として追加する。
"""
import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
PORTFOLIO_PATH = Path(__file__).parent / "data" / "program_portfolio.json"

A8_PUB_BASE = "https://pub.a8.net"
A8_LOGIN_URL = f"{A8_PUB_BASE}/a8v2/media/loginAction.do"
A8_SEARCH_URL = f"{A8_PUB_BASE}/a8v2/media/programListAction.do"

HIGH_VALUE_GENRES = [
    {"query": "プログラミングスクール", "min_reward": 8000, "category": "high_value"},
    {"query": "FX 口座開設", "min_reward": 5000, "category": "investment_savings"},
    {"query": "転職エージェント", "min_reward": 5000, "category": "high_value"},
    {"query": "英会話 オンライン", "min_reward": 3000, "category": "high_value"},
    {"query": "証券 口座開設", "min_reward": 5000, "category": "investment_savings"},
    {"query": "クレジットカード", "min_reward": 3000, "category": "savings_lifestyle"},
    {"query": "電力会社 乗り換え", "min_reward": 2000, "category": "savings_lifestyle"},
    {"query": "クラウド会計", "min_reward": 1500, "category": "dx_tools"},
]


def load_env():
    env_path = ROOT_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def load_portfolio() -> dict:
    return json.loads(PORTFOLIO_PATH.read_text(encoding="utf-8"))


def save_portfolio(data: dict):
    PORTFOLIO_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def get_candidates(portfolio: dict) -> list:
    return [p for p in portfolio.get("programs", []) if p.get("status") == "candidate"]


def get_existing_ids(portfolio: dict) -> set:
    return {p["id"] for p in portfolio.get("programs", [])}


async def login(page) -> bool:
    """A8.netにログイン"""
    media_id = os.getenv("A8_MEDIA_ID", "")
    password = os.getenv("A8_PASSWORD", "")
    if not media_id or not password:
        print("[A8] A8_MEDIA_ID / A8_PASSWORD が未設定")
        return False

    try:
        await page.goto(A8_LOGIN_URL, timeout=20000)
        await page.fill('input[name="login"]', media_id)
        await page.fill('input[name="passwd"]', password)
        await page.click('input[type="submit"], button[type="submit"]')
        await page.wait_for_load_state("domcontentloaded", timeout=15000)

        logged_in = await page.locator("text=ログアウト").count() > 0
        if logged_in:
            print("[A8] ログイン成功")
            return True
        else:
            print("[A8] ログイン失敗（ログアウトリンクが見つからない）")
            return False
    except Exception as e:
        print(f"[A8] ログインエラー: {e}")
        return False


async def apply_program(page, program: dict) -> dict:
    """1件のプログラムに提携申請する"""
    name = program.get("name", "")
    result = {"name": name, "status": "skipped", "error": ""}

    try:
        search_url = f"{A8_SEARCH_URL}?act=search&keyword={name}"
        await page.goto(search_url, timeout=20000)
        await page.wait_for_load_state("domcontentloaded", timeout=10000)

        # 提携申請ボタンを探す
        apply_buttons = page.locator(
            'a:has-text("提携申請"), input[value*="提携申請"], button:has-text("提携申請")'
        )
        count = await apply_buttons.count()

        if count == 0:
            # 既に提携済みか、見つからない
            already = await page.locator('text=提携中').count()
            if already > 0:
                result["status"] = "already_partnered"
                print(f"  [{name}] 既に提携済み")
                return result
            result["status"] = "not_found"
            result["error"] = "申請ボタンが見つからない"
            print(f"  [{name}] プログラムが見つからない / 申請ボタンなし")
            return result

        # 最初の申請ボタンをクリック
        await apply_buttons.first.click()
        await page.wait_for_load_state("domcontentloaded", timeout=15000)

        # 確認画面の送信ボタンを押す（あれば）
        confirm_buttons = page.locator(
            'input[value*="申請"], button:has-text("申請する"), input[type="submit"]'
        )
        if await confirm_buttons.count() > 0:
            await confirm_buttons.first.click()
            await page.wait_for_load_state("domcontentloaded", timeout=15000)

        result["status"] = "applied"
        print(f"  [{name}] 提携申請完了")

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        print(f"  [{name}] エラー: {e}")

    return result


async def discover_high_value_programs(page, portfolio: dict) -> list:
    """A8.netで高単価プログラムを検索し、未登録のものをcandidateとして返す"""
    existing_names = {p.get("name", "").lower() for p in portfolio.get("programs", [])}
    new_candidates = []

    for genre in HIGH_VALUE_GENRES:
        query = genre["query"]
        print(f"\n[検索] {query} (最低報酬: {genre['min_reward']}円)")

        try:
            search_url = f"{A8_SEARCH_URL}?act=search&keyword={query}&sortType=epc"
            await page.goto(search_url, timeout=20000)
            await page.wait_for_load_state("domcontentloaded", timeout=10000)

            # プログラム一覧から名前と報酬を抽出
            programs = page.locator('.programList, .program-item, tr.program')
            prog_count = await programs.count()

            if prog_count == 0:
                # フォールバック: テーブル行から探す
                rows = page.locator('table tr')
                prog_count = await rows.count()

            print(f"  {prog_count}件のプログラムを検出")

            # 最大3件ずつ候補追加
            added = 0
            for i in range(min(prog_count, 10)):
                try:
                    row = programs.nth(i) if await programs.count() > 0 else page.locator('table tr').nth(i)
                    text = await row.text_content()
                    if not text:
                        continue

                    # プログラム名の簡易抽出（最初の意味のある文字列）
                    lines = [l.strip() for l in text.split('\n') if l.strip() and len(l.strip()) > 3]
                    if not lines:
                        continue
                    prog_name = lines[0][:50]

                    if prog_name.lower() in existing_names:
                        continue

                    prog_id = f"auto_{query.replace(' ', '_')}_{i}"
                    new_candidates.append({
                        "id": prog_id,
                        "name": prog_name,
                        "status": "candidate",
                        "category": genre["category"],
                        "source": "auto_discover",
                        "discovered_at": time.strftime("%Y-%m-%d"),
                    })
                    existing_names.add(prog_name.lower())
                    added += 1
                    if added >= 3:
                        break
                except Exception:
                    continue

            time.sleep(2)  # レートリミット

        except Exception as e:
            print(f"  検索エラー: {e}")

    return new_candidates


async def main(args):
    load_env()
    portfolio = load_portfolio()
    candidates = get_candidates(portfolio)

    if args.dry_run:
        print(f"\n=== candidate 案件 ({len(candidates)}件) ===")
        for p in candidates:
            print(f"  - {p['name']} (id: {p['id']})")
        return

    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
        )
        page = await context.new_page()

        if not await login(page):
            print("[A8] ログイン失敗。終了。")
            await browser.close()
            return

        # 高単価プログラム自動発見
        if args.discover:
            print("\n=== 高単価プログラム自動検索 ===")
            new_progs = await discover_high_value_programs(page, portfolio)
            if new_progs:
                portfolio["programs"].extend(new_progs)
                save_portfolio(portfolio)
                print(f"\n{len(new_progs)}件の新規candidateを追加")
                candidates = get_candidates(portfolio)

        # 提携申請
        if not candidates:
            print("\n申請対象の candidate がありません")
            await browser.close()
            return

        max_count = args.count
        results = []
        applied = 0

        print(f"\n=== 自動提携申請 開始 (最大{max_count}件) ===")
        for program in candidates[:max_count]:
            result = await apply_program(page, program)
            results.append(result)

            if result["status"] == "applied":
                applied += 1
                # ポートフォリオのステータスを更新
                for p in portfolio["programs"]:
                    if p["id"] == program["id"]:
                        p["status"] = "applied"
                        p["applied_at"] = time.strftime("%Y-%m-%d")
                        break

            time.sleep(3)  # レートリミット

        save_portfolio(portfolio)
        await browser.close()

    print(f"\n=== 結果: 申請={applied} / 対象={len(results)} ===")
    for r in results:
        print(f"  {r['name']}: {r['status']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A8.net 自動提携申請")
    parser.add_argument("--dry-run", action="store_true", help="対象リスト表示のみ")
    parser.add_argument("--count", type=int, default=5, help="最大申請件数")
    parser.add_argument("--discover", action="store_true", help="高単価プログラム自動検索も実行")
    args = parser.parse_args()
    asyncio.run(main(args))
