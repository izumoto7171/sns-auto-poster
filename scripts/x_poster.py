"""
Amazon商品 X(Twitter) 投稿スクリプト（スレッド形式・シャドウバン回避設計）

入力:  data/amazon_deals.json（product_rotator.py が毎日更新）
出力:  data/post_log.json（投稿記録）

スレッド構造（シャドウバン回避）:
  Tweet 1: ストーリー・フックのみ（リンクなし・ハッシュタグ1個以内）
  Tweet 2: 商品スペック・価格・割引率（リンクなし）
  Tweet 3: Amazonアフィリエイトリンク + #PR + アソシエイト開示

なぜスレッド形式か:
  X のリーチ評価は「本文ツイート」が主。リンクは返信に分離することで
  アルゴリズムのペナルティを回避しやすくなる。

実行:
  python3 scripts/x_poster.py             # 本番投稿
  python3 scripts/x_poster.py --dry-run   # プレビューのみ
"""

from __future__ import annotations

import os
import sys
import json
import re
import argparse
from datetime import datetime, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.notifier import notify as _discord_notify

# ─────────────────────────────────────────
# パス定義
# ─────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR     = PROJECT_ROOT / "data"
ENV_PATH     = PROJECT_ROOT / ".env"

DEALS_JSON   = DATA_DIR / "amazon_deals.json"
POST_LOG     = DATA_DIR / "post_log.json"

# ─────────────────────────────────────────
# 環境変数読み込み
# ─────────────────────────────────────────
if ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

# 景表法対応（2023年10月施行ガイドライン準拠）
DISCLOSURE = "#PR\n※Amazonアソシエイトに参加しています"


# ─────────────────────────────────────────
# 投稿ログ管理
# ─────────────────────────────────────────
def load_post_log() -> dict:
    if not POST_LOG.exists():
        return {"posts": []}
    try:
        return json.loads(POST_LOG.read_text(encoding="utf-8"))
    except Exception:
        return {"posts": []}


def save_post_log(log: dict) -> None:
    POST_LOG.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")


def get_today_posted_keywords(log: dict) -> list[str]:
    """今日すでに投稿済みのキーワード一覧を返す"""
    today = date.today().isoformat()
    return [
        p.get("search_keyword", "")
        for p in log.get("posts", [])
        if p.get("date") == today
    ]


# ─────────────────────────────────────────
# 商品選択
# ─────────────────────────────────────────
def pick_product(products: list[dict], posted_today: list[str]) -> dict | None:
    """
    未投稿の商品を1件選ぶ。
    すべて投稿済みの場合は最初の商品を返す（1日5投稿で商品を循環させる）。
    """
    for p in products:
        kw = p.get("search_keyword", p.get("title", ""))
        if kw not in posted_today:
            return p
    # 全件投稿済み → 最初の商品（日をまたいだ安全弁）
    return products[0] if products else None


# ─────────────────────────────────────────
# Gemini によるスレッド生成
# ─────────────────────────────────────────
def generate_thread(product: dict) -> dict | None:
    """
    Gemini APIでXスレッド3ツイートを生成する。

    構成（2026年Xアルゴリズム最適化）:
      Tweet1: 悩みへの共感 + 商品名を自然に盛り込む（リンクなし）
              → 「知ってる人」感でエンゲージメントを引き出す
      Tweet2: 「なぜこれを選んだか」の理由3点 + 価格（リンクなし）
              → 比較・検討ユーザーの背中を押す
      Tweet3: 誘導文 + アフィリエイトリンク + 開示（自動付加）
              → リンクをツリー末尾に置きシャドウバンを回避
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ GEMINI_API_KEY 未設定")
        return None

    title    = product.get("title", "")
    brand    = product.get("brand", "")
    price    = product.get("price", {}).get("display", "")
    disc     = product.get("discount_rate", 0)
    features = product.get("features", [])
    hook     = product.get("story_hook", "")
    why      = product.get("why_viral", "")
    problem  = product.get("user_problem", "")
    url      = product.get("amazon_url", "")

    feat_str = "\n".join(f"  ・{f}" for f in features)
    disc_str = f"（通常より約{disc}%OFF想定）" if disc else ""

    prompt = f"""Amazonアフィリエイト投稿用のXスレッド（3ツイート）を日本語で生成してください。

【商品情報】
- 商品名: {title}
- ブランド: {brand}
- 価格: {price} {disc_str}
- 特徴:
{feat_str}
- フック候補: {hook}
- バイラル理由: {why}
- 解決する悩み: {problem}

【出力形式】以下のJSON形式のみ（コードブロック不要）:
{{
  "tweet1": "...",
  "tweet2": "...",
  "tweet3": "..."
}}

【各ツイートのルール】

■ tweet1（共感 + 商品紹介 / 140〜200字）
- ユーザーの「あるある悩み」への共感から始める
  例: 「一人暮らし始めてすぐ気づいたこと〜」「仕事始めてからずっと悩んでた〜」
- 後半で商品名を自然に登場させる
  例: 「そこで使い始めたのが{brand}の〇〇で〜」「{title[:15]}に変えてから〜」
- 具体的な数字・変化を1つ入れる（「3週間で〜」「毎日30分の〜が消えた」）
- URLは絶対に含めない / ハッシュタグは0〜1個
- 改行を活用してスマホで読みやすく

■ tweet2（なぜこれなのか / 120〜160字）
- 「これを選んだ理由は3つ：」で始める
- 箇条書き3点（スペックより「体験的なメリット」を優先）
  例: ✅ ケーブル不要で出かけられる / ✅ 純正の半額以下 / ✅ 職場でも使える小ささ
- 参考価格: {price} を必ず含める
- URLは含めない

■ tweet3（誘導文 / 40字以内）
- 「Amazonで確認→」「最安値はこちら→」など誘導のみ
- URLは含めない（スクリプトが自動付加する）"""

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        resp   = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt,
        )
        raw = resp.text.strip()

        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        thread = json.loads(raw)

        # tweet3にURL + 開示文を付加（固定順序）
        body3 = thread.get("tweet3", "Amazonで確認はこちら→").strip()
        thread["tweet3"] = f"{body3}\n{url}\n{DISCLOSURE}"

        return thread

    except json.JSONDecodeError as e:
        print(f"❌ スレッドJSONパースエラー: {e}")
        return None
    except Exception as e:
        print(f"❌ Gemini APIエラー: {e}")
        return None


def build_fallback_thread(product: dict) -> dict:
    """
    Gemini不使用のフォールバックスレッドを商品データから直接組み立てる。
    クォータ超過・APIエラー時に使用。
    """
    title    = product.get("title", "")
    brand    = product.get("brand", "")
    price    = product.get("price", {}).get("display", "")
    disc     = product.get("discount_rate", 0)
    features = product.get("features", [])
    hook     = product.get("story_hook", "")
    problem  = product.get("user_problem", "")
    url      = product.get("amazon_url", "")

    disc_str  = f"（通常より約{disc}%OFF想定）" if disc else ""
    feat_lines = "\n".join(f"✅ {f}" for f in features[:3])

    tweet1 = f"{hook}\n\n{problem}で悩んでいたとき、{brand}の製品を試してみたら状況が変わった。\n\n詳しくは↓に"
    tweet2 = f"これを選んだ理由は3つ：\n{feat_lines}\n\n参考価格: {price} {disc_str}"
    tweet3 = f"Amazonで詳細を確認→\n{url}\n{DISCLOSURE}"

    return {"tweet1": tweet1, "tweet2": tweet2, "tweet3": tweet3}


# ─────────────────────────────────────────
# バリデーション
# ─────────────────────────────────────────
def _x_units(text: str) -> int:
    """X の文字単位数を計算（URL=23単位、CJK=2単位、その他=1単位）"""
    normalized = re.sub(r'https?://\S+', '\x00' * 23, text)
    count = 0
    for ch in normalized:
        cp = ord(ch)
        # CJK統合漢字・ハングル・全角など
        if (0x1100 <= cp <= 0x115F or 0x2E80 <= cp <= 0x9FFF or
                0xAC00 <= cp <= 0xD7FF or 0xFF00 <= cp <= 0xFF60 or
                0xFFE0 <= cp <= 0xFFE6):
            count += 2
        else:
            count += 1
    return count


def validate_thread(thread: dict) -> list[str]:
    """スレッドのコンプライアンスチェック。問題があればメッセージを返す。"""
    warnings = []

    t1 = thread.get("tweet1", "")
    if "http" in t1 or "amzn" in t1:
        warnings.append("❌ tweet1にリンクが含まれています（シャドウバンリスク）")

    t3 = thread.get("tweet3", "")
    if "http" not in t3:
        warnings.append("❌ tweet3にリンクがありません（収益ゼロリスク）")
    if "#PR" not in t3:
        warnings.append("❌ tweet3に#PRがありません（景表法違反リスク）")

    for key in ("tweet1", "tweet2", "tweet3"):
        units = _x_units(thread.get(key, ""))
        if units > 280:
            warnings.append(f"❌ {key}が280単位超（{units}単位）")

    return warnings


# ─────────────────────────────────────────
# X 投稿（tweepy → twikit フォールバック）
# ─────────────────────────────────────────
def _load_twikit_cookies() -> str | None:
    """X_COOKIES 環境変数または x_cookies.json のパスを返す"""
    cookies_path = DATA_DIR.parent / "x_automation" / "x_cookies.json"

    env_cookies = os.getenv("X_COOKIES", "")
    if env_cookies and not cookies_path.exists():
        cookies_path.write_text(env_cookies, encoding="utf-8")
        print("  X_COOKIES 環境変数からCookieを復元")

    return str(cookies_path) if cookies_path.exists() else None


def post_thread(thread: dict) -> bool:
    """
    スレッド（3ツイート返信チェーン）を投稿する。
    tweepy → twikit → x_automation.x_poster（ブラウザ含む既存実装）の順でフォールバック。
    """
    tweet1 = thread.get("tweet1", "")
    tweet2 = thread.get("tweet2", "")
    tweet3 = thread.get("tweet3", "")

    # ── tweepy（公式API） ──────────────────
    try:
        import tweepy

        api_key      = os.getenv("X_API_KEY")
        api_secret   = os.getenv("X_API_SECRET")
        token        = os.getenv("X_ACCESS_TOKEN")
        token_secret = os.getenv("X_ACCESS_TOKEN_SECRET")

        if all([api_key, api_secret, token, token_secret]):
            client = tweepy.Client(
                consumer_key        = api_key,
                consumer_secret     = api_secret,
                access_token        = token,
                access_token_secret = token_secret,
            )
            r1    = client.create_tweet(text=tweet1)
            t1_id = r1.data["id"]
            print(f"  ✅ Tweet1(tweepy) (id: {t1_id})")

            r2    = client.create_tweet(text=tweet2, in_reply_to_tweet_id=t1_id)
            t2_id = r2.data["id"]
            print(f"  ✅ Tweet2(tweepy) (id: {t2_id})")

            r3    = client.create_tweet(text=tweet3, in_reply_to_tweet_id=t2_id)
            t3_id = r3.data["id"]
            print(f"  ✅ Tweet3(tweepy) (id: {t3_id})")
            return True

    except Exception as e:
        print(f"  ⚠️ tweepy失敗: {e}")
        print("  → twikit にフォールバック...")

    # ── twikit（Cookie認証） ──────────────
    try:
        from twikit import Client

        cookies_path = _load_twikit_cookies()
        if not cookies_path:
            print("  ❌ x_cookies.json が見つかりません（X_COOKIES 未設定）")
        else:
            c = Client("ja")
            c.load_cookies(cookies_path)

            t1       = c.create_tweet(text=tweet1)
            reply_id = str(t1.id)
            print(f"  ✅ Tweet1(twikit) (id: {t1.id})")

            try:
                t2       = c.create_tweet(text=tweet2, reply_to=reply_id)
                reply_id = str(t2.id)
                print(f"  ✅ Tweet2(twikit) (id: {t2.id})")
                t3 = c.create_tweet(text=tweet3, reply_to=reply_id)
                print(f"  ✅ Tweet3(twikit) (id: {t3.id})")
            except Exception as e2:
                print(f"  ⚠️ Tweet2/3エラー（Tweet1は投稿済み）: {e2}")

            return True

    except Exception as e:
        print(f"  ⚠️ twikit失敗: {e}")
        print("  → x_automation.x_poster にフォールバック...")

    # ── x_automation/x_poster.py（既存実装・ブラウザ含む） ──
    try:
        x_auto_dir = PROJECT_ROOT / "x_automation"
        sys.path.insert(0, str(x_auto_dir))
        from x_poster import post_amazon_thread  # type: ignore

        return post_amazon_thread(thread)

    except Exception as e:
        print(f"  ❌ x_automation.x_poster も失敗: {e}")
        return False


# ─────────────────────────────────────────
# メイン
# ─────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Amazon商品 X投稿スクリプト")
    parser.add_argument("--dry-run", action="store_true", help="プレビューのみ（投稿しない）")
    args = parser.parse_args()

    # 商品読み込み
    if not DEALS_JSON.exists():
        print("❌ data/amazon_deals.json が見つかりません。先に product_rotator.py を実行してください。")
        sys.exit(1)

    products = json.loads(DEALS_JSON.read_text(encoding="utf-8"))
    if not products:
        print("❌ amazon_deals.json が空です。")
        sys.exit(1)

    # 投稿済み商品を除いて選択
    log          = load_post_log()
    posted_today = get_today_posted_keywords(log)
    product      = pick_product(products, posted_today)

    if not product:
        print("❌ 投稿できる商品がありません。")
        sys.exit(1)

    price = product.get("price", {}).get("display", "")
    disc  = product.get("discount_rate", 0)
    print(f"\n🛍️  選択商品: {product.get('title', '')}")
    print(f"   価格: {price}" + (f"  ({disc}%OFF想定)" if disc else ""))
    print(f"   URL: {product.get('amazon_url', '')}")

    # スレッド生成（Gemini失敗時はフォールバックで継続）
    print(f"\n🤖 スレッド生成中（Gemini）...")
    thread = generate_thread(product)
    if not thread:
        print("⚠️  Gemini生成失敗 → フォールバックテンプレートで投稿")
        _discord_notify(
            "scripts/x_poster.py",
            "Gemini停止中：テンプレートで代用します",
            f"商品: {product.get('title', '')[:80]}",
        )
        thread = build_fallback_thread(product)

    # バリデーション
    warnings = validate_thread(thread)
    for w in warnings:
        print(w)
    if any(w.startswith("❌") for w in warnings):
        print("❌ バリデーションエラーのため投稿を中止します")
        sys.exit(1)

    # プレビュー
    print(f"\n{'─' * 60}")
    print("📝 投稿内容プレビュー")
    print(f"{'─' * 60}")
    for key in ("tweet1", "tweet2", "tweet3"):
        units = _x_units(thread[key])
        print(f"\n── {key}（{units}文字単位）──")
        print(thread[key])

    if args.dry_run:
        print(f"\n🔍 dry-run モード: 投稿をスキップ")
        return

    # X投稿
    print(f"\n🚀 X にスレッド投稿中...")
    success = post_thread(thread)

    if success:
        # 投稿ログに記録
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        log["posts"].append({
            "date":           date.today().isoformat(),
            "posted_at":      datetime.now().isoformat(),
            "title":          product.get("title", ""),
            "search_keyword": product.get("search_keyword", ""),
            "amazon_url":     product.get("amazon_url", ""),
            "tweet1_preview": thread["tweet1"][:80],
        })
        save_post_log(log)
        print("✅ 投稿完了・ログ記録済み")
    else:
        _discord_notify(
            "scripts/x_poster.py",
            "X投稿：全手段が失敗（投稿スキップ）",
            f"商品: {product.get('title', '')[:80]} / tweepy/twikit/x_automation すべて失敗",
        )
        print("❌ 投稿失敗")
        sys.exit(1)


if __name__ == "__main__":
    main()
