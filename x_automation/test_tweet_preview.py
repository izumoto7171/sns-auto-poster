"""
投稿前プレビュースクリプト — 実際のツイート文（3本）をコンソール出力す���だけ。

使い方:
  python3 x_automation/test_tweet_preview.py
"""

import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(Path(__file__).parent))

# .env 読み込み
env_path = ROOT_DIR / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

from fetch_amazon_deals import fetch_deals
from generate_amazon_thread import generate_thread, validate_thread


def preview(count: int = 3):
    print("=" * 60)
    print("【ツイー��プレビュー】投稿前チェ���ク")
    print("=" * 60)

    products = fetch_deals("gadget", count=count)
    if not products:
        print("❌ 商品が取得できませんでした")
        sys.exit(1)

    print(f"取得商品数: {len(products)}")

    for i, product in enumerate(products[:count], 1):
        title      = product.get("title", "(タイトルなし)")
        amazon_url = product.get("amazon_url", "")
        category   = product.get("category", "")

        print(f"\n{'─' * 60}")
        print(f"【商品 {i}】{title}")
        print(f"  カテゴリ: {category}")
        print(f"  amazon_url: {amazon_url or '（空！）'}")

        if not amazon_url:
            print("  ⚠️  amazon_url が空です → tweet3 に URL が入りま���ん！")

        thread = generate_thread(product)
        issues = validate_thread(thread)

        if issues:
            print(f"\n  ❌ コ���プライアンス問題:")
            for w in issues:
                print(f"     {w}")
        else:
            print(f"\n  ✅ コンプライアンスOK")

        print(f"\n  ── Tweet1（本文）──")
        print(f"  {thread.get('tweet1', '（���）')}")
        print(f"\n  ── Tweet2（スペック）──")
        print(f"  {thread.get('tweet2', '（空）')}")
        print(f"\n  ── Tweet3（リンク）──")
        t3 = thread.get("tweet3", "（空）")
        print(f"  {t3}")

        # URLが含まれているか確認
        if "http" in t3:
            print(f"\n  ✅ URLが含まれています")
        else:
            print(f"\n  ❌ tweet3 に URL が含まれていません！アフィリエイト収益ゼロになります")

    print(f"\n{'=' * 60}")
    print("プレビュー完了")


if __name__ == "__main__":
    preview()
