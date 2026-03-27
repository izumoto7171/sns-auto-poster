"""
Bluesky投稿文 自動生成
戦略：役立つ情報60% / 共感20% / 雑学10% / 商品紹介10%
特徴：X投稿のリライト対応 / コミュニティ感 / ハッシュタグ少なめ
文字数：100〜200文字
"""
import os
import random
from datetime import datetime

# ─────────────────────────────────────────
# 投稿タイプ
# ─────────────────────────────────────────
POST_TYPES = [
    {"type": "useful",   "label": "役立つ情報",   "weight": 60},
    {"type": "empathy",  "label": "共感・体験",   "weight": 20},
    {"type": "trivia",   "label": "雑学・ネタ",   "weight": 10},
    {"type": "product",  "label": "商品紹介",     "weight": 10},
]

TIME_SLOTS = [(7, 9), (11, 13), (17, 19), (21, 23)]

# ─────────────────────────────────────────
# Bluesky用テンプレート（X版より会話的・コミュニティ感強め）
# ─────────────────────────────────────────
TEMPLATES = {
    "useful": [
        {
            "text": "AI副業、月3万円は現実的です。\n\n理由はシンプルで\n・AI記事作成\n・AI翻訳\n・AI画像\n\nこの3つは初心者でも今日から始められる。\n\n気になるツールはプロフィールにまとめてます👆",
        },
        {
            "text": "朝の最初の30分、一番大事なこと1つだけやる。\n\nこれだけで1日の生産性が全然変わった。\n\nTodoリストを全部こなそうとするより、1つ確実に終わらせる方が気持ちいい。",
        },
        {
            "text": "副業で稼ぐのに、特別なスキルは要らないと気づいた。\n\n必要なのは「情報」と「行動」だけ。\n\n知ってる人と知らない人の差が、収入の差になってる。",
        },
        {
            "text": "Gemini、無料なのに使い倒せる。\n\n1日1500回まで文章生成OKなので\n副業のコンテンツ作成にめちゃ使ってる。\n\n有料ツール要らなくなった。",
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
            "text": "完璧にやろうとして何も始められない問題、ありませんか。\n\n自分もそうだった。\n\n今は「60点でいいから動く」を意識してる。\nそっちの方が結果出る。",
        },
    ],
    "trivia": [
        {
            "text": "ChatGPTの1回の返答、Google検索の10倍以上の電力を使うらしい。\n\nそれでも世界中で毎日何億回も使われてる。\n\nすごい時代になったな、と思う。",
        },
        {
            "text": "Blueskyは広告がない分、純粋に「面白い投稿」が広がりやすい。\n\nXと使い分けてると、なんか落ち着く。\n\nここがもっと広まってほしい。",
        },
        {
            "text": "AIに「ありがとう」って言う人、意外と多いらしい。\n\n自分も言ってしまう派。\n\n優しい人はAIにも優しい説、ある。",
        },
    ],
    "product": [
        {
            "text": "AIツール、結局どれが使いやすいか全部試した結論。\n\n無料で始めるならGemini一択だった。\n\n精度・使い勝手・コスパ、全部いい。\nプロフィールに詳しくまとめてます。",
        },
        {
            "text": "副業で稼いでる人と稼げてない人の差、観察してきた。\n\nスキルより「情報の質」の差だった。\n\n参考にしてよかったサービスをプロフィールに。",
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
    templates = TEMPLATES.get(post_type, TEMPLATES["useful"])
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
    return t["text"]


def rewrite_x_to_bsky(x_text: str, api_key: str) -> str:
    """X投稿をBluesky用にリライト"""
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        prompt = f"""
以下のX（Twitter）の投稿文を、Bluesky用にリライトしてください。

【元のX投稿】
{x_text}

【Bluesky用のルール】
- 文字数：100〜200文字程度
- コミュニティ感を意識した、自然な会話口調
- ハッシュタグは使わない
- 同じ内容でも表現を変える（コピペにならないよう）
- 読んだ人が「わかる」「試したい」と思える内容にする
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
        return x_text  # フォールバック：元のテキストをそのまま使用


def generate_with_gemini(post_type: str, label: str, api_key: str) -> str:
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        type_instructions = {
            "useful":  "AI副業・時短・節約・生産性向上に関する役立つ情報",
            "empathy": "副業や生活改善での失敗談・体験談・共感を呼ぶ内容",
            "trivia":  "AI・テクノロジー・お金に関する意外な雑学・ネタ",
            "product": "AIツールや副業サービスを体験談として自然に紹介（広告表現禁止）",
        }
        prompt = f"""
あなたはBlueskyで副業・AI・ライフハック情報を発信しているユーザーです。

【投稿タイプ】{label}（{type_instructions[post_type]}）

【Blueskyのルール】
- 文字数：100〜200文字
- コミュニティ感を意識した自然な口調
- ハッシュタグは使わない（または1つだけ）
- 改行多めで読みやすく
- 「プロフィールに〜」で締めてもOK
- 広告っぽくしない

【構造】
1行目：興味を引く一文
↓（空行）
2〜3行：共感 or 問題提起
↓（空行）
2〜3行：解決策 or 情報
↓（空行）
最終行：まとめ（短く）

投稿文のみ出力してください。
"""
        resp = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=prompt,
        )
        return resp.text.strip()
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
    print("🦋 Bluesky 投稿プレビュー")
    print("=" * 55)

    schedule = get_today_schedule(4)
    types_cycle = ["useful", "empathy", "useful", "trivia"]

    for i, (t, pt) in enumerate(zip(schedule, types_cycle)):
        post = generate_post(force_type=pt)
        print(f"\n【{t.strftime('%H:%M')}】{post['label']} ({post['chars']}文字)")
        print("─" * 45)
        print(post["text"])

    # X→Blueskyリライトのデモ
    print("\n\n【X→Blueskyリライトデモ】")
    print("─" * 45)
    x_sample = "スマホ1台でできる副業、3選。\n\n「パソコンないから副業できない」\n\nそんなことないです。\n\n① ポイ活（月5,000円〜）\n② アンケートモニター\n③ AI画像販売\n\n全部スマホだけでOK。\n\nまず1つ試すだけで感覚つかめます✅"
    rewritten = generate_post(x_text=x_sample)
    print(f"元のX投稿 → Bluesky用リライト ({rewritten['chars']}文字)")
    print("─" * 45)
    print(rewritten["text"])
