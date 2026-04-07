"""
Bluesky投稿文 自動生成
戦略：検証ログ50% / 共感30% / ライフハック（AI活用で浮いた時間）20%
特徴：Build in Public（現在進行形の検証データ）/ カスタムフィード対応キーワード
文字数：100〜200文字
インプレ強化：ハッシュタグ + バイラルフック + エンゲージCTA
"""
import os
import random
from datetime import datetime

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

# エンゲージメントCTA
ENGAGEMENT_CTAS = [
    "同じ状況の人いる？",
    "試してみた人いたら教えてほしい",
    "引き続き記録していきます",
    "気になった人はフォローしてね",
    "次の結果もここで公開します",
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

def generate_with_template(post_type: str) -> str:
    templates = TEMPLATES.get(post_type, TEMPLATES["verification"])
    today = datetime.now().strftime("%Y%m%d")
    key = f"{today}_{post_type}"
    used = _used.get(key, [])
    available = [t for i, t in enumerate(templates) if i not in used]
    if not available:
        available = templates
        _used[key] = []
    t = random.choice(available)
    idx = templates.index(t)
    _used.setdefault(key, []).append(idx)
    return append_hashtags(t["text"], post_type)


def rewrite_x_to_bsky(x_text: str, api_key: str) -> str:
    """X投稿をBluesky用にリライト（検証ログスタイルに変換）"""
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
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
        resp = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=prompt,
        )
        return resp.text.strip()
    except Exception as e:
        print(f"⚠️ Gemini失敗: {e}")
        return x_text


def generate_with_gemini(post_type: str, label: str, api_key: str) -> str:
    try:
        from google import genai
        client = genai.Client(api_key=api_key)

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

        prompt = f"""
あなたはBlueskyで副業・AI自動化を「現在進行形」で実験・公開しているユーザーです。
読者と一緒に試行錯誤している「Build in Public」スタイルで投稿してください。

【投稿タイプ】{label}
【内容の方向性】{type_instructions[post_type]}

【バイラルフックの参考（そのまま使わずアレンジする）】
{hook_pattern}

【Blueskyのルール】
- 文字数：100〜200文字（ハッシュタグ除く）
- ハッシュタグは不要（後から追加する）
- カスタムフィード対応：以下のキーワードを文中に1〜2個、自然に入れること
  → {ai_kw}、{side_kw}、{tech_kw}
- 改行多めで読みやすく
- 「教える」口調NG → 「やってみた」「わかった」「失敗した」口調でOK
- 広告・PR感ゼロ
- 最後は「{cta}」で締める

【構造】
1行目：今やっていることや結果（数字入り）
↓（空行）
2〜3行：背景・気づき・失敗ポイント
↓（空行）
最終行：{cta}

投稿文のみ出力してください。
"""
        resp = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=prompt,
        )
        text = resp.text.strip()
        return append_hashtags(text, post_type)
    except Exception as e:
        print(f"⚠️ Gemini失敗、テンプレート使用: {e}")
        return generate_with_template(post_type)


def generate_post(force_type: str = None, x_text: str = None) -> dict:
    """Bluesky投稿文を生成"""
    post_type_info = pick_post_type() if not force_type else \
        next((p for p in POST_TYPES if p["type"] == force_type), POST_TYPES[0])

    post_type = post_type_info["type"]
    label     = post_type_info["label"]
    api_key   = os.getenv("GEMINI_API_KEY")

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
        text = generate_with_gemini(post_type, label, api_key)
    else:
        text = generate_with_template(post_type)

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
