"""
twikitでXにログインしてCookieを生成するワンショットスクリプト
"""
import asyncio
import os
import sys
from pathlib import Path

# .env読み込み
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

COOKIES_FILE = Path(__file__).parent / "x_cookies.json"


async def main():
    from twikit import Client

    username = os.environ["X_USERNAME"]
    email    = os.environ["X_EMAIL"]
    password = os.environ["X_PASSWORD"]

    print(f"Xにログイン中: @{username}")
    client = Client("ja")
    await client.login(
        auth_info_1=username,
        auth_info_2=email,
        password=password,
    )
    client.save_cookies(str(COOKIES_FILE))
    print(f"✅ Cookie保存完了: {COOKIES_FILE}")
    print(f"   サイズ: {COOKIES_FILE.stat().st_size} bytes")


asyncio.run(main())
