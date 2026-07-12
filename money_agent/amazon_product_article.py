"""
Amazonアフィリエイト — 商品ランキング記事生成 → はてなブログ投稿

フロー:
  1. crawlers.crawler_amazon (PA-API → Gemini → 静的データ) で商品を取得
  2. Geminiで「〇〇おすすめランキング」記事を生成
  3. 商品URLをAmazonアフィリエイトリンク（tag付き）に変換して挿入
  4. はてなブログに投稿

実行:
  python3 money_agent/amazon_product_article.py            # 1記事生成・投稿
  python3 money_agent/amazon_product_article.py --dry-run  # ファイル出力のみ
  python3 money_agent/amazon_product_article.py --count 3  # 3記事
"""

import os
import sys
import json
import random
import argparse
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_env():
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k, v)


_load_env()

from money_agent.hatena_atomapi import post as hatena_post
from crawlers.crawler_amazon import fetch_deals

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# ============================================================
# 記事化するカテゴリ（crawler_amazon.CATEGORIES のキーに対応）
# ============================================================
ARTICLE_CATEGORIES = [
    {
        "category_key": "gadget",
        "name": "ガジェット・家電",
        "title_format": "【{year}年版】Amazonで買うべきガジェットおすすめランキングTOP10",
        "tags": ["ガジェット", "Amazon", "一人暮らし"],
    },
    {
        "category_key": "kitchen",
        "name": "キッチン家電",
        "title_format": "【{year}年版】一人暮らしにおすすめキッチン家電ランキングTOP10｜Amazon",
        "tags": ["キッチン家電", "Amazon", "一人暮らし"],
    },
    {
        "category_key": "cleaning",
        "name": "掃除・生活家電",
        "title_format": "【{year}年版】コスパ最強の掃除家電ランキングTOP10｜Amazonおすすめ",
        "tags": ["掃除家電", "Amazon", "コスパ"],
    },
    {
        "category_key": "daily_goods",
        "name": "日用品・消耗品",
        "title_format": "【{year}年版】一人暮らしの日用品おすすめTOP10｜Amazonで揃える節約術",
        "tags": ["日用品", "Amazon", "節約"],
    },
    {
        "category_key": "audio",
        "name": "オーディオ",
        "title_format": "【{year}年版】コスパで選ぶワイヤレスイヤホンおすすめランキングTOP10｜Amazon",
        "tags": ["オーディオ", "Amazon", "コスパ"],
    },
    {
        "category_key": "smart_home",
        "name": "スマートホーム",
        "title_format": "【{year}年版】一人暮らしにおすすめスマートホーム家電TOP10｜Amazon",
        "tags": ["スマートホーム", "Amazon", "一人暮らし"],
    },
    {
        "category_key": "pc",
        "name": "PC・デスク環境",
        "title_format": "【{year}年版】デスク環境を快適にするPC周辺機器おすすめTOP10｜Amazon",
        "tags": ["PC周辺機器", "Amazon", "デスク環境"],
    },
]

DRAFTS_DIR = Path(__file__).parent / "hatena_drafts"
LOG_PATH = Path(__file__).parent / "data" / "amazon_article_log.json"


# ============================================================
# Geminiで記事生成
# ============================================================
def generate_ranking_article(category: dict, products: list) -> str:
    """商品リストからSEOランキング記事を生成する。gemini_client経由でリトライ付き。"""
    if not GEMINI_API_KEY:
        print("[gemini] GEMINI_API_KEY 未設定 → モック記事を返す")
        return _mock_article(category, products)

    year = datetime.now().year

    products_text = "\n".join(
        f"{i+1}. 【{p.get('title', '')}】 "
        f"{p.get('price', {}).get('display', '価格不明')}"
        + (f"（{p['discount_rate']}%OFF）" if p.get("discount_rate") else "")
        + f" / {p.get('brand', '')} / {', '.join(p.get('features', [])[:2])}"
        for i, p in enumerate(products[:10])
    )

    prompt = f"""あなたはSEOライターです。以下の商品リストを使って、はてなブログ向けのランキング記事を作成してください。

【カテゴリ】{category['name']}
【ターゲットキーワード】Amazon {category['name']} おすすめ
【商品リスト（Amazon 人気・セール順）】
{products_text}

【記事要件】
- 文字数: 2000〜3000字
- 形式: Markdown（## ### #### を使う）
- 構成:
  1. リード文（検索意図に応える導入 200字程度）
  2. 選び方のポイント（3〜4点、各100字程度）
  3. おすすめランキングTOP10（各商品に100〜150字の説明）
     - 各商品に「[商品名](PRODUCT_URL_PLACEHOLDER_0)」〜「[商品名](PRODUCT_URL_PLACEHOLDER_9)」形式でリンクプレースホルダーを順番に入れる（0始まり）
     - 価格・割引率・特徴を必ず含める
  4. まとめ（150字程度）
- SEO: タイトルキーワードを自然に入れる
- Amazonアフィリエイトの宣伝っぽさを出さず、読者目線のレビューとして書く
- 年号は{year}年を使う
- Markdownのみ出力（前置き・後置きは不要）
"""

    try:
        from money_agent.gemini_client import generate as gemini_generate
        article = gemini_generate(prompt, use_cache=False, temperature=0.7)
        if not article:
            print("[gemini] 全リトライ消耗 → モック記事にフォールバック")
            return _mock_article(category, products)
        if article.startswith("```"):
            lines = article.split("\n")
            article = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
        print(f"[gemini] 記事生成完了 ({len(article)}字)")
        return article
    except Exception as e:
        print(f"[gemini] エラー: {e}")
        return _mock_article(category, products)


def _mock_article(category: dict, products: list) -> str:
    lines = [f"## {category['name']}おすすめランキングTOP{len(products)}", ""]
    for i, p in enumerate(products[:5], 1):
        price = p.get("price", {}).get("display", "価格不明")
        lines += [f"### {i}位: {p.get('title', '')}", f"価格: {price}", ""]
    lines.append("## まとめ\nAmazonで人気の商品をご紹介しました。")
    return "\n".join(lines)


# ============================================================
# 商品URLをプレースホルダーから実URLに置換
# ============================================================
def inject_product_urls(article: str, products: list) -> str:
    """Geminiが出力したプレースホルダーを実際のAmazonアフィリエイトURLに置換する。"""
    for i, p in enumerate(products[:10]):
        placeholder = f"PRODUCT_URL_PLACEHOLDER_{i}"
        article = article.replace(placeholder, p.get("amazon_url", ""))
    return article


# ============================================================
# ログ管理
# ============================================================
def load_log() -> list:
    if LOG_PATH.exists():
        with open(LOG_PATH, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_log(log: list):
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def already_posted(category_key: str, log: list) -> bool:
    """同じカテゴリを7日以内に投稿済みかチェック"""
    cutoff = (datetime.now() - timedelta(days=7)).isoformat()
    for entry in log:
        if entry.get("category_key") == category_key and entry.get("posted_at", "") > cutoff:
            return True
    return False


# ============================================================
# メイン処理
# ============================================================
def run(count: int = 1, dry_run: bool = False):
    print(f"=== Amazonアフィリエイト記事生成 開始 ({datetime.now().strftime('%Y-%m-%d %H:%M')}) ===")
    log = load_log()
    year = datetime.now().year
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)

    categories = random.sample(ARTICLE_CATEGORIES, len(ARTICLE_CATEGORIES))
    posted = 0

    for category in categories:
        if posted >= count:
            break

        if already_posted(category["category_key"], log) and not dry_run:
            print(f"[main] スキップ（7日以内投稿済み）: {category['name']}")
            continue

        print(f"\n--- カテゴリ: {category['name']} ---")

        products = fetch_deals(category["category_key"], count=10)
        if len(products) < 3:
            print(f"[main] 商品が少なすぎてスキップ ({len(products)}件)")
            continue

        article_body = generate_ranking_article(category, products)
        article_body = inject_product_urls(article_body, products)

        title = category["title_format"].format(year=year)
        tags = category["tags"] + ["Amazonアフィリエイト", "おすすめ"]

        print(f"\n[タイトル] {title}")
        print(f"[文字数]   {len(article_body)}字")
        print(f"[タグ]     {', '.join(tags)}")

        if dry_run:
            draft_path = DRAFTS_DIR / f"amazon_{category['category_key']}_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
            with open(draft_path, "w", encoding="utf-8") as f:
                f.write(f"# {title}\n\n{article_body}")
            print(f"[dry-run] ドラフト保存: {draft_path}")
            posted += 1
            continue

        result_url = hatena_post({
            "title": title,
            "body": article_body,
            "category": tags,
            "draft": False,
        })

        log.append({
            "category_key": category["category_key"],
            "name": category["name"],
            "title": title,
            "url": result_url,
            "products": len(products),
            "posted_at": datetime.now().isoformat(),
            "success": bool(result_url),
        })
        save_log(log)

        if result_url:
            posted += 1
            print(f"[main] 投稿完了: {result_url}")
        else:
            print(f"[main] 投稿失敗（ドラフト保存済み）")

    print(f"\n=== 完了: {posted}/{count} 件 ===")
    return posted


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=1, help="生成する記事数")
    parser.add_argument("--dry-run", action="store_true", help="投稿せずドラフト保存のみ")
    args = parser.parse_args()
    run(count=args.count, dry_run=args.dry_run)
