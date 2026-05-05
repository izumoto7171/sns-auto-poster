"""
Bluesky投稿文 自動生成
戦略：検証ログ50% / 共感30% / ライフハック（AI活用で浮いた時間）20%
特徴：Build in Public（現在進行形の検証データ）/ カスタムフィード対応キーワード
文字数：100〜200文字
インプレ強化：ハッシュタグ + バイラルフック + エンゲージCTA
"""
import os
import sys
import random
from datetime import datetime
from pathlib import Path

# gemini_client（money_agent/）をパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent / "money_agent"))

# ─────────────────────────────────────────
# 投稿タイプ
# ─────────────────────────────────────────
POST_TYPES = [
    {"type": "verification", "label": "検証ログ",       "weight": 50},
    {"type": "empathy",      "label": "共感・体験",     "weight": 30},
    {"type": "lifehack",     "label": "AIで浮いた時間", "weight": 20},
]

TIME_SLOTS = [(7, 9), (11, 13), (17, 19), (21, 23)]

# ─────────────────────────────────────────
# Bluesky カスタムフィード対応キーワード
# ─────────────────────────────────────────
FEED_KEYWORDS = {
    "ai":    ["Gemini", "AI自動化", "ChatGPT", "API", "生成AI", "LLM"],
    "side":  ["副業", "アフィリエイト", "自動投稿", "収益化", "Lancers"],
    "tech":  ["Python", "GitHub Actions", "スクリプト", "自動化", "ワークフロー"],
}

# ─────────────────────────────────────────
# ハッシュタグ（タイプ別 × 2〜3個）
# Blueskyはハッシュタグがカスタムフィード流入に直結する
# ─────────────────────────────────────────
HASHTAGS_BY_TYPE = {
    "verification": ["#副業", "#AI自動化", "#BuildInPublic"],
    "empathy":      ["#副業", "#副業初心者", "#フリーランス"],
    "lifehack":     ["#AI活用", "#自動化", "#ライフハック"],
}

# エンゲージメントCTA（フォロー誘導・宣伝臭はNG）
ENGAGEMENT_CTAS = [
    "同じ状況の人いる？",
    "試してみた人いたら教えてほしい",
    "引き続き記録していきます",
    "次の結果もここで公開します",
    "うまくいかなかった話も正直に書く",
    "続きはまた報告します",
]

# バイラルフックパターン
VIRAL_HOOK_PATTERNS = [
    "〇〇を試した結果、△△だった（数字入り）",
    "失敗した話を正直に書く",
    "「〇〇できない」と思ってたら実は××だった",
    "〇〇の前後比較（時間・コスト）",
    "3ヶ月やってみてわかったこと",
]


def append_hashtags(text: str, post_type: str) -> str:
    """投稿テキストにハッシュタグを追加（300文字以内に収める）"""
    tags = HASHTAGS_BY_TYPE.get(post_type, HASHTAGS_BY_TYPE["verification"])
    # ランダムに2個選ぶ
    selected = random.sample(tags, min(2, len(tags)))
    hashtag_str = " ".join(selected)
    full = f"{text}\n\n{hashtag_str}"
    if len(full) <= 300:
        return full
    return f"{text}\n\n{selected[0]}"


# ─────────────────────────────────────────
# テンプレート（APIなしのフォールバック）
# ─────────────────────────────────────────
TEMPLATES = {
    "verification": [
        {
            "text": "【検証】Gemini APIで記事の下書きを自動生成して1週間。\n\n結果：1記事あたり約40分 → 8分に短縮。\n\n品質はまだ粗いけど、叩き台として使えばむしろ早い。\n\nAI自動化の実態、引き続き記録していきます。",
        },
        {
            "text": "GitHub Actionsで副業の自動投稿を組んで2週間。\n\n失敗ログ：Cookieの期限切れで3回投稿がスキップ。\n成功ログ：手動ゼロで28回投稿完了。\n\n自動化は「動いてからが本番」だと痛感してる。",
        },
        {
            "text": "Gemini無料プランの実力を測ってみた。\n\n1日1500回呼び出しOK → 副業コンテンツなら余裕で足りる。\n\n無料でどこまでできるか、引き続き検証中。",
        },
        {
            "text": "アフィリエイト記事をAIで量産して1ヶ月。\n\nSEO流入：0 → 少しずつ増加中（まだ微量）。\n\nわかったこと：記事数より「キーワード選定」が全て。\n\n次の1ヶ月はキーワードを絞って検証します。",
        },
        {
            "text": "Bluesky投稿を毎日自動化して気づいたこと。\n\nリンク入り投稿のいいね：ほぼゼロ。\nリンクなし投稿のいいね：4倍以上。\n\n「広告感」が出た瞬間に読まれなくなる。",
        },
        {
            "text": "副業ブログのPV数、週次で記録してる。\n\n1週目：3PV\n4週目：47PV\n8週目：112PV（今ここ）\n\nまだ少ないけど、右肩上がりは続いてる。",
        },
        {
            "text": "GitHub Actionsのクーロンでアフィリエイト投稿を自動化した。\n\n設定した最初の3日間：エラー率50%。\n\nハマったのはタイムゾーン設定（UTCとJSTを混同してた）。\n\n同じミスで詰まってる人いそう。",
        },
    ],
    "empathy": [
        {
            "text": "副業始めた最初の1ヶ月、1円も稼げなかった。\n\n正直めちゃくちゃ焦った。\n\nでも続けてたら少しずつ形になってきた。\n最初はみんなそんなもんだと思う。",
        },
        {
            "text": "「忙しくて副業する時間ない」←1年前の自分。\n\n1日15分だけって決めてやり始めたら\n3ヶ月で月1万になってた。\n\n時間じゃなくてやり方の問題だった。",
        },
        {
            "text": "完璧にやろうとして何も始められない問題、ありませんか。\n\n今は「60点でいいから動く」を意識してる。\nそっちの方が結果出る。",
        },
        {
            "text": "Lancersで最初の案件を取るまで10連敗した。\n\n提案文を変えたら次の週に受注できた。\n変えたのは「相手が何を不安に思っているか」を書いたこと。",
        },
        {
            "text": "副業の収益が初めてゼロじゃなくなった日のことは今でも覚えてる。\n\n金額は数百円だったけど、\n「仕組みで稼げる」という感覚が初めてわかった瞬間だった。",
        },
        {
            "text": "自動化ツールを組んで3週間、まだ収益はほぼゼロ。\n\nでもわかったこと：投稿数より投稿の質の方が重要。\n\n量産から「1投稿を磨く」に方向転換中。",
        },
    ],
    "lifehack": [
        {
            "text": "AI自動化で浮いた時間で何をしてるか、正直に言うと。\n\nGeminiに任せた作業：2時間 → 20分。\n浮いた時間でLancers受注1件。\n\nAIは「楽をする道具」じゃなく「時間を生む道具」だった。",
        },
        {
            "text": "Python + GitHub Actionsで自動投稿を組んだ。\n\n毎日4回、SNS3つに自動で投稿されてる。\n\n浮いた時間：1日約30分 → 月15時間。\nその時間で次の自動化を考えてる。複利みたいな感覚。",
        },
        {
            "text": "生成AIで「下書き」を作らせるようになってから、\nブログ記事を書くのが怖くなくなった。\n\nAIに雛形を作らせて、自分は「編集者」になる。\nこれだけで作業量が体感半分以下になった。",
        },
    ],
}


def pick_post_type() -> dict:
    total = sum(p["weight"] for p in POST_TYPES)
    r = random.randint(1, total)
    cumulative = 0
    for pt in POST_TYPES:
        cumulative += pt["weight"]
        if r <= cumulative:
            return pt
    return POST_TYPES[0]


_used: dict = {}

def generate_with_template(post_type: str, recent_texts: list = None) -> str:
    templates = TEMPLATES.get(post_type, TEMPLATES["verification"])
    recent_texts = recent_texts or []

    # 直近投稿と重複するテンプレを除外（プロセスをまたいで有効）
    # recent_texts の先頭20文字とテンプレの先頭20文字を比較
    available = [
        t for t in templates
        if not any(rt.startswith(t["text"][:20]) for rt in recent_texts)
    ]
    if not available:
        available = templates  # 全部使い切ったらリセット

    t = random.choice(available)
    return append_hashtags(t["text"], post_type)


def rewrite_x_to_bsky(x_text: str, api_key: str) -> str:
    """X投稿をBluesky用にリライト（検証ログスタイルに変換）"""
    try:
        from gemini_client import generate
        prompt = f"""
以下のX（Twitter）の投稿文を、Bluesky用にリライトしてください。

【元のX投稿】
{x_text}

【Blueskyの戦略・ルール】
- 文字数：100〜200文字程度
- スタイル：「Build in Public」（現在進行形の検証ログ・生データを出す）
- 温度感：広告感ゼロ・「一緒に実験している」感
- ハッシュタグは不要（後から追加する）
- カスタムフィード対応：AI・副業・技術系のキーワードを文中に自然に入れる
- 改行を適度に使い読みやすく

リライトした投稿文のみ出力してください。
"""
        result = generate(prompt, use_cache=False)
        return result if result else x_text
    except Exception as e:
        print(f"⚠️ Gemini失敗: {e}")
        return x_text


def generate_with_gemini(post_type: str, label: str, api_key: str, recent_texts: list = None) -> str:
    try:
        from gemini_client import generate

        ai_kw   = random.choice(FEED_KEYWORDS["ai"])
        side_kw = random.choice(FEED_KEYWORDS["side"])
        tech_kw = random.choice(FEED_KEYWORDS["tech"])
        hook_pattern = random.choice(VIRAL_HOOK_PATTERNS)
        cta = random.choice(ENGAGEMENT_CTAS)

        type_instructions = {
            "verification": (
                "AI・副業・自動化に関する「現在進行形の検証ログ」。"
                "数字（時間・回数・金額）を入れ、成功・失敗を正直に書く。"
                "「〇〇を試した結果〜だった」形式。広告感ゼロ。"
            ),
            "empathy": (
                "副業・AI活用での失敗談・体験談・共感を呼ぶ内容。"
                "「自分も最初は〜」という等身大の言葉で書く。"
            ),
            "lifehack": (
                "AI・自動化で浮いた時間を何に使ったかのリアルな話。"
                "「AIに任せた作業：〇時間 → △分」という前後比較や、"
                "浮いた時間でやったことを具体的に書く。"
            ),
        }

        # 副業開始からの経過週数（実際の運用開始日: 2026-01-01 を起点）
        from datetime import date
        weeks_in = max(1, (date.today() - date(2026, 1, 1)).days // 7)

        recent_block = ""
        if recent_texts:
            samples = "\n".join(f"- {t[:60]}" for t in recent_texts[:5])
            recent_block = f"\n【直近の投稿（これと同じ内容・出だしはNG）】\n{samples}\n"

        prompt = f"""
あなたはBlueskyで副業・AI自動化を「現在進行形」で記録しているユーザーです。
副業を始めて{weeks_in}週目。毎日の試行錯誤を正直に書いています。
{recent_block}

【投稿タイプ】{label}
【内容の方向性】{type_instructions[post_type]}

【必須ルール（絶対に守ること）】
- 文字数：100〜200文字（ハッシュタグ除く）
- ハッシュタグは書かない（後から追加する）
- 改行を使って縦読みしやすくする
- 1行目で数字か具体的な事実を出す（「副業{weeks_in}週目」「〇〇→△△に短縮」など）
- キーワードを文中に自然に入れる: {ai_kw}、{side_kw} のどちらか1つ
- 最後の1行: {cta}

【絶対NG（これをやったら書き直し）】
- 「〇〇してみましょう」「ぜひ〜」「おすすめです」などの勧誘・教える口調
- 「フォローしてね」「プロフを見てね」などの自己宣伝
- 曖昧な表現（「なんとなく」「少し」「うまくいってる」）→ 必ず数字に変える
- URLやリンクを含めること

【構造（この順番で書く）】
1行目: 具体的な数字・事実（今週やったこと or 結果）
空行
2〜3行: 背景・気づき・正直な感想（失敗もOK）
空行
最終行: {cta}

投稿文のみ出力してください。前置きや説明は不要です。
"""
        text = generate(prompt, use_cache=False)
        if text:
            return append_hashtags(text.strip(), post_type)
        print("⚠️ Gemini応答なし（全リトライ失敗）、テンプレート使用")
        return generate_with_template(post_type, recent_texts)
    except Exception as e:
        print(f"⚠️ Gemini失敗、テンプレート使用: {e}")
        return generate_with_template(post_type, recent_texts)


def generate_post(force_type: str = None, x_text: str = None, recent_texts: list = None) -> dict:
    """Bluesky投稿文を生成"""
    post_type_info = pick_post_type() if not force_type else \
        next((p for p in POST_TYPES if p["type"] == force_type), POST_TYPES[0])

    post_type    = post_type_info["type"]
    label        = post_type_info["label"]
    api_key      = os.getenv("GEMINI_API_KEY")
    recent_texts = recent_texts or []

    # X投稿のリライトモード
    if x_text:
        if api_key:
            text = rewrite_x_to_bsky(x_text, api_key)
        else:
            text = x_text
        text = append_hashtags(text, post_type)
        return {"type": "rewrite", "label": "Xリライト", "text": text, "chars": len(text)}

    # 通常生成
    if api_key:
        text = generate_with_gemini(post_type, label, api_key, recent_texts=recent_texts)
    else:
        text = generate_with_template(post_type, recent_texts)

    return {"type": post_type, "label": label, "text": text, "chars": len(text)}


def get_today_schedule(posts_per_day: int = 4) -> list:
    """今日の投稿スケジュールを生成（3〜5回）"""
    today = datetime.now().date()
    slots = random.sample(TIME_SLOTS, min(posts_per_day, len(TIME_SLOTS)))
    schedule = []
    for slot_start, slot_end in sorted(slots):
        hour   = random.randint(slot_start, slot_end - 1)
        minute = random.randint(0, 59)
        schedule.append(datetime(today.year, today.month, today.day, hour, minute))
    return sorted(schedule)


if __name__ == "__main__":
    import sys

    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

    print("=" * 55)
    print("Bluesky 投稿プレビュー（Build in Public戦略）")
    print("=" * 55)

    schedule = get_today_schedule(4)
    types_cycle = ["verification", "empathy", "verification", "lifehack"]

    for i, (t, pt) in enumerate(zip(schedule, types_cycle)):
        post = generate_post(force_type=pt)
        print(f"\n【{t.strftime('%H:%M')}】{post['label']} ({post['chars']}文字)")
        print("─" * 45)
        print(post["text"])
