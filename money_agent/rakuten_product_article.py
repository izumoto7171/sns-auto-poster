"""
楽天アフィリエイト — 商品ランキング記事生成 → はてなブログ投稿

フロー:
  1. 楽天商品検索APIで人気商品を取得
  2. Geminiで「〇〇おすすめランキング」記事を生成
  3. 商品URLを楽天アフィリエイトリンクに変換して挿入
  4. はてなブログに投稿

実行:
  python3 money_agent/rakuten_product_article.py            # 1記事生成・投稿
  python3 money_agent/rakuten_product_article.py --dry-run  # ファイル出力のみ
  python3 money_agent/rakuten_product_article.py --count 3  # 3記事
"""

import os
import sys
import json
import random
import requests
import argparse
from datetime import datetime
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

# ============================================================
# 環境変数
# ============================================================
RAKUTEN_APP_ID       = os.environ.get("RAKUTEN_APP_ID", "")        # アプリケーションID (UUID)
RAKUTEN_ACCESS_KEY   = os.environ.get("RAKUTEN_ACCESS_KEY", "")    # アクセスキー (pk_...)
RAKUTEN_AFFILIATE_ID = os.environ.get("RAKUTEN_AFFILIATE_ID", "")  # アフィリエイトID
GEMINI_API_KEY       = os.environ.get("GEMINI_API_KEY", "")

RAKUTEN_SEARCH_URL = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20220601"
RAKUTEN_ORIGIN     = os.environ.get("RAKUTEN_ORIGIN", "")

# crawlers パッケージ（楽天APIキャッシュ管理）
from crawlers.crawler_rakuten import fetch_products as _fetch_products_cached

# ============================================================
# 記事化するカテゴリ（楽天ジャンルID + SEOキーワード）
# ============================================================
ARTICLE_CATEGORIES = [
    {
        "genre_id": "100804",
        "name": "キッチン用品・調理器具",
        "keyword": "キッチン おすすめ 一人暮らし 男性",
        "title_format": "【{year}年版】一人暮らし男性におすすめ{name}ランキングTOP10",
        "tags": ["キッチン", "一人暮らし", "調理器具", "楽天"],
    },
    {
        "genre_id": "215783",
        "name": "家電・生活家電",
        "keyword": "家電 一人暮らし おすすめ コスパ",
        "title_format": "【{year}年版】一人暮らしにおすすめ{name}ランキングTOP10｜コスパ重視",
        "tags": ["家電", "一人暮らし", "コスパ", "楽天"],
    },
    {
        "genre_id": "551167",
        "name": "日用品・消耗品",
        "keyword": "日用品 節約 まとめ買い 一人暮らし",
        "title_format": "【{year}年版】一人暮らしの{name}節約術｜まとめ買いおすすめTOP10",
        "tags": ["日用品", "節約", "一人暮らし", "楽天"],
    },
    {
        "genre_id": "214099",  # 旧ID 116631 は楽天API側で廃止され0件になるため更新（2026-07-15）
        "name": "インスタント・レトルト食品",
        "keyword": "インスタント レトルト 一人暮らし コスパ",
        "title_format": "【{year}年版】一人暮らし男性に人気の{name}おすすめTOP10",
        "tags": ["インスタント", "レトルト", "食費節約", "楽天"],
    },
    {
        "genre_id": "506539",  # 旧ID 400395 は楽天API側で廃止され0件になるため更新（2026-07-15）
        "name": "コーヒー・飲料",
        "keyword": "コーヒー おすすめ 一人暮らし 節約",
        "title_format": "【{year}年】コスパで選ぶ{name}おすすめランキングTOP10",
        "tags": ["コーヒー", "飲料", "節約", "楽天"],
    },
    {
        "genre_id": "100227",
        "name": "健康食品・プロテイン",
        "keyword": "プロテイン おすすめ コスパ 一人暮らし",
        "title_format": "【{year}年版】コスパ最強{name}ランキングTOP10｜一人暮らし向け",
        "tags": ["プロテイン", "健康食品", "一人暮らし", "楽天"],
    },
]

DRAFTS_DIR  = Path(__file__).parent / "hatena_drafts"
LOG_PATH    = Path(__file__).parent / "data" / "rakuten_article_log.json"


# ============================================================
# 楽天APIで商品取得（crawlers.crawler_rakuten に委譲）
# ============================================================
def fetch_rakuten_products(genre_id: str, hits: int = 10) -> list:
    """楽天市場APIで人気商品を取得する。24時間キャッシュ付き。"""
    return _fetch_products_cached(genre_id, hits=hits)


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
        f"{i+1}. 【{p['name']}】 {p['price']}円 / レビュー{p['review_count']}件({p['review_avg']}点) / {p['shop']}"
        for i, p in enumerate(products[:10])
    )

    prompt = f"""あなたはSEOライターです。以下の商品リストを使って、はてなブログ向けのランキング記事を作成してください。

【カテゴリ】{category['name']}
【ターゲットキーワード】{category['keyword']}
【商品リスト（楽天市場 人気順）】
{products_text}

【記事要件】
- 文字数: 2000〜3000字
- 形式: Markdown（## ### #### を使う）
- 構成:
  1. リード文（検索意図に応える導入 200字程度）
  2. 選び方のポイント（3〜4点、各100字程度）
  3. おすすめランキングTOP10（各商品に100〜150字の説明）
     - 各商品に「[商品名](PRODUCT_URL_PLACEHOLDER_0)」〜「[商品名](PRODUCT_URL_PLACEHOLDER_9)」形式でリンクプレースホルダーを順番に入れる（0始まり）
     - 価格・レビュー数・特徴を必ず含める
  4. まとめ（150字程度）
- SEO: タイトルキーワードを自然に入れる
- 楽天アフィリエイトの宣伝っぽさを出さず、読者目線のレビューとして書く
- 年号は{year}年を使う
- Markdownのみ出力（前置き・後置きは不要）
"""

    try:
        from money_agent.gemini_client import generate as gemini_generate
        article = gemini_generate(prompt, use_cache=False, temperature=0.7)
        if not article:
            print("[gemini] 全リトライ消耗 → モック記事にフォールバック")
            return _mock_article(category, products)
        # コードブロックで囲まれていたら除去
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
        lines += [f"### {i}位: {p['name']}", f"価格: {p['price']}円 / レビュー: {p['review_count']}件", ""]
    lines.append("## まとめ\n楽天市場で人気の商品をご紹介しました。")
    return "\n".join(lines)


# ============================================================
# 商品URLをプレースホルダーから実URLに置換
# ============================================================
def inject_product_urls(article: str, products: list) -> str:
    """Geminiが出力したプレースホルダーを実際のURLに置換する。"""
    for i, p in enumerate(products[:10]):
        placeholder = f"PRODUCT_URL_PLACEHOLDER_{i}"
        article = article.replace(placeholder, p["url"])
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


def already_posted(genre_id: str, log: list) -> bool:
    """同じジャンルを7日以内に投稿済みかチェック"""
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(days=7)).isoformat()
    for entry in log:
        if entry.get("genre_id") == genre_id and entry.get("posted_at", "") > cutoff:
            return True
    return False


# ============================================================
# メイン処理
# ============================================================
def run(count: int = 1, dry_run: bool = False):
    print(f"=== 楽天アフィリエイト記事生成 開始 ({datetime.now().strftime('%Y-%m-%d %H:%M')}) ===")
    log = load_log()
    year = datetime.now().year
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)

    # 未投稿のカテゴリをランダムな順で試す
    categories = random.sample(ARTICLE_CATEGORIES, len(ARTICLE_CATEGORIES))
    posted = 0

    for category in categories:
        if posted >= count:
            break

        if already_posted(category["genre_id"], log) and not dry_run:
            print(f"[main] スキップ（7日以内投稿済み）: {category['name']}")
            continue

        print(f"\n--- カテゴリ: {category['name']} ---")

        # 商品取得
        products = fetch_rakuten_products(category["genre_id"], hits=12)
        if len(products) < 3:
            print(f"[main] 商品が少なすぎてスキップ ({len(products)}件)")
            continue

        # 記事生成
        article_body = generate_ranking_article(category, products)
        article_body = inject_product_urls(article_body, products)

        title = category["title_format"].format(year=year, name=category["name"])
        tags  = category["tags"] + ["楽天アフィリエイト", "おすすめ"]

        print(f"\n[タイトル] {title}")
        print(f"[文字数]   {len(article_body)}字")
        print(f"[タグ]     {', '.join(tags)}")

        if dry_run:
            # ドラフトとして保存
            draft_path = DRAFTS_DIR / f"rakuten_{category['genre_id']}_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
            with open(draft_path, "w", encoding="utf-8") as f:
                f.write(f"# {title}\n\n{article_body}")
            print(f"[dry-run] ドラフト保存: {draft_path}")
            posted += 1
            continue

        # はてなブログ投稿
        result_url = hatena_post({
            "title":    title,
            "body":     article_body,
            "category": tags,
            "draft":    False,
        })

        log.append({
            "genre_id":  category["genre_id"],
            "name":      category["name"],
            "title":     title,
            "url":       result_url,
            "products":  len(products),
            "posted_at": datetime.now().isoformat(),
            "success":   bool(result_url),
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
    parser.add_argument("--count",   type=int, default=1,        help="生成する記事数")
    parser.add_argument("--dry-run", action="store_true",         help="投稿せずドラフト保存のみ")
    args = parser.parse_args()
    run(count=args.count, dry_run=args.dry_run)
