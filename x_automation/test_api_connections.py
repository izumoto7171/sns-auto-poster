"""
API接続テストスクリプト
Amazon PA-API / X API / Gemini API の疎通確認

使い方:
  python3.11 x_automation/test_api_connections.py
  python3.11 x_automation/test_api_connections.py --api amazon
  python3.11 x_automation/test_api_connections.py --api x
  python3.11 x_automation/test_api_connections.py --api gemini
"""

import os
import sys
import json
import argparse
from datetime import datetime

# .env 読み込み
env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


# ─────────────────────────────────────────
# 必要ライブラリ一覧（インストール確認用）
# ─────────────────────────────────────────
REQUIRED_LIBS = {
    "amazon_paapi":  "python-amazon-paapi",   # Amazon PA-API ラッパー
    "tweepy":        "tweepy",                 # X API v2 公式
    "twikit":        "twikit",                 # X 非公式・Cookieベース
    "google.genai":  "google-genai",           # Gemini API
    "requests":      "requests",               # HTTP汎用
    "playwright":    "playwright",             # ブラウザ自動化
    "dotenv":        "python-dotenv",          # .env読み込み
    "atproto":       "atproto",               # Bluesky
}


def check_libraries():
    """インストール済みライブラリをチェック"""
    print("\n" + "=" * 55)
    print("📦 ライブラリ確認")
    print("=" * 55)

    missing = []
    for module, package in REQUIRED_LIBS.items():
        try:
            __import__(module)
            print(f"  ✅ {package}")
        except ImportError:
            print(f"  ❌ {package}  → pip install {package}")
            missing.append(package)

    if missing:
        print(f"\n⚠️  未インストール: {len(missing)}件")
        print(f"   pip install {' '.join(missing)}")
    else:
        print("\n✅ 全ライブラリOK")

    return len(missing) == 0


# ─────────────────────────────────────────
# Amazon PA-API テスト
# ─────────────────────────────────────────
def test_amazon_api():
    """Amazon PA-APIへの接続テスト（ガジェットカテゴリで検索）"""
    print("\n" + "=" * 55)
    print("🛒 Amazon PA-API 接続テスト")
    print("=" * 55)

    access_key   = os.getenv("AMAZON_ACCESS_KEY")
    secret_key   = os.getenv("AMAZON_SECRET_KEY")
    associate_tag = os.getenv("AMAZON_ASSOCIATE_TAG", "smartearn22-22")

    # 環境変数チェック
    print(f"  AMAZON_ACCESS_KEY   : {'✅ 設定済み' if access_key else '❌ 未設定'}")
    print(f"  AMAZON_SECRET_KEY   : {'✅ 設定済み' if secret_key else '❌ 未設定'}")
    print(f"  AMAZON_ASSOCIATE_TAG: ✅ {associate_tag}")

    if not access_key or not secret_key:
        print("\n⚠️  PA-APIキー未設定。.envに以下を追加してください:")
        print("  AMAZON_ACCESS_KEY=your_access_key")
        print("  AMAZON_SECRET_KEY=your_secret_key")
        print("  AMAZON_ASSOCIATE_TAG=smartearn22-22")
        print("\n  取得先: https://affiliate.amazon.co.jp/ → ツール → Product Advertising API")
        return False

    try:
        from amazon_paapi import AmazonApi

        amazon = AmazonApi(
            access_key,
            secret_key,
            associate_tag,
            "JP",
        )

        # テスト検索（ガジェット1件）
        result = amazon.search_items(
            keywords="ガジェット",
            search_index="Electronics",
            item_count=1,
            resources=["ItemInfo.Title", "Offers.Listings.Price", "Images.Primary.Medium"],
        )

        if result and result.items:
            item = result.items[0]
            title = item.item_info.title.display_value if item.item_info else "不明"
            print(f"\n✅ PA-API接続成功！")
            print(f"   テスト商品: {title[:50]}...")
            return True
        else:
            print("⚠️  検索結果が空でした")
            return False

    except ImportError:
        print("\n❌ python-amazon-paapi 未インストール")
        print("   pip install python-amazon-paapi")
        return False
    except Exception as e:
        print(f"\n❌ PA-APIエラー: {e}")
        return False


# ─────────────────────────────────────────
# X API テスト
# ─────────────────────────────────────────
def test_x_api():
    """X API（tweepy）への接続テスト"""
    print("\n" + "=" * 55)
    print("🐦 X API 接続テスト")
    print("=" * 55)

    api_key      = os.getenv("X_API_KEY")
    api_secret   = os.getenv("X_API_SECRET")
    access_token = os.getenv("X_ACCESS_TOKEN")
    access_secret = os.getenv("X_ACCESS_TOKEN_SECRET")
    bearer_token = os.getenv("X_BEARER_TOKEN")

    print(f"  X_API_KEY          : {'✅ 設定済み' if api_key else '❌ 未設定'}")
    print(f"  X_API_SECRET       : {'✅ 設定済み' if api_secret else '❌ 未設定'}")
    print(f"  X_ACCESS_TOKEN     : {'✅ 設定済み' if access_token else '❌ 未設定'}")
    print(f"  X_ACCESS_TOKEN_SECRET: {'✅ 設定済み' if access_secret else '❌ 未設定'}")
    print(f"  X_BEARER_TOKEN     : {'✅ 設定済み' if bearer_token else '⚠️ 未設定（読み取りのみ必要）'}")

    if not all([api_key, api_secret, access_token, access_secret]):
        print("\n⚠️  X APIキー未設定。.envに追加してください:")
        print("  X_API_KEY=...")
        print("  X_API_SECRET=...")
        print("  X_ACCESS_TOKEN=...")
        print("  X_ACCESS_TOKEN_SECRET=...")
        print("\n  取得先: https://developer.x.com/en/portal/dashboard")
        print("  ※ Free Tierでも投稿(write)は可能")
        return False

    try:
        import tweepy

        client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret,
        )
        # 自分のアカウント情報を取得（書き込みなし）
        me = client.get_me()
        if me and me.data:
            print(f"\n✅ X API接続成功！")
            print(f"   アカウント: @{me.data.username} (ID: {me.data.id})")
            return True
        else:
            print("⚠️  ユーザー情報取得失敗")
            return False

    except ImportError:
        print("\n❌ tweepy 未インストール: pip install tweepy")
        return False
    except Exception as e:
        print(f"\n❌ X APIエラー: {e}")
        return False


# ─────────────────────────────────────────
# twikit（Cookie）テスト
# ─────────────────────────────────────────
def test_twikit():
    """twikit（Cookie認証）の接続テスト"""
    print("\n" + "=" * 55)
    print("🍪 twikit (Cookie認証) テスト")
    print("=" * 55)

    cookies_path = os.path.join(os.path.dirname(__file__), "x_cookies.json")
    print(f"  x_cookies.json: {'✅ 存在' if os.path.exists(cookies_path) else '❌ なし'}")

    if not os.path.exists(cookies_path):
        print("\n⚠️  Cookieファイルがありません")
        print("   python3.11 x_automation/fetch_x_cookies.py を実行してください")
        return False

    try:
        import asyncio
        from twikit import Client

        async def _check():
            client = Client("ja")
            client.load_cookies(cookies_path)
            # タイムラインを1件だけ取得（投稿なし）
            user = await client.get_user_by_screen_name(os.getenv("X_USERNAME", ""))
            return user

        user = asyncio.run(_check())
        if user:
            print(f"\n✅ twikit接続成功！")
            print(f"   アカウント: @{user.screen_name}")
            return True
        return False

    except ImportError:
        print("\n❌ twikit 未インストール: pip install twikit")
        return False
    except Exception as e:
        print(f"\n❌ twikitエラー: {e}")
        return False


# ─────────────────────────────────────────
# Gemini API テスト
# ─────────────────────────────────────────
def test_gemini_api():
    """Gemini APIへの接続テスト"""
    print("\n" + "=" * 55)
    print("🤖 Gemini API 接続テスト")
    print("=" * 55)

    api_key = os.getenv("GEMINI_API_KEY")
    print(f"  GEMINI_API_KEY: {'✅ 設定済み' if api_key else '❌ 未設定'}")

    if not api_key:
        print("\n⚠️  .envに GEMINI_API_KEY=... を追加してください")
        return False

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model="gemini-1.5-flash",
            contents="「テスト成功」とだけ返してください",
        )
        print(f"\n✅ Gemini API接続成功！")
        print(f"   レスポンス: {resp.text.strip()[:30]}")
        return True

    except ImportError:
        print("\n❌ google-genai 未インストール: pip install google-genai")
        return False
    except Exception as e:
        print(f"\n❌ Gemini APIエラー: {e}")
        return False


# ─────────────────────────────────────────
# メイン
# ─────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="API接続テスト")
    parser.add_argument("--api", choices=["all", "amazon", "x", "twikit", "gemini"],
                        default="all", help="テスト対象（デフォルト: all）")
    args = parser.parse_args()

    print(f"\n🔍 API接続テスト開始 ({datetime.now().strftime('%Y/%m/%d %H:%M')})")

    results = {}

    if args.api in ("all",):
        results["ライブラリ"] = check_libraries()

    if args.api in ("all", "amazon"):
        results["Amazon PA-API"] = test_amazon_api()

    if args.api in ("all", "x"):
        results["X API (tweepy)"] = test_x_api()

    if args.api in ("all", "twikit"):
        results["twikit"] = test_twikit()

    if args.api in ("all", "gemini"):
        results["Gemini API"] = test_gemini_api()

    # サマリー
    print("\n" + "=" * 55)
    print("📊 テスト結果サマリー")
    print("=" * 55)
    for name, ok in results.items():
        status = "✅" if ok else "❌"
        print(f"  {status} {name}")

    ok_count = sum(1 for v in results.values() if v)
    print(f"\n  {ok_count}/{len(results)} 項目OK")

    if not results.get("Amazon PA-API"):
        print("\n💡 PA-APIなしでも fetch_amazon_deals.py は Gemini fallback で動作します")
    if not results.get("X API (tweepy)") and not results.get("twikit"):
        print("💡 X APIなしでも twikit (Cookie) があれば投稿できます")


if __name__ == "__main__":
    main()
