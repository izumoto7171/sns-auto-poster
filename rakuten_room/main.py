"""
楽天ルーム アフィリエイト自動投稿
ペルソナ: 一人暮らし20代男性 × 女性ウケ商品ガチレビュー

実行:
  python -m rakuten_room.main          # 1商品を投稿
  python -m rakuten_room.main --count 3  # 3商品を投稿
  python -m rakuten_room.main --dry-run  # 投稿せずコンテンツのみ確認
"""

import sys
import os
import json
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def load_env():
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k, v)

load_env()

from rakuten_room.product_fetcher import fetch_products
from rakuten_room.review_generator import generate_room_review
from rakuten_room.room_poster import post_sync

LOG_PATH = os.path.join(os.path.dirname(__file__), "post_log.json")


def load_log() -> list:
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH) as f:
            return json.load(f)
    return []


def save_log(log: list):
    with open(LOG_PATH, "w") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def already_posted(product_url: str, log: list) -> bool:
    posted_urls = {entry["url"] for entry in log}
    return product_url in posted_urls


def run(count: int = 1, dry_run: bool = False):
    print(f"=== 楽天ルーム 自動投稿 開始 ({datetime.now().strftime('%Y-%m-%d %H:%M')}) ===")
    print(f"投稿数: {count}  dry-run: {dry_run}")

    log = load_log()
    products = fetch_products(count * 3)  # 重複除外のため多めに取得
    posted = 0

    for product in products:
        if posted >= count:
            break

        # 重複チェック
        if already_posted(product["url"], log):
            print(f"[main] スキップ（投稿済み）: {product['name'][:30]}")
            continue

        print(f"\n--- 商品: {product['name'][:40]} ---")
        print(f"    価格: {product['price']}円 / カテゴリ: {product['category_name']}")

        # レビュー生成
        review = generate_room_review(product)

        print(f"\n[コメント]\n{review['comment']}")
        print(f"\n[ハッシュタグ] {' '.join('#' + t for t in review['hashtags'])}")
        print(f"\n[SNSキャプション]\n{review['sns_caption']}")

        if dry_run:
            print("\n[dry-run] 投稿はスキップ")
            posted += 1
            continue

        # 楽天ルームに投稿
        success = post_sync(product, review)

        # ログ記録
        log.append({
            "url":       product["url"],
            "name":      product["name"],
            "price":     product["price"],
            "category":  product["category_name"],
            "comment":   review["comment"],
            "hashtags":  review["hashtags"],
            "success":   success,
            "posted_at": datetime.now().isoformat(),
        })
        save_log(log)

        if success:
            posted += 1
            print(f"[main] 投稿完了 ({posted}/{count})")
        else:
            print(f"[main] 投稿失敗: {product['name'][:30]}")

    print(f"\n=== 完了: {posted}/{count} 件投稿 ===")
    return posted


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count",   type=int, default=1,          help="投稿する商品数")
    parser.add_argument("--dry-run", action="store_true",           help="コンテンツ確認のみ（実際には投稿しない）")
    args = parser.parse_args()

    run(count=args.count, dry_run=args.dry_run)
