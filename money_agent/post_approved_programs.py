"""
A8.net 新着承認プログラム → 記事生成 → はてな投稿

承認済みプログラムのアフィリエイトリンクを直接指定して記事を生成・投稿する。
Gemini レートリミット時は指数バックオフでリトライ。
"""

import os
import sys
import json
import time
from datetime import datetime
from pathlib import Path

# .env読み込み
def load_env():
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

load_env()

# Supabase クライアント
sys.path.insert(0, str(Path(__file__).parent.parent))
from db_client import db

# ============================================================
# 承認済みプログラム定義（A8.net から取得済み）
# ============================================================
APPROVED_PROGRAMS = [
    {
        "id": "approved_mf_kakutei_2026",
        "name": "マネーフォワード クラウド確定申告",
        "company": "株式会社マネーフォワード",
        "genre": "クラウド会計・確定申告",
        "reward": "新規会員登録1500円",
        "epc": 22.85,
        "confirm_rate": "27.31%",
        "affiliate_url": "https://px.a8.net/svt/ejp?a8mat=4B1DXL+8UIXF6+4JGQ+BWVTE",
        "description": "はじめての方でも確定申告がラクラク完了できるクラウド型確定申告ソフト。自動化で準備時間を1/6に短縮。",
        "keyword": "マネーフォワード クラウド確定申告",
    },
    {
        "id": "approved_mf_kaikeigyo_2026",
        "name": "マネーフォワード クラウド開業届",
        "company": "株式会社マネーフォワード",
        "genre": "開業・個人事業主サポート",
        "reward": "新規無料会員登録300円",
        "epc": 15.38,
        "confirm_rate": "63.26%",
        "affiliate_url": "https://px.a8.net/svt/ejp?a8mat=4B1DXL+8XI3G2+4JGQ+1NQUK2",
        "description": "簡単3ステップで開業届を作成・提出できるサービス。個人事業主の開業手続きをラクに。",
        "keyword": "マネーフォワード クラウド開業届",
    },
    {
        "id": "approved_mf_kaikei_2026",
        "name": "マネーフォワード クラウド会計",
        "company": "株式会社マネーフォワード",
        "genre": "クラウド会計",
        "reward": "新規会員登録700円",
        "epc": 3.57,
        "confirm_rate": "28.57%",
        "affiliate_url": "https://px.a8.net/svt/ejp?a8mat=4B1DXL+987WC2+4JGQ+60WN6",
        "description": "会計業務を約1/2に削減するクラウド会計ソフト。6つのサービスがセットで使える。",
        "keyword": "マネーフォワード クラウド会計",
    },
    {
        "id": "approved_freee_2026",
        "name": "freee会計",
        "company": "株式会社Wiz",
        "genre": "クラウド会計",
        "reward": "新規導入1500円（通常プラン）／新規導入20000円（補助金プラン）",
        "epc": 3.09,
        "confirm_rate": "13.63%",
        "affiliate_url": "https://px.a8.net/svt/ejp?a8mat=4B1DXL+8AVMGI+3SPO+9FDI8Y",
        "description": "クラウド会計シェアNo.1のfreee会計。法改正も基本料金内で対応、補助金プランあり。",
        "keyword": "freee会計",
    },
]

def load_seen() -> set:
    """処理済みプログラム ID の set を DB から返す"""
    try:
        return db.get_a8_processed_ids("new")
    except Exception as e:
        print(f"[PostApproved] 処理済みDB読み込み失敗: {e}")
        return set()


def mark_single(program_id: str) -> None:
    """1件を処理済みとして DB にマークする（並列安全）"""
    try:
        db.mark_a8_processed(program_id, "new")
    except Exception as e:
        print(f"[PostApproved] 処理済みDB書き込み失敗 ({program_id}): {e}")


_URL_PLACEHOLDER = "AFFILIATE_URL_PLACEHOLDER"


def generate_article(program: dict, max_retries: int = 5):
    """Gemini APIで記事生成。gemini_client 経由（tenacityリトライ付き）。"""
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from gemini_client import generate as gemini_generate, strip_code_block
    except ImportError:
        print("[Gemini] gemini_client 未インポート")
        return None

    affiliate_url = program['affiliate_url']
    year = datetime.now().year

    # URLはプロンプトに含めず、生成後にPython側でプレースホルダーを置換する
    # （GeminiがURLを書き換えるバグを防ぐ）
    prompt = f"""あなたはアフィリエイトブログの専門ライターです。
以下のサービスを紹介するSEO最適化記事を書いてください。

【サービス情報】
- サービス名: {program['name']}
- 提供会社: {program['company']}
- ジャンル: {program['genre']}
- 報酬: {program['reward']}
- 概要: {program['description']}

【記事要件】
- 文字数: 2000〜3000文字
- 対象読者: 副業・節約に興味があるサラリーマン・フリーランス・主婦
- 構成: 導入 → サービス概要 → メリット3〜5個 → こんな人におすすめ → 料金・登録方法 → まとめ
- タイトルはSEOキーワードを含む（例:「【{year}年最新】{program['name']}の評判は？メリット・デメリットを徹底解説」）
- 自然な口調で読みやすく
- 見出しはMarkdown（## / ###）を使用
- 記事末尾に必ずアフィリエイトリンクのCTAを入れる
  形式: <a href="{_URL_PLACEHOLDER}" rel="nofollow">▶ {program['name']}の公式サイトで詳細を確認する</a>
- コードブロックなし、JSONのみで返す

以下のJSON形式で返してください:
{{
  "title": "記事タイトル（SEOキーワード含む）",
  "keyword": "SEOメインキーワード（20文字以内）",
  "category": "副業",
  "tags": ["クラウド会計", "確定申告", "フリーランス", "副業"],
  "body": "本文（Markdown + アフィリエイトリンク含む）"
}}"""

    raw = gemini_generate(prompt, use_cache=False)
    if not raw:
        print(f"[Gemini] 記事生成失敗（全リトライ消耗）: {program['name']}")
        return None

    try:
        text = strip_code_block(raw)
        article = json.loads(text.strip())
        # プレースホルダーを実URLに置換（Geminiにはリンク文字列を触らせない）
        article["body"] = article.get("body", "").replace(_URL_PLACEHOLDER, affiliate_url)
        article["program_id"]   = program["id"]
        article["program_name"] = program["name"]
        article["generated_at"] = datetime.now().isoformat()
        return article
    except Exception as e:
        print(f"[Gemini] JSONパースエラー ({program['name']}): {e}")
        return None


def run(dry_run: bool = False, force: bool = False):
    """承認済みプログラムの記事を生成してはてな投稿"""
    print(f"\n=== 承認済みプログラム記事投稿 {'[DRY RUN]' if dry_run else ''} ===")
    print(f"実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    seen = load_seen()
    # EPC降順でソート（高単価から処理）
    targets = sorted(
        [p for p in APPROVED_PROGRAMS if force or p["id"] not in seen],
        key=lambda x: x["epc"],
        reverse=True
    )

    if not targets:
        print("全プログラム処理済み。--force で再実行可能。")
        return

    print(f"処理対象: {len(targets)}件")
    for p in targets:
        print(f"  - {p['name']} (EPC:{p['epc']}, 報酬:{p['reward']})")

    sys.path.insert(0, str(Path(__file__).parent))
    from hatena_atomapi import post as hatena_post

    posted = 0
    for program in targets:
        print(f"\n--- {program['name']} ---")

        article = generate_article(program)
        if not article:
            print(f"  記事生成失敗。スキップ（seenには追加しない→次回リトライ対象）。")
            continue

        print(f"  タイトル: {article['title'][:70]}")
        print(f"  文字数: {len(article.get('body', ''))}文字")

        if dry_run:
            print(f"  [DRY RUN] 本文冒頭:\n{article.get('body','')[:300]}...")
            mark_single(program["id"])
            posted += 1
        else:
            url = hatena_post(article)
            if url:
                print(f"  投稿完了: {url}")
                mark_single(program["id"])
                posted += 1
            else:
                print(f"  投稿失敗")
            time.sleep(5)  # 連続投稿間隔
    print(f"\n=== 完了: {posted}/{len(targets)}件投稿 ===")


if __name__ == "__main__":
    args = sys.argv[1:]
    dry_run = "dry-run" in args or "dry_run" in args
    force = "--force" in args
    run(dry_run=dry_run, force=force)
