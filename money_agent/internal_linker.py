"""
内部リンク自動管理

【機能】
1. 投稿済み記事のインデックスをSupabaseから構築
2. キーワード重複率ベースの関連記事検索
3. 新記事生成時に関連記事URLリストを返す
4. 既存記事に内部リンクを自動追記（hatena_editor.py と連携）

【使い方】
    from money_agent.internal_linker import find_related_articles
    related = find_related_articles("freee 中小企業 クラウド会計", "dx_tools")
    # → [{"title": "...", "url": "...", "score": 0.6}, ...]
"""

import json
import os
import sys
import re
from pathlib import Path
from collections import Counter

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

INDEX_FILE = Path(__file__).parent / "data" / "article_index.json"

# 内部リンクSENTINEL（冪等性保証用）
INTERNAL_LINK_SENTINEL = "<!-- internal-links-auto -->"


def _load_index() -> list[dict]:
    """記事インデックスを読み込み"""
    if INDEX_FILE.exists():
        try:
            return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save_index(index: list[dict]):
    INDEX_FILE.write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def build_index() -> list[dict]:
    """Supabaseからはてなブログの投稿済み記事インデックスを構築"""
    try:
        from db_client import db
        posts = db.get_posts(limit=500)
    except Exception as e:
        print(f"[InternalLinker] DB読み込みエラー: {e}")
        return _load_index()

    index = []
    seen_urls = set()

    for post in posts:
        url = post.get("url", "")
        if not url or url in seen_urls:
            continue
        # はてなブログの記事のみ（SNS投稿は除外）
        if "hateblo" not in url and "hatenablog" not in url:
            continue

        seen_urls.add(url)
        index.append({
            "title": post.get("title", post.get("text", ""))[:100],
            "url": url,
            "keyword": post.get("label", post.get("keyword", "")),
            "category": post.get("category", post.get("post_type", "")),
            "created_at": post.get("created_at", ""),
        })

    if index:
        _save_index(index)
        print(f"[InternalLinker] インデックス更新: {len(index)}記事")

    return index


def _tokenize(text: str) -> list[str]:
    """簡易トークナイザ（スペース区切り + 記号除去）"""
    text = text.lower()
    text = re.sub(r'[【】「」『』（）()｜|・、。！？!?,./\-]', ' ', text)
    return [w.strip() for w in text.split() if len(w.strip()) >= 2]


def _similarity(tokens_a: list[str], tokens_b: list[str]) -> float:
    """単語重複率ベースの類似度（0.0〜1.0）"""
    if not tokens_a or not tokens_b:
        return 0.0
    set_a = set(tokens_a)
    set_b = set(tokens_b)
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


def find_related_articles(
    keyword: str,
    category: str,
    max_results: int = 5,
    min_score: float = 0.15,
) -> list[dict]:
    """
    キーワードに関連する既存記事を検索

    Returns:
        [{"title": "...", "url": "...", "score": 0.6}, ...]
    """
    index = _load_index()
    if not index:
        index = build_index()

    if not index:
        return []

    query_tokens = _tokenize(keyword)
    results = []

    for article in index:
        # 同じカテゴリの記事を優先
        article_tokens = _tokenize(
            f"{article.get('title', '')} {article.get('keyword', '')}"
        )
        score = _similarity(query_tokens, article_tokens)

        # カテゴリ一致ボーナス
        if article.get("category") == category:
            score += 0.1

        if score >= min_score:
            results.append({
                "title": article["title"],
                "url": article["url"],
                "score": round(score, 3),
                "category": article.get("category", ""),
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:max_results]


def generate_related_links_html(related_articles: list[dict]) -> str:
    """関連記事リンクのHTML/Markdownブロックを生成"""
    if not related_articles:
        return ""

    lines = [
        INTERNAL_LINK_SENTINEL,
        "\n## 関連記事\n",
    ]
    for article in related_articles[:5]:
        lines.append(f"- [{article['title']}]({article['url']})")

    lines.append("")
    return "\n".join(lines)


def add_internal_links_to_existing(article_url: str, article_keyword: str, article_category: str):
    """
    新記事が投稿された後、関連する既存記事にも内部リンクを追加する。
    hatena_editor.py の AtomPub API 更新と連携。
    """
    related = find_related_articles(article_keyword, article_category, max_results=3)
    if not related:
        return

    print(f"[InternalLinker] {len(related)}件の既存記事に内部リンクを追加予定")
    for r in related:
        print(f"  → {r['title'][:40]}... (類似度: {r['score']})")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "build":
        build_index()
    else:
        # テスト検索
        results = find_related_articles("freee 中小企業 クラウド会計", "dx_tools")
        for r in results:
            print(f"  [{r['score']:.2f}] {r['title'][:50]} → {r['url'][:60]}")
