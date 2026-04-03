"""
ディストリビューターエージェント
生成記事をはてな→note→X→Blueskyへ順次配信する
"""
import sys
import os
import random
import json
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
ROOT_DIR = BASE_DIR.parent


def _generate_sns_texts(article: dict) -> dict:
    """SNS投稿文を生成（X / Bluesky）"""
    keyword = article.get("keyword", "")
    title = article.get("title", "")

    x_options = [
        f"✅ 新記事\n\n「{title[:35]}...」\n\n{keyword}について基礎から実践まで解説しました。\nアフィリエイトリンクもまとめてます👇\n\nプロフィールからチェック📩",
        f"💡 {keyword}で収益を上げる方法を記事にまとめました\n\n初心者でも再現できる具体的な手順付き✅\n\n詳しくはブログへ→\nLINE登録で限定情報も配信中📲",
        f"【新記事】{title[:28]}...\n\n✅ 具体的な手順あり\n✅ おすすめサービス紹介\n✅ よくある失敗も解説\n\n読んで損なし！",
    ]
    bsky_options = [
        f"新記事を書きました📝\n\n{keyword}についてまとめました。気になる方はぜひ。\nアフィリエイトリンクも参考にしてください🙌",
        f"「{keyword}」の記事です。\n\n初心者向けに分かりやすく解説したつもりです。\nよかったら読んでみてください😊",
    ]

    return {
        "x": random.choice(x_options),
        "bluesky": random.choice(bsky_options),
    }


def run(article: dict, dry_run: bool = False) -> dict:
    """
    ディストリビューター実行
    Returns: 配信結果
    """
    slot = article.get("slot", 0)
    keyword = article.get("keyword", "")
    print(f"\n  📡 [Distributor-{slot}] 「{keyword}」配信開始...")

    results = {"hatena": False, "note": False, "x": False, "bluesky": False}

    if dry_run:
        print(f"  🔍 [Distributor-{slot}] dry-run — 投稿スキップ")
        return results

    # === はてなブログ投稿 ===
    try:
        sys.path.insert(0, str(ROOT_DIR))
        from hatena_automation.hatena_poster import post_to_hatena
        hatena_result = post_to_hatena(article)
        results["hatena"] = bool(hatena_result)
        status = "✅" if results["hatena"] else "❌"
        print(f"  {status} [Distributor-{slot}] はてな投稿")
    except Exception as e:
        print(f"  ❌ [Distributor-{slot}] はてな失敗: {e}")

    # === note投稿 ===
    try:
        from note_automation.note_poster import post_to_note
        note_result = post_to_note(article)
        results["note"] = bool(note_result)
        status = "✅" if results["note"] else "❌"
        print(f"  {status} [Distributor-{slot}] note投稿")
    except Exception as e:
        print(f"  ❌ [Distributor-{slot}] note失敗: {e}")

    # === X / Bluesky 投稿 ===
    sns_texts = _generate_sns_texts(article)

    try:
        from x_automation.x_poster import post_with_tweepy
        post_with_tweepy(sns_texts["x"])
        results["x"] = True
        print(f"  ✅ [Distributor-{slot}] X投稿")
    except Exception as e:
        print(f"  ❌ [Distributor-{slot}] X失敗: {e}")

    try:
        from bluesky_automation.bsky_poster import post_to_bluesky
        post_to_bluesky(sns_texts["bluesky"])
        results["bluesky"] = True
        print(f"  ✅ [Distributor-{slot}] Bluesky投稿")
    except Exception as e:
        print(f"  ❌ [Distributor-{slot}] Bluesky失敗: {e}")

    success_count = sum(results.values())
    print(f"  📊 [Distributor-{slot}] 配信完了: {success_count}/4プラットフォーム")
    return results
