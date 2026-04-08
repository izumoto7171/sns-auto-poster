"""
12:05 Anker ケーブルホルダー BENEFIT スレッド投稿スクリプト
A/Bテスト ID: B0BDCFM671_202604061013（benefit側）

実行方法:
  python3 x_automation/post_benefit_1205.py          # 即時投稿
  python3 x_automation/post_benefit_1205.py --dry-run # プレビューのみ
"""
import sys
import json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from generate_amazon_thread import record_ab_result, enforce_disclosure, validate_thread
from twikit import Client

# ─────────────────────────────────────────
# スレッド本文
# ─────────────────────────────────────────
AB_ID   = "B0BDCFM671_202604061013"
VARIANT = "benefit"

TWEET1 = """デスクの配線、ぐちゃぐちゃのまま2年放置してた。

正直、こんなに変わるとは思わなかった。

Ankerのこれ1つ置いただけで、デスクが別物になった。"""

TWEET2 = """■ Anker マグネットケーブルホルダー 6-in-1
・強力マグネットでデスクや壁に貼り付け
・6本のケーブルを同時にホールド
・粘着テープ不要・跡が残らない

価格: ¥1,990（15%OFF）
今がチャンスかも。"""

TWEET3 = enforce_disclosure(
    "詳細はこちら→ https://www.amazon.co.jp/dp/B0BDCFM671?tag=smartearn22-22",
    amazon_url="https://www.amazon.co.jp/dp/B0BDCFM671?tag=smartearn22-22"
)

THREAD = {"tweet1": TWEET1, "tweet2": TWEET2, "tweet3": TWEET3}

# ─────────────────────────────────────────
# 画像プロンプト（DALL-E / MJ 用）
# ─────────────────────────────────────────
IMAGE_PROMPT = """A split-image comparison photo. LEFT side (labeled 'Before'): \
messy desk with tangled cables everywhere, multiple charging cables in a chaotic pile, \
stressful and cluttered workspace, dim lighting. \
RIGHT side (labeled 'After'): clean minimalist desk setup, Anker magnetic cable holder \
organizing cables neatly on white desk surface, satisfying tidy workspace, soft natural light. \
High quality product lifestyle photography. \
Photorealistic, 4K, commercial product photography style. \
with a subtle dark semi-transparent banner at the bottom-right corner \
containing white Japanese text '詳細はツリーをチェック ↓'"""

LOG_FILE = Path(__file__).parent / "post_log.json"


def load_log():
    if LOG_FILE.exists():
        with open(LOG_FILE) as f:
            return json.load(f)
    return []


def save_log(log):
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=4)


def post_thread(dry_run: bool = False):
    # コンプライアンスチェック
    issues = validate_thread(THREAD)
    if issues:
        print("コンプライアンスエラー（投稿中止）:")
        for w in issues:
            print(f"  {w}")
        return False

    print("=== 12:05 BENEFIT スレッド ===")
    print(f"[Tweet1 - {len(TWEET1)}文字]")
    print(TWEET1)
    print(f"\n[Tweet2 - {len(TWEET2)}文字]")
    print(TWEET2)
    print(f"\n[Tweet3 - {len(TWEET3)}文字]")
    print(TWEET3)
    print(f"\n[画像プロンプト（DALL-E）]")
    print(IMAGE_PROMPT[:200] + "...")
    print()

    if dry_run:
        print("[DRY RUN] 投稿はスキップ")
        return True

    # twikit で投稿
    client = Client('ja')
    cookies_path = Path(__file__).parent / "x_cookies.json"
    client.load_cookies(str(cookies_path))

    print("Tweet1 投稿中...")
    t1 = client.create_tweet(TWEET1)
    print(f"  → ID: {t1.id}")

    print("Tweet2 投稿中（リプライ）...")
    t2 = client.create_tweet(TWEET2, reply_to=t1.id)
    print(f"  → ID: {t2.id}")

    print("Tweet3 投稿中（リプライ）...")
    t3 = client.create_tweet(TWEET3, reply_to=t2.id)
    print(f"  → ID: {t3.id}")

    thread_url = f"https://x.com/dt_alj/status/{t1.id}"
    print(f"\nスレッド完成: {thread_url}")

    # ログ記録
    log = load_log()
    log.append({
        "datetime":   datetime.now().isoformat(),
        "type":       "amazon_thread",
        "label":      "配線整理 BENEFIT",
        "ab_id":      AB_ID,
        "variant":    VARIANT,
        "tweet1_id":  t1.id,
        "tweet2_id":  t2.id,
        "tweet3_id":  t3.id,
        "thread_url": thread_url,
        "chars":      len(TWEET1),
        "success":    True,
        "mode":       "live",
    })
    save_log(log)
    print("post_log.json に記録済み")
    return True


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    success = post_thread(dry_run=dry_run)
    sys.exit(0 if success else 1)
