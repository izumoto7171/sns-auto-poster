"""
人間承認フロー
各エージェントの成果物を人間が確認・承認してから公開する仕組み

【フロー】
1. Writer が記事を生成 → pending/YYYY-MM-DD_keyword.json に保存
2. GitHub の Actions サマリーで内容を確認
3. 承認: approved.json にキーワードを追加
4. 次回実行時に Distributor が approved 記事のみ投稿

【設計思想】
- ハルシネーション防止: 人間が事実確認してから公開
- 規約違反防止: 人間がASP規約を確認してから公開
- 品質管理: タイトル・内容を確認してから公開
"""
import json
import os
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent
PENDING_DIR = BASE_DIR / "pending"
APPROVED_FILE = BASE_DIR / "approved.json"
REJECTED_FILE = BASE_DIR / "rejected.json"

PENDING_DIR.mkdir(exist_ok=True)


# ── 保存 ─────────────────────────────────────────────────────

def save_pending(article: dict) -> str:
    """記事を承認待ちとして保存し、ファイルパスを返す"""
    keyword = article.get("keyword", "unknown").replace(" ", "_")
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{date_str}_{keyword}.json"
    filepath = PENDING_DIR / filename

    pending_entry = {
        **article,
        "pending_since": datetime.now().isoformat(),
        "status": "pending",
    }
    filepath.write_text(
        json.dumps(pending_entry, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(filepath)


def load_approved_keywords() -> list:
    """承認済みキーワードリストを読み込む"""
    if APPROVED_FILE.exists():
        try:
            return json.loads(APPROVED_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def load_pending_articles() -> list:
    """承認待ち記事を全件読み込む"""
    articles = []
    for f in sorted(PENDING_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            data["_filename"] = f.name
            articles.append(data)
        except Exception:
            pass
    return articles


def get_approved_pending() -> list:
    """承認待ちの中から承認済みのものを返す"""
    approved_keywords = load_approved_keywords()
    pending = load_pending_articles()
    return [p for p in pending if p.get("keyword") in approved_keywords]


def mark_as_published(filename: str):
    """投稿済みとしてマーク（pendingから削除）"""
    filepath = PENDING_DIR / filename
    if filepath.exists():
        filepath.unlink()


# ── サマリー表示（GitHub Actions の Step Summary 用）──────────

def print_approval_summary(articles: list):
    """承認が必要な記事の一覧を出力"""
    if not articles:
        print("\n📭 承認待ち記事はありません")
        return

    print("\n" + "=" * 60)
    print(f"  ⏳ 承認待ち記事: {len(articles)}件")
    print("=" * 60)
    for i, a in enumerate(articles, 1):
        title = a.get("title", "タイトルなし")[:50]
        keyword = a.get("keyword", "-")
        category = a.get("category", "-")
        char_count = a.get("char_count", 0)
        affiliate_count = a.get("affiliate_count", 0)
        since = a.get("pending_since", "")[:16]

        print(f"\n  [{i}] {title}...")
        print(f"       キーワード: {keyword} | カテゴリ: {category}")
        print(f"       文字数: {char_count} | アフィリエイト: {affiliate_count}件")
        print(f"       保存日時: {since}")

    print("\n" + "=" * 60)
    print("  📝 承認方法:")
    print("     money_agent/approved.json に キーワードを追加してコミット")
    print('     例: ["楽天証券 口座開設", "SBI証券 米国株"]')
    print("=" * 60)


# ── CLI ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"

    if cmd == "list":
        articles = load_pending_articles()
        print_approval_summary(articles)

    elif cmd == "approve":
        # python3 approval_flow.py approve "キーワード"
        keyword = sys.argv[2] if len(sys.argv) > 2 else ""
        if not keyword:
            print("使い方: python3 approval_flow.py approve 'キーワード'")
        else:
            approved = load_approved_keywords()
            if keyword not in approved:
                approved.append(keyword)
                APPROVED_FILE.write_text(
                    json.dumps(approved, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                print(f"✅ 承認: 「{keyword}」")
            else:
                print(f"既に承認済み: 「{keyword}」")

    elif cmd == "approved-list":
        approved = load_approved_keywords()
        print(f"承認済み ({len(approved)}件): {approved}")
