"""
差別化投稿生成スクリプト
competitor_templates.json のテンプレートと、自分の作業ログ・失敗談を組み合わせて
「AIっぽさを消した自然な日本語」の投稿を10個生成し、post_queue.json に保存する。

使い方:
  python3 human_post_generator.py                        # テンプレートから10投稿生成
  python3 human_post_generator.py --work-log 作業メモ.txt  # 作業ログファイルを指定
  python3 human_post_generator.py --append               # キューに追記（上書きしない）

出力: post_queue.json（scheduled_poster.py が読み取る）
"""
import os
import sys
import json
import argparse
import random
from datetime import datetime


TEMPLATES_FILE = os.path.join(os.path.dirname(__file__), "competitor_templates.json")
QUEUE_FILE     = os.path.join(os.path.dirname(__file__), "post_queue.json")
POST_LOG_FILE  = os.path.join(os.path.dirname(__file__), "post_log.json")

# ─────────────────────────────────────────
# 自分の検証ログ（ここに実際の失敗談・作業記録を書いておく）
# 日常的に更新することで「リアルな人間感」が増す
# ─────────────────────────────────────────
DEFAULT_WORK_LOGS = [
    "GitHub Actionsのcronが日本時間と9時間ずれていてしばらく気づかなかった",
    "Gemini APIのレート制限に何度も引っかかって、リトライ処理を書き直した",
    "はてなブログへのPlaywright自動投稿でCookieが毎週切れる問題が未解決",
    "X APIの無料枠は月1500ポスト制限があることを始めてから知った",
    "最初の1ヶ月は毎日投稿してアクセスゼロ。SEOは時間かかる",
    "アフィリエイトリンクのクリック率を上げようとして記事を全部書き直した",
    "Gemini 2.0 flash liteは無料なのに精度がかなり高くて驚いた",
    "Blueskyのフォロワーがゼロから伸びない。プラットフォームの特性を理解してなかった",
    "収益ゼロが続いたとき、辞めようか本気で考えた。でも仕組みは動いてる",
    "noteの記事をAIで書いたらアクセスが普通に来た。タイトルが大事だと気づいた",
    "自動化ツールをゼロから作ったのでバグ対応に一番時間を使ってる",
    "副業を始めて6ヶ月。まだ月1000円以下。でも仕組みは確実に育ってる",
]


def load_templates() -> dict:
    """competitor_templates.json を読み込む"""
    if not os.path.exists(TEMPLATES_FILE):
        print(f"❌ {TEMPLATES_FILE} が存在しません")
        print("   先に competitor_analyzer.py を実行してください")
        print("   （または --dry-run オプションで動作確認）")
        sys.exit(1)

    with open(TEMPLATES_FILE, encoding="utf-8") as f:
        return json.load(f)


def load_work_log_file(path: str) -> list[str]:
    """テキストファイルから作業ログを読み込む（1行1エントリ）"""
    try:
        with open(path, encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        print(f"作業ログ {len(lines)} 件を読み込みました: {path}")
        return lines
    except Exception as e:
        print(f"⚠️ 作業ログファイル読み込み失敗: {e}")
        return []


def load_post_history_snippets() -> list[str]:
    """post_log.json から過去の投稿内容を抜き出す（文体参考用）"""
    if not os.path.exists(POST_LOG_FILE):
        return []
    try:
        with open(POST_LOG_FILE, encoding="utf-8") as f:
            log = json.load(f)
        # 直近20件のテキストを返す
        texts = [entry.get("text", "") for entry in log[-20:] if entry.get("text")]
        return texts
    except Exception:
        return []


def generate_posts_with_gemini(
    templates: list[dict],
    work_logs: list[str],
    post_history: list[str],
    count: int,
    api_key: str,
) -> list[dict]:
    """Gemini で差別化された投稿を生成"""
    from google import genai

    # ランダムでテンプレートを選ぶ（同じテンプレートを使いすぎない）
    selected_templates = []
    for i in range(count):
        t = templates[i % len(templates)]
        selected_templates.append(t)

    templates_text = "\n".join([
        f"【テンプレート{t['id']}：{t['name']}】\n"
        f"構成: {t['structure']['hook']} → {t['structure']['body']} → {t['structure']['close']}\n"
        f"効果: {t['description']}"
        for t in templates[:5]
    ])

    work_logs_text = "\n".join([f"・{log}" for log in random.sample(work_logs, min(8, len(work_logs)))])

    history_text = ""
    if post_history:
        history_text = f"""
【過去の自分の投稿例（文体・トーンの参考に）】
{chr(10).join(post_history[:5])}
"""

    prompt = f"""
あなたはAI副業・自動化ツールを実際に作って運用しているエンジニア/個人開発者です。
「専門家ではなく、試行錯誤中の普通の人」として投稿します。

【使用するテンプレート構成（5パターン）】
{templates_text}

【自分の実際の作業・失敗ログ（これを素材に使う）】
{work_logs_text}
{history_text}

【依頼】
上記のテンプレートと作業ログを組み合わせて、X（Twitter）投稿を{count}個生成してください。

【絶対ルール】
1. 1投稿あたり日本語で50〜100文字（X換算140単位以内、ハッシュタグ除く）
2. AIが書いたと分かる表現を使わない（「〇〇することが重要です」「〇〇しましょう」「〇〇といえます」禁止）
3. 完璧な情報より、生々しい体験談・失敗談・気づきを優先する
4. 5つのテンプレートを偏りなく使う（同じパターンを3回以上使わない）
5. 改行で読みやすくする（3〜5行が理想）
6. 投稿ごとにトーンを少し変える（驚き・反省・気づき・ユーモア・決意など）
7. ハッシュタグは出力しない（後から追加する）

出力形式（JSONのみ・説明文不要）：
{{
  "posts": [
    {{
      "template_id": 使ったテンプレートのID（整数）,
      "text": "投稿テキスト"
    }}
  ]
}}
"""

    client = genai.Client(api_key=api_key)
    resp = client.models.generate_content(
        model="gemini-2.0-flash-lite",
        contents=prompt,
    )
    raw = resp.text.strip()

    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    data = json.loads(raw)
    return data.get("posts", [])


def save_queue(posts: list[dict], append_mode: bool = False):
    """生成した投稿を post_queue.json に保存"""
    if append_mode and os.path.exists(QUEUE_FILE):
        with open(QUEUE_FILE, encoding="utf-8") as f:
            existing = json.load(f)
        # 未投稿分はそのまま保持
        queue = [p for p in existing if p.get("status") != "posted"]
    else:
        queue = []

    now = datetime.now().isoformat()
    for p in posts:
        queue.append({
            "id":          f"{int(datetime.now().timestamp())}_{random.randint(1000,9999)}",
            "template_id": p.get("template_id"),
            "text":        p["text"],
            "created_at":  now,
            "status":      "pending",  # pending / posted / failed / skipped
            "posted_at":   None,
        })

    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)

    print(f"\n✅ {len(posts)}件をキューに保存: {QUEUE_FILE}")
    print(f"   キュー合計: {len(queue)}件（未投稿）")


def print_posts(posts: list[dict]):
    """生成した投稿をプレビュー表示"""
    print("\n" + "=" * 55)
    print(f"📝 生成した投稿 {len(posts)} 件")
    print("=" * 55)
    for i, p in enumerate(posts, 1):
        tmpl_id = p.get("template_id", "?")
        print(f"\n【投稿 {i}/{len(posts)}】テンプレート{tmpl_id}")
        print("─" * 45)
        print(p["text"])
    print("\n" + "=" * 55)


def main():
    parser = argparse.ArgumentParser(description="差別化X投稿生成ツール")
    parser.add_argument("--count",    type=int, default=10, help="生成件数（デフォルト: 10）")
    parser.add_argument("--work-log", type=str, default=None, help="作業ログファイルのパス")
    parser.add_argument("--append",   action="store_true",   help="既存キューに追記する")
    parser.add_argument("--dry-run",  action="store_true",   help="APIなし・サンプルテンプレートで動作確認")
    args = parser.parse_args()

    # .env 読み込み
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ GEMINI_API_KEY が未設定です")
        sys.exit(1)

    # テンプレート読み込み
    if args.dry_run:
        print("【DRY RUNモード】フォールバック用サンプルテンプレートを使用")
        template_data = {
            "target_account": "sample",
            "templates": [
                {"id": 1, "name": "失敗談＋学び", "description": "共感を呼ぶ失敗→気づき",
                 "structure": {"hook": "失敗した数字を入れる", "body": "何が問題だったか", "close": "前向きな一言"},
                 "example_hook": "3ヶ月で0円だった理由を正直に話す"},
                {"id": 2, "name": "比較＋結論", "description": "試した結果を数字で示す",
                 "structure": {"hook": "複数比較してみた", "body": "箇条書き結果", "close": "自分の結論"},
                 "example_hook": "AIツール5つ試した結果"},
                {"id": 3, "name": "進捗ログ", "description": "リアルタイム性で信頼感",
                 "structure": {"hook": "今日の数字", "body": "課題と対策", "close": "次のアクション"},
                 "example_hook": "【今月の記録】"},
                {"id": 4, "name": "逆説フック", "description": "意外性で読み進めさせる",
                 "structure": {"hook": "一般論の否定", "body": "自分の体験", "close": "本質的な気づき"},
                 "example_hook": "努力しても稼げない理由"},
                {"id": 5, "name": "ハウツー箇条書き", "description": "すぐ保存したくなる実用情報",
                 "structure": {"hook": "〇選・〇ステップ", "body": "シンプルな箇条書き", "close": "試してみて"},
                 "example_hook": "今すぐできる副業3選"},
            ]
        }
    else:
        template_data = load_templates()

    templates = template_data.get("templates", [])
    target    = template_data.get("target_account", "不明")
    print(f"📊 テンプレート読み込み完了（@{target} 分析ベース・{len(templates)}パターン）")

    # 作業ログ
    work_logs = DEFAULT_WORK_LOGS[:]
    if args.work_log:
        extra = load_work_log_file(args.work_log)
        work_logs = extra + work_logs

    # 過去投稿（文体参考）
    post_history = load_post_history_snippets()

    # 生成
    print(f"\n🤖 Gemini で {args.count} 件の投稿を生成中...")
    try:
        posts = generate_posts_with_gemini(templates, work_logs, post_history, args.count, api_key)
    except Exception as e:
        print(f"❌ 投稿生成エラー: {e}")
        sys.exit(1)

    if not posts:
        print("❌ 投稿が生成されませんでした")
        sys.exit(1)

    print_posts(posts)
    save_queue(posts, append_mode=args.append)

    print("\n次のステップ:")
    print("  python3 scheduled_poster.py preview   # 投稿スケジュール確認")
    print("  python3 scheduled_poster.py run        # 予約投稿を開始")


if __name__ == "__main__":
    main()
