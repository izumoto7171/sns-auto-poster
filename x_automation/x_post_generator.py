"""
X（Twitter）投稿文 自動生成
戦略：役立つ情報60% / 共感20% / 雑学10% / 商品紹介10%
構造：①興味を引く一文 → ②共感・問題提起 → ③解決方法 → ④まとめ
"""
import os
import random
import json
import re
from datetime import datetime, timedelta

# ─────────────────────────────────────────
# 投稿タイプの定義と重み
# ─────────────────────────────────────────
POST_TYPES = [
    {"type": "useful",   "label": "役立つ情報",   "weight": 60},
    {"type": "empathy",  "label": "共感・体験",   "weight": 20},
    {"type": "trivia",   "label": "雑学・ネタ",   "weight": 10},
    {"type": "product",  "label": "商品紹介",     "weight": 10},
]

# ─────────────────────────────────────────
# 投稿時間帯（4スロット）
# ─────────────────────────────────────────
TIME_SLOTS = [
    (7, 9),
    (11, 13),
    (17, 19),
    (21, 23),
]

# ─────────────────────────────────────────
# テンプレート（APIなしでも動く）
# ─────────────────────────────────────────
TEMPLATES = {
    "useful": [
        {
            "hook":    "実はAI副業で月3万円なら、かなり現実的です。",
            "empathy": "「副業って難しそう」と思ってる人、多いですよね。\n\nでも実際は、",
            "solution": "・AI記事作成\n・AI翻訳\n・AI画像生成\n\nこの3つは初心者でもすぐ始められる。",
            "summary": "使えるツールはプロフィールにまとめてます👆",
        },
        {
            "hook":    "時間を2倍使えるようになった、たった1つの習慣。",
            "empathy": "「やることが多すぎて全部できない」\n\nそれ、順番の問題かもしれません。",
            "solution": "朝の最初の30分だけ、\n一番大事なこと1つだけに集中する。\n\nこれだけで1日の質が変わります。",
            "summary": "シンプルだけど、続けると効果がデカい🔥",
        },
        {
            "hook":    "スマホ1台でできる副業、3選。",
            "empathy": "「パソコンないから副業できない」\n\nそんなことないです。",
            "solution": "① ポイ活（月5,000円〜）\n② アンケートモニター\n③ AI画像販売\n\n全部スマホだけでOK。",
            "summary": "まず1つ試すだけで感覚つかめます✅",
        },
    ],
    "empathy": [
        {
            "hook":    "正直に言います。副業を始めた最初の1ヶ月は、全然稼げませんでした。",
            "empathy": "やり方が分からなくて\n試行錯誤の毎日。",
            "solution": "でも続けてたら少しずつ形になってきた。\n\n最初はみんなそんなもん。",
            "summary": "「うまくいかない」は通過点🙆",
        },
        {
            "hook":    "「忙しくて副業する時間がない」←これ、昔の自分です。",
            "empathy": "通勤中も帰宅後もヘトヘト。\nそんな状態で何ができるの、って。",
            "solution": "でも1日15分だけやってみたら\n3ヶ月で月1万円になってた。\n\n時間じゃなくて、やり方の問題だった。",
            "summary": "少しだけ試してみる価値はある👀",
        },
    ],
    "trivia": [
        {
            "hook":    "ChatGPTが1回返答するのに使う電力、知ってますか？",
            "empathy": "普通のGoogle検索の10倍以上らしい。",
            "solution": "それでも世界中で毎日何億回も使われてる。\n\nAIってどんだけエネルギー食ってんだ笑",
            "summary": "便利さとコストは常にトレードオフ🌍",
        },
        {
            "hook":    "AIに「ありがとう」って言う人、意外と多い説。",
            "empathy": "無意識に礼儀正しくなってしまう現象。",
            "solution": "感謝されるとAIの返答品質が上がる\nって研究もあるらしい。\n\n本当かどうかはともかく、",
            "summary": "優しい人はAIにも優しい説🤖",
        },
    ],
    "product": [
        {
            "hook":    "AIツール、結局どれが一番コスパいいの？って思って全部試した。",
            "empathy": "有料サービスに課金しまくった時期がありまして。",
            "solution": "結論、最初は無料ツールで十分でした。\n\n特にGeminiは無料なのに精度が高くて驚いた。\nライフハック系の文章なら十分使える。",
            "summary": "詳しくはプロフィールのリンクから🔗",
        },
        {
            "hook":    "副業で稼げる人と稼げない人、何が違うんだろうと観察してみた。",
            "empathy": "スキルの差より、情報の差が大きかった。",
            "solution": "稼げる人は「どこで稼ぐか」を知ってる。\nやみくもに作業してるわけじゃない。\n\n自分が参考にしたサービスはプロフィールに。",
            "summary": "情報格差を埋めるだけで変わります✅",
        },
    ],
}


def pick_post_type() -> dict:
    """重み付きランダムで投稿タイプを選択"""
    total = sum(p["weight"] for p in POST_TYPES)
    r = random.randint(1, total)
    cumulative = 0
    for pt in POST_TYPES:
        cumulative += pt["weight"]
        if r <= cumulative:
            return pt
    return POST_TYPES[0]


_used_templates: dict = {}  # 同じ日に同じテンプレを使わないよう管理

def generate_with_template(post_type: str) -> str:
    """テンプレートから投稿文を生成（同日重複防止）"""
    templates = TEMPLATES.get(post_type, TEMPLATES["useful"])
    today = datetime.now().strftime("%Y%m%d")
    key = f"{today}_{post_type}"

    used = _used_templates.get(key, [])
    available = [t for i, t in enumerate(templates) if i not in used]
    if not available:
        available = templates  # 全部使ったらリセット
        _used_templates[key] = []

    t = random.choice(available)
    idx = templates.index(t)
    _used_templates.setdefault(key, []).append(idx)

    post = f"{t['hook']}\n\n{t['empathy']}\n\n{t['solution']}\n\n{t['summary']}"
    return post


def generate_with_gemini(post_type: str, label: str, api_key: str) -> str:
    """Gemini APIで投稿文を生成"""
    try:
        from google import genai

        type_instructions = {
            "useful":  "AI副業・時短・節約・生産性向上などに関する役立つ情報投稿",
            "empathy": "副業や生活改善での失敗談・体験談・共感を呼ぶ投稿",
            "trivia":  "AI・テクノロジー・お金に関する意外な雑学・ネタ投稿",
            "product": "AIツールや副業サービスを体験談・比較として自然に紹介する投稿（直接的な広告表現は禁止）",
        }

        client = genai.Client(api_key=api_key)
        prompt = f"""
あなたはX（Twitter）で副業・AI・ライフハック情報を発信するインフルエンサーです。

【投稿タイプ】{label}（{type_instructions[post_type]}）

【必須ルール】
・全体140〜250文字程度
・改行を多めに使い、読みやすくする
・具体的な数字やメリットを入れる
・ユーザーの悩みに触れる導入から始める
・「プロフィールにまとめてます」「プロフィールリンクから」などで締める
・ハッシュタグは不要
・広告・宣伝っぽい表現は使わない

【構造】
1行目：興味を引く一文（結論や数字を含む）
↓（空行）
2〜3行：共感または問題提起
↓（空行）
3〜5行：解決方法や情報（箇条書きOK）
↓（空行）
最終行：軽いまとめ＋プロフィール誘導

投稿文のみ出力してください。説明・タイトルは不要。
"""
        resp = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=prompt,
        )
        return resp.text.strip()

    except Exception as e:
        print(f"⚠️ Gemini失敗、テンプレート使用: {e}")
        return generate_with_template(post_type)


def generate_post(force_type: str = None) -> dict:
    """投稿文を生成して返す"""
    post_type_info = pick_post_type() if not force_type else \
        next((p for p in POST_TYPES if p["type"] == force_type), POST_TYPES[0])

    post_type = post_type_info["type"]
    label     = post_type_info["label"]

    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        text = generate_with_gemini(post_type, label, api_key)
    else:
        text = generate_with_template(post_type)

    return {
        "type":  post_type,
        "label": label,
        "text":  text,
        "chars": len(text),
    }


def get_today_schedule() -> list:
    """今日の投稿スケジュール（4回分）を生成"""
    today = datetime.now().date()
    schedule = []

    for slot_start, slot_end in TIME_SLOTS:
        # スロット内でランダムな時間を選択（前回と被らないよう）
        hour   = random.randint(slot_start, slot_end - 1)
        minute = random.randint(0, 59)
        post_time = datetime(today.year, today.month, today.day, hour, minute)
        schedule.append(post_time)

    schedule.sort()
    return schedule


def preview_posts(count: int = 4):
    """生成した投稿をプレビュー表示"""
    print("=" * 55)
    print("📋 今日のX投稿プレビュー")
    print("=" * 55)

    schedule = get_today_schedule()

    for i in range(count):
        post = generate_post()
        post_time = schedule[i] if i < len(schedule) else None

        print(f"\n【投稿 {i+1}/4】{post['label']} ({post['chars']}文字)")
        if post_time:
            print(f"🕐 投稿予定時刻: {post_time.strftime('%H:%M')}")
        print("─" * 45)
        print(post["text"])
        print()

    print("=" * 55)


if __name__ == "__main__":
    # .envを読み込む
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

    preview_posts(4)
