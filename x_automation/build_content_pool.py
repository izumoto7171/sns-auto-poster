"""
content_pool.json ビルダー

x_post_generator.py の TEMPLATES dict を読み込み、
全テンプレートを組み立ててJSONプールとして書き出す。

使い方:
  python3 build_content_pool.py            # content_pool.json を生成・上書き
  python3 build_content_pool.py --stats    # 現在のプール統計を表示（生成しない）
"""
import json
import sys
import argparse
from datetime import datetime
from pathlib import Path

BASE_DIR  = Path(__file__).parent
POOL_FILE = BASE_DIR / "content_pool.json"

# x_post_generator をインポート
sys.path.insert(0, str(BASE_DIR))
from x_post_generator import TEMPLATES


def assemble_text(t: dict) -> str:
    """テンプレートの各フィールドを結合して投稿テキストを作る"""
    parts = []
    for key in ("hook", "empathy", "solution", "summary"):
        v = t.get(key, "").strip()
        if v:
            parts.append(v)
    return "\n\n".join(parts)


def build_pool() -> dict:
    """TEMPLATES から content_pool.json の内容を生成して返す"""
    items: list[dict] = []

    type_labels = {
        "useful":   "役立つ情報",
        "empathy":  "共感・体験",
        "trivia":   "雑学・ネタ",
        "product":  "Amazon商品紹介",
        "progress": "収益進捗ログ",
    }

    for post_type, templates in TEMPLATES.items():
        label = type_labels.get(post_type, post_type)
        for idx, t in enumerate(templates):
            text = assemble_text(t)
            if not text:
                continue
            items.append({
                "id":         f"{post_type}_{idx:03d}",
                "type":       post_type,
                "label":      label,
                "text":       text,
                "hook":       t.get("hook", "").strip(),
                "source":     "template",
                "created_at": datetime.now().strftime("%Y-%m-%d"),
            })

    return {
        "version":    1,
        "updated_at": datetime.now().strftime("%Y-%m-%d"),
        "total":      len(items),
        "items":      items,
    }


def print_stats(pool: dict):
    from collections import Counter
    items = pool.get("items", [])
    counts = Counter(item["type"] for item in items)
    print(f"content_pool.json 統計（合計: {pool.get('total', 0)}件）")
    print(f"更新日: {pool.get('updated_at', '不明')}")
    print()
    for post_type, count in sorted(counts.items()):
        print(f"  {post_type:10s}: {count:3d}件")


def main():
    parser = argparse.ArgumentParser(description="content_pool.json ビルダー")
    parser.add_argument("--stats", action="store_true", help="現在のプール統計を表示（生成しない）")
    args = parser.parse_args()

    if args.stats:
        if not POOL_FILE.exists():
            print(f"{POOL_FILE} が存在しません。先に実行してください。")
            sys.exit(1)
        with POOL_FILE.open(encoding="utf-8") as f:
            pool = json.load(f)
        print_stats(pool)
        return

    pool = build_pool()

    with POOL_FILE.open("w", encoding="utf-8") as f:
        json.dump(pool, f, ensure_ascii=False, indent=2)

    print(f"content_pool.json を生成しました（{pool['total']}件）")
    print_stats(pool)
    print(f"\n保存先: {POOL_FILE}")


if __name__ == "__main__":
    main()
