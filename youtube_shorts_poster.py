"""
YouTube Shorts 自動投稿パイプライン
商品動画を生成してJapanAdCheckチャンネルに投稿する

使い方:
  python3.11 youtube_shorts_poster.py                          # ローテーションで1本投稿
  python3.11 youtube_shorts_poster.py --product amazon_kindle  # 指定商品を投稿
  python3.11 youtube_shorts_poster.py --dry-run                # 動画生成のみ（投稿しない）
  python3.11 youtube_shorts_poster.py --list                   # 投稿済み一覧
"""
import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent

# .env 読み込み
env_path = BASE_DIR / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

# アップロード履歴
POSTED_LOG = BASE_DIR / "output" / "youtube_posted.json"

# 投稿する商品リスト（ローテーション順）
PRODUCT_ROTATION = [
    "amazon_kindle",      # Kindle Unlimited
    "amazon_audible",     # Audible
    "amazon_prime",       # Amazon Prime
    "rakuten_card",       # 楽天カード
    "sbi_securities",     # SBI証券
    "rakuten_securities", # 楽天証券
]


def load_posted_log() -> list:
    if POSTED_LOG.exists():
        with open(POSTED_LOG, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_posted_log(log: list):
    POSTED_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(POSTED_LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def get_next_product(log: list) -> str:
    """まだ投稿していない商品を順番に返す（全部投稿済みならリセット）"""
    posted_ids = {entry["product_id"] for entry in log}
    for pid in PRODUCT_ROTATION:
        if pid not in posted_ids:
            return pid
    # 全部投稿済み → ログをリセットして最初から
    print("全商品投稿済み。ローテーションをリセットします。")
    return PRODUCT_ROTATION[0]


def generate_video(product_id: str, product: dict) -> str:
    """affiliate_video_creator を使って動画を生成"""
    from affiliate_video_creator import create_affiliate_video, generate_youtube_description

    output_path = str(BASE_DIR / "output" / f"shorts_{product_id}.mp4")
    create_affiliate_video(product, output_path, duration=20)
    return output_path


def upload_to_youtube(video_path: str, product: dict) -> str:
    """youtube_uploader を使ってYouTube Shortsにアップロード"""
    sys.path.insert(0, str(BASE_DIR / "youtube_automation"))
    from youtube_uploader import upload_video
    from affiliate_video_creator import generate_youtube_description

    name = product["name"]
    desc = generate_youtube_description(product)

    # タイトル: 60文字以内、#Shorts必須
    title = f"【日本の神アイテム】{name} #Shorts"
    if len(title) > 60:
        title = f"{name} #Shorts"

    tags = [
        name, "日本", "ライフハック", "便利グッズ", "おすすめ",
        "Shorts", "shorts", product.get("category", "副業"),
    ]

    video_id = upload_video(
        video_path=video_path,
        title=title,
        description=desc,
        tags=tags,
        privacy="public",
        category_id="22",  # People & Blogs
    )
    return video_id


def run(product_id: str = None, dry_run: bool = False):
    sys.path.insert(0, str(BASE_DIR))
    from money_agent.keywords_db import AFFILIATE_PROGRAMS, _resolve_affiliate_url

    log = load_posted_log()

    # 商品決定
    if not product_id:
        product_id = get_next_product(log)

    product = AFFILIATE_PROGRAMS.get(product_id)
    if not product:
        print(f"商品ID '{product_id}' が見つかりません")
        print(f"使用可能: {PRODUCT_ROTATION}")
        sys.exit(1)

    product = _resolve_affiliate_url(product)
    print(f"\n商品: {product['name']} ({product_id})")

    # 動画生成
    video_path = generate_video(product_id, product)
    if not Path(video_path).exists():
        print("動画生成失敗")
        sys.exit(1)

    if dry_run:
        print(f"\n[DRY RUN] 動画生成のみ完了: {video_path}")
        return

    # YouTube アップロード
    video_id = upload_to_youtube(video_path, product)

    if video_id:
        entry = {
            "datetime": datetime.now().isoformat(),
            "product_id": product_id,
            "product_name": product["name"],
            "video_id": video_id,
            "url": f"https://www.youtube.com/shorts/{video_id}",
        }
        log.append(entry)
        save_posted_log(log)
        print(f"\n投稿完了: https://www.youtube.com/shorts/{video_id}")
    else:
        print("アップロード失敗")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="YouTube Shorts 自動投稿")
    parser.add_argument("--product", "-p", default=None, help="商品ID")
    parser.add_argument("--dry-run", action="store_true", help="動画生成のみ（投稿しない）")
    parser.add_argument("--list", action="store_true", help="投稿済み一覧を表示")
    args = parser.parse_args()

    if args.list:
        log = load_posted_log()
        if not log:
            print("投稿履歴なし")
        else:
            print(f"\n投稿済み ({len(log)}件):")
            for e in reversed(log[-10:]):
                dt = e["datetime"][:16].replace("T", " ")
                print(f"  {dt}  {e['product_name']}")
                print(f"    {e['url']}")
    else:
        run(product_id=args.product, dry_run=args.dry_run)
