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
    "一人暮らし始めて食費が月4万円超えてた。外食を減らしたら2万円台に下がった",
    "ふるさと納税を2年間やってなかった。今年から始めたら食費が体感で下がった",
    "格安SIMに乗り換えるのを面倒だと思って1年放置してた。乗り換えたら月5,000円浮いた",
    "電気圧力鍋を買ってから自炊が続くようになった。道具って大事だと実感した",
    "業務スーパーに初めて行ったら鶏肉の価格が普通のスーパーの半分以下だった",
    "コンビニに毎日立ち寄る習慣をやめたら月8,000円以上余った。塵も積もれば山",
    "冷蔵庫の設定温度を「強」から「中」に変えただけで電気代が少し下がった",
    "節水シャワーヘッドを1,500円で買ったら3か月で元が取れた。低コスト節約グッズは最強",
    "部屋の片付けは掃除より「物を減らす」が先だとわかった",
    "作り置きを日曜に1時間やるようにしたら平日の食費と時間の両方が削れた",
    "サブスクの棚卸しをしたら使ってないサービスが3つあった。解約して月3,000円減",
    "一人暮らし3年目になってやっと生活費をコントロールできてきた気がする",
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


# 投稿者ペルソナ（毎回ランダム選択でスパム検知を回避）
_HUMAN_PERSONAS = [
    "節約オタクの20代男性。コスパを数字で語るのが好き。感情より事実優先の口調。",
    "副業歴3年のフリーランサー。失敗談から始めて最後に学びを見せるストーリー型。",
    "ガジェット好きの会社員。スペックより「使い勝手の変化」にフォーカスする体験重視型。",
    "ミニマリストの20代。「物を減らして豊かに」が信条。余計な表現を省いた短文スタイル。",
    "3人家族の主婦。家計管理の実体験から「本当に役立ったもの」だけを正直に紹介する。",
    "浪費を卒業した30代男性。「昔の自分みたいな人に届いてほしい」という伝え方が特徴。",
    "在宅ワーカーの30代女性。共感から始め「わかる…」と思わせてから解決策へ誘導する。",
    "IT系フリーランスの専門家。冷静に「使った結果」を数値やビフォーアフターで示す論理派。",
]


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

    # 投稿ごとに異なるペルソナを割り当て（文体の多様性確保）
    persona_assignments = []
    for i in range(count):
        persona_assignments.append(f"{i+1}番目: {random.choice(_HUMAN_PERSONAS)}")
    personas_text = "\n".join(persona_assignments)

    history_text = ""
    if post_history:
        history_text = f"""
【過去の自分の投稿例（文体・トーンの参考に）】
{chr(10).join(post_history[:5])}
"""

    prompt = f"""
以下のキャラクター割り当てに従い、それぞれの投稿を異なるキャラクターとして書いてください。

【投稿ごとのキャラクター割り当て】
{personas_text}

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
3. 完璧な情報より、生々しい体験談・失敗談・気づきを優先する（誠実・体験談型を徹底）
4. 5つのテンプレートを偏りなく使う（同じパターンを3回以上使わない）
5. 改行で読みやすくする（3〜5行が理想）
6. 投稿ごとにトーンを少し変える（驚き・反省・気づき・ユーモア・決意など）
7. ハッシュタグは出力しない（後から追加する）
8. 10投稿中3〜4件は末尾に自然な「問いかけ」を入れる（例: 「同じ経験した人いる？」「他にオススメあれば教えて」）
9. 禁止ワード: 「絶対」「必ず買え」「騙されたと思って」など過度な煽り表現は使わない

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
        model="gemini-1.5-flash",
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

    # 重複フィルタリング（過去14日間と照合）
    try:
        from content_selector import filter_new_posts, write_skip_log
        posts, skipped = filter_new_posts(posts)
        if skipped:
            print(f"\n[dedup] {len(skipped)}件が過去14日以内の重複として除外されました:")
            for s in skipped:
                reason = s.get("_skip_reason", "")
                print(f"  - [{reason}] {s['text'][:50]}...")
            written = write_skip_log(skipped)
            print(f"  → post_skip.log に {written}件 追記")
        if not posts:
            print("\n全投稿が重複のためキューへの保存をスキップしました。")
            print("human_post_generator.py を再実行するか、--count を増やしてください。")
            return
    except ImportError:
        print("[WARN] content_selector が見つかりません。重複チェックをスキップします。")

    save_queue(posts, append_mode=args.append)

    print("\n次のステップ:")
    print("  python3 scheduled_poster.py preview   # 投稿スケジュール確認")
    print("  python3 scheduled_poster.py run        # 予約投稿を開始")


if __name__ == "__main__":
    main()
