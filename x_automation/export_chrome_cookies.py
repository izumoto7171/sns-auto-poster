"""
ChromeのX(Twitter)Cookieを読み取ってJSONに保存し、GitHub Secretsを更新するスクリプト
前提: ChromeでX(x.com)にログイン済みであること
"""
import json
import sys
import subprocess
from pathlib import Path


def export_for_twikit(cookies):
    """twikit用フォーマット（辞書形式）に変換"""
    return {c.name: c.value for c in cookies}


def export_for_playwright(cookies):
    """playwright用フォーマット（リスト形式）に変換"""
    result = []
    for c in cookies:
        entry = {
            "name": c.name,
            "value": c.value,
            "domain": c.domain if c.domain else ".x.com",
            "path": c.path if c.path else "/",
            "secure": bool(c.secure),
            "httpOnly": False,
            "sameSite": "None",
        }
        if hasattr(c, 'expires') and c.expires:
            entry["expires"] = c.expires
        result.append(entry)
    return result


def main():
    try:
        import browser_cookie3
    except ImportError:
        print("❌ browser_cookie3 未インストール: pip install browser-cookie3")
        sys.exit(1)

    print("🍪 ChromeからX(Twitter)のCookieを読み取り中...")
    print("   ※Chromeを閉じるか、ほかのタブを閉じる必要はありません")

    try:
        cookies = list(browser_cookie3.chrome(domain_name=".x.com"))
        if not cookies:
            cookies = list(browser_cookie3.chrome(domain_name="x.com"))
    except Exception as e:
        print(f"❌ Chrome Cookie読み取りエラー: {e}")
        print("   → Chromeにx.comでログインしてから再実行してください")
        sys.exit(1)

    if not cookies:
        print("❌ x.comのCookieが見つかりません")
        print("   → ChromeでX(x.com)にログインしてから再実行してください")
        sys.exit(1)

    print(f"✅ {len(cookies)}個のCookieを取得")

    # 重要なCookieを確認
    important = {c.name: c.value[:20] + "..." for c in cookies if c.name in ("auth_token", "ct0", "guest_id")}
    print(f"   auth_token: {'あり' if 'auth_token' in important else 'なし ⚠️'}")
    print(f"   ct0: {'あり' if 'ct0' in important else 'なし ⚠️'}")

    if "auth_token" not in important:
        print("⚠️ auth_tokenが見つかりません。ChromeでXにログインしているか確認してください")

    # twikit用
    twikit_data = export_for_twikit(cookies)
    twikit_path = Path(__file__).parent / "x_cookies.json"
    with open(twikit_path, "w") as f:
        json.dump(twikit_data, f, indent=2)
    print(f"\n✅ twikit用Cookie保存: {twikit_path}")

    # playwright用
    playwright_data = export_for_playwright(cookies)
    playwright_path = Path(__file__).parent / "x_browser_cookies.json"
    with open(playwright_path, "w") as f:
        json.dump(playwright_data, f, indent=2)
    print(f"✅ playwright用Cookie保存: {playwright_path}")

    # GitHub Secrets更新
    print("\n📤 GitHub Secretsを更新中...")
    try:
        twikit_json = json.dumps(twikit_data)
        result = subprocess.run(
            ["/usr/local/bin/gh", "secret", "set", "X_COOKIES", "--body", twikit_json],
            capture_output=True, text=True, cwd=str(Path(__file__).parent.parent)
        )
        if result.returncode == 0:
            print("✅ X_COOKIES シークレット更新完了")
        else:
            print(f"❌ X_COOKIES 更新失敗: {result.stderr}")
    except Exception as e:
        print(f"❌ gh コマンドエラー: {e}")

    try:
        playwright_json = json.dumps(playwright_data)
        result = subprocess.run(
            ["/usr/local/bin/gh", "secret", "set", "X_BROWSER_COOKIES", "--body", playwright_json],
            capture_output=True, text=True, cwd=str(Path(__file__).parent.parent)
        )
        if result.returncode == 0:
            print("✅ X_BROWSER_COOKIES シークレット更新完了")
        else:
            print(f"❌ X_BROWSER_COOKIES 更新失敗: {result.stderr}")
    except Exception as e:
        print(f"❌ gh コマンドエラー: {e}")

    print("\n✅ 完了！次回のGitHub Actions実行でXへの投稿が可能になります。")


if __name__ == "__main__":
    main()
