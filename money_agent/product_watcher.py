"""
Amazon × A8.net 商品監視パイプライン

【フロー】
1. Amazon ベストセラーRSSから新着商品を取得
2. A8.net 新着承認プログラムを取得
3. Anthropic API（claude-sonnet-4-6）で紹介記事を生成
4. はてなブログに投稿
5. git commit & push（GitHub Actions では不要 — workflow が担当）

【実行】
  python3 money_agent/product_watcher.py           # 通常実行
  python3 money_agent/product_watcher.py dry-run   # 投稿なし・下書き保存
  python3 money_agent/product_watcher.py cli       # claude CLI モード（ローカル向け）
  python3 money_agent/product_watcher.py amazon    # Amazon のみ
  python3 money_agent/product_watcher.py a8        # A8 のみ
"""

from __future__ import annotations

import os
import re
import sys
import json
import time
import subprocess
from datetime import datetime
from pathlib import Path

# ============================================================
# .env 読み込み
# ============================================================
def _load_env():
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

_load_env()

# ============================================================
# 定数
# ============================================================
PENDING_DIR  = Path(__file__).parent / "pending"
PENDING_DIR.mkdir(exist_ok=True)

REPO_ROOT    = Path(__file__).parent.parent
MAX_PER_RUN  = 3   # 1実行あたりの最大処理件数（Gemini/Claude クォータ節約）
DRY_RUN      = "dry-run" in sys.argv
CLI_MODE     = "cli" in sys.argv
ONLY_AMAZON  = "amazon" in sys.argv
ONLY_A8      = "a8" in sys.argv

ARTICLE_PROMPT_AMAZON = """\
あなたはAmazonアソシエイトのアフィリエイトブログ専門ライターです。
以下の商品を紹介するSEO最適化記事を書いてください。

【商品情報】
- 商品名: {title}
- カテゴリ: {category}
- 商品説明: {description}
- アフィリエイトURL: {url}

【記事要件】
- 文字数: 2000〜3000文字
- 対象読者: 購入を検討しているユーザー
- 見出し構成: 商品概要 / 特徴・メリット / こんな人におすすめ / 口コミ・評判 / まとめ
- アフィリエイトURL へのCTAを2〜3箇所に自然に配置
- SEOキーワードを見出しと本文に自然に含める
- HTML形式で出力（h2/h3/p/ul/li/strong タグ使用、装飾スタイル不要）

出力フォーマット（必ずこの形式で返す）:
<meta>
{{"title": "SEO最適化された記事タイトル（30〜50文字）", "tags": ["タグ1", "タグ2", "タグ3"]}}
</meta>
<body>
（HTML形式の記事本文）
</body>
"""

ARTICLE_PROMPT_A8 = """\
あなたはA8.netのアフィリエイトブログ専門ライターです。
以下のサービスを紹介するSEO最適化記事を書いてください。

【サービス情報】
- サービス名: {name}
- 提供会社: {company}
- 成果報酬: {reward}
- アフィリエイトURL: {url}

【記事要件】
- 文字数: 2000〜3000文字
- 対象読者: 副業・節約に興味があるサラリーマン・フリーランス・主婦
- 見出し構成: サービス概要 / 特徴・メリット / 申込方法 / こんな人におすすめ / まとめ
- アフィリエイトURL へのCTAを2〜3箇所に自然に配置（「今すぐ申し込む」「無料で始める」など）
- SEOキーワードを見出しと本文に自然に含める
- HTML形式で出力（h2/h3/p/ul/li/strong タグ使用、装飾スタイル不要）

出力フォーマット（必ずこの形式で返す）:
<meta>
{{"title": "SEO最適化された記事タイトル（30〜50文字）", "tags": ["タグ1", "タグ2", "タグ3"]}}
</meta>
<body>
（HTML形式の記事本文）
</body>
"""


# ============================================================
# 記事生成（Anthropic API）
# ============================================================
def generate_article_api(product: dict) -> dict | None:
    """claude-sonnet-4-6 で記事を生成"""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("[Claude] ANTHROPIC_API_KEY 未設定")
        return None

    try:
        import anthropic
    except ImportError:
        print("[Claude] pip install anthropic が必要")
        return None

    source = product.get("source", "")
    if source == "amazon":
        prompt = ARTICLE_PROMPT_AMAZON.format(
            title=product.get("title", ""),
            category=product.get("category", ""),
            description=product.get("description", ""),
            url=product.get("url", ""),
        )
    else:  # a8
        prompt = ARTICLE_PROMPT_A8.format(
            name=product.get("name", ""),
            company=product.get("company", ""),
            reward=product.get("reward", ""),
            url=product.get("affiliate_url", ""),
        )

    client = anthropic.Anthropic(api_key=api_key)
    for attempt in range(3):
        try:
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            content = message.content[0].text
            break
        except Exception as e:
            print(f"[Claude API] attempt {attempt + 1}/3 失敗: {e}")
            if attempt < 2:
                time.sleep(10 * (attempt + 1))
            else:
                return None

    return _parse_article_response(content, product)


# ============================================================
# 記事生成（claude CLI）
# ============================================================
def generate_article_cli(product: dict) -> dict | None:
    """claude -p で記事を生成（ローカル実行向け）"""
    source = product.get("source", "")
    if source == "amazon":
        prompt = ARTICLE_PROMPT_AMAZON.format(
            title=product.get("title", ""),
            category=product.get("category", ""),
            description=product.get("description", ""),
            url=product.get("url", ""),
        )
    else:
        prompt = ARTICLE_PROMPT_A8.format(
            name=product.get("name", ""),
            company=product.get("company", ""),
            reward=product.get("reward", ""),
            url=product.get("affiliate_url", ""),
        )

    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True, text=True, timeout=120,
            cwd=str(REPO_ROOT),
        )
        if result.returncode != 0:
            print(f"[claude CLI] エラー: {result.stderr[:300]}")
            return None
        return _parse_article_response(result.stdout, product)
    except FileNotFoundError:
        print("[claude CLI] claude コマンドが見つかりません")
        return None
    except Exception as e:
        print(f"[claude CLI] 実行失敗: {e}")
        return None


# ============================================================
# レスポンスパース
# ============================================================
def _parse_article_response(content: str, product: dict) -> dict | None:
    """<meta>/<body> フォーマットを解析"""
    meta_match = re.search(r"<meta>\s*(\{.*?\})\s*</meta>", content, re.DOTALL)
    body_match = re.search(r"<body>\s*(.*?)\s*</body>", content, re.DOTALL)

    if not body_match:
        # フォーマット無視して全体を body とみなす
        body = content.strip()
        title = product.get("title") or product.get("name", "商品紹介記事")
        tags  = [product.get("category", "アフィリエイト")]
    else:
        body  = body_match.group(1).strip()
        title = product.get("title") or product.get("name", "商品紹介記事")
        tags  = [product.get("category", "アフィリエイト")]
        if meta_match:
            try:
                meta = json.loads(meta_match.group(1))
                title = meta.get("title", title)
                tags  = meta.get("tags", tags)
            except json.JSONDecodeError:
                pass

    if not body:
        return None

    return {
        "title":         title,
        "body":          body,
        "tags":          tags,
        "category":      product.get("category", "副業"),
        "source":        product.get("source", ""),
        "affiliate_url": product.get("url") or product.get("affiliate_url", ""),
        "product_name":  product.get("title") or product.get("name", ""),
    }


# ============================================================
# はてなブログ投稿
# ============================================================
def post_to_hatena(article: dict) -> bool:
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from hatena_atomapi import post
        url = post(article)
        print(f"[Hatena] 投稿: {article['title'][:50]} → {url}")
        return True
    except Exception as e:
        print(f"[Hatena] 投稿失敗: {e}")
        return False


# ============================================================
# 下書き保存（dry-run 用）
# ============================================================
def save_draft(article: dict):
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    src  = article.get("source", "unknown")
    path = PENDING_DIR / f"draft_{src}_{ts}.json"
    path.write_text(json.dumps(article, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[dry-run] 下書き保存: {path.name}")


# ============================================================
# git commit & push
# ============================================================
def git_push(message: str):
    """変更をコミット & プッシュ"""
    try:
        subprocess.run(["git", "add", "-A"], cwd=REPO_ROOT, check=True, capture_output=True)
        diff = subprocess.run(
            ["git", "diff", "--staged", "--quiet"],
            cwd=REPO_ROOT, capture_output=True,
        )
        if diff.returncode == 0:
            print("[git] コミットする変更なし")
            return
        subprocess.run(["git", "commit", "-m", message], cwd=REPO_ROOT, check=True, capture_output=True)
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=REPO_ROOT, check=True, capture_output=True)
        subprocess.run(["git", "push"], cwd=REPO_ROOT, check=True, capture_output=True)
        print(f"[git] プッシュ完了: {message}")
    except subprocess.CalledProcessError as e:
        print(f"[git] 失敗: {e}")


# ============================================================
# メインパイプライン
# ============================================================
def run():
    print(f"[{datetime.now():%Y-%m-%d %H:%M}] 商品監視パイプライン開始"
          + (" [dry-run]" if DRY_RUN else "")
          + (" [CLI]"     if CLI_MODE else ""))

    all_products = []

    # --- Amazon 新着商品 ---
    if not ONLY_A8:
        try:
            from amazon_monitor import fetch_new_products as fetch_amazon
            amazon_products = fetch_amazon(max_per_run=MAX_PER_RUN)
            all_products.extend(amazon_products)
        except Exception as e:
            print(f"[Amazon] スキップ: {e}")

    # --- A8.net 新着承認プログラム ---
    if not ONLY_AMAZON:
        try:
            from a8_approved_auto import (
                a8_login, fetch_new_approved, fetch_best_link,
                load_seen as a8_load_seen, save_seen as a8_save_seen,
            )
            a8_session = a8_login()
            if a8_session:
                a8_seen     = a8_load_seen()
                a8_programs = [
                    p for p in fetch_new_approved(a8_session)
                    if p.get("ins_id") not in a8_seen
                ]
                # アフィリエイトURLを付与
                for p in a8_programs[:MAX_PER_RUN]:
                    link = fetch_best_link(a8_session, p["ins_id"])
                    p["affiliate_url"] = link
                    p["source"]        = "a8"
                all_products.extend(a8_programs[:MAX_PER_RUN])
                print(f"[A8] 新着: {len(a8_programs)}件")
        except Exception as e:
            print(f"[A8] スキップ: {e}")

    if not all_products:
        print("新着なし — 終了")
        return

    # --- 記事生成 & 投稿 ---
    posted = 0
    a8_processed = []

    for product in all_products[:MAX_PER_RUN]:
        name = product.get("title") or product.get("name", "不明")
        print(f"\n処理: {name[:60]}")

        article = generate_article_cli(product) if CLI_MODE else generate_article_api(product)

        if not article:
            print("  → 記事生成失敗、スキップ")
            continue

        if DRY_RUN:
            save_draft(article)
            continue

        if post_to_hatena(article):
            posted += 1
            if product.get("source") == "a8":
                a8_processed.append(product.get("ins_id"))

        time.sleep(3)

    # A8 処理済みを保存
    if a8_processed:
        try:
            from a8_approved_auto import load_seen as a8_load_seen, save_seen as a8_save_seen
            a8_seen = a8_load_seen()
            a8_seen.update(a8_processed)
            a8_save_seen(a8_seen)
        except Exception as e:
            print(f"[A8] seen 保存失敗: {e}")

    # git push（ローカル実行のみ。GitHub Actions は workflow が担当）
    if posted > 0 and not DRY_RUN and "GITHUB_ACTIONS" not in os.environ:
        git_push(f"feat: 商品記事投稿 {posted}件 {datetime.now().strftime('%Y-%m-%d')}")

    print(f"\n完了: {posted}件投稿")


if __name__ == "__main__":
    run()
