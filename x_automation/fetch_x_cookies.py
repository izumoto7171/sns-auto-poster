"""
ChromeのX(Twitter)セッションCookieをtwikit形式で保存する
"""
import json
from pathlib import Path

COOKIES_FILE = Path(__file__).parent / "x_cookies.json"

try:
    import rookiepy
    cookies = rookiepy.chrome(domains=["twitter.com", "x.com"])
    # twikit互換形式に変換
    twikit_cookies = {c["name"]: c["value"] for c in cookies}
    with open(COOKIES_FILE, "w") as f:
        json.dump(twikit_cookies, f, ensure_ascii=False, indent=2)
    print(f"✅ X Cookie保存完了（{len(twikit_cookies)}件）: {COOKIES_FILE}")
except Exception as e:
    print(f"❌ エラー: {e}")
