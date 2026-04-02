"""
Gemini API — 「一人暮らし20代男性が女性ウケ商品をガチレビュー」コンテンツ生成
"""

import os
import json
import random
from google import genai
from google.genai import types

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# 楽天ルームのコメント欄は最大1000文字程度
ROOM_COMMENT_MAX = 500

# 20代男性ペルソナのバリエーション（毎回少し違うキャラにする）
PERSONAS = [
    "一人暮らし2年目の26歳エンジニア。女性向け商品はほぼ無知だが彼女へのプレゼント探しで調査中。",
    "25歳の会社員。姉に頼まれて代わりに購入 → 自分でも使ってみた正直レポ。",
    "28歳フリーランス。在宅仕事で肌荒れが増えたので女性用スキンケアに手を出し始めた男。",
    "23歳大学院生。片付け好きで部屋のインテリアに女子力高めのアイテムを取り入れ中。",
    "27歳営業マン。モテたくて女性が好きな雰囲気を研究し始めたら沼にはまった。",
]


def generate_room_review(product: dict) -> dict:
    """
    商品情報から楽天ルーム投稿用レビューを生成する。

    Returns:
        {
            "comment": str,      # 楽天ルームに投稿するコメント（500文字以内）
            "hashtags": list,    # ハッシュタグリスト
            "sns_caption": str,  # X/Bluesky シェア用キャプション
        }
    """
    if not GEMINI_API_KEY:
        print("[review_generator] GEMINI_API_KEY 未設定 → モックレビューを返す")
        return _mock_review(product)

    client = genai.Client(api_key=GEMINI_API_KEY)
    persona = random.choice(PERSONAS)

    prompt = f"""あなたは次のペルソナです:
{persona}

以下の商品を楽天ルームで紹介するコメントを書いてください。

【商品情報】
- 商品名: {product['name']}
- 価格: {product['price']}円
- カテゴリ: {product['category_name']}
- レビュー数: {product['review_count']}件 / 平均評価: {product['review_avg']}
- ショップ: {product['shop']}

【出力ルール】
1. "comment": 楽天ルーム投稿用コメント（{ROOM_COMMENT_MAX}文字以内）
   - 男性視点ならではの「最初の戸惑い → 試してみたら良かった」流れで書く
   - 具体的な使用シーンや感想を入れる（女性へのプレゼントや自分使いなど）
   - 「ガチレビュー」感を出す（欠点も正直に書く）
   - 価格の費用対効果に触れる
   - 絵文字は2〜3個まで
2. "hashtags": 5〜8個のハッシュタグ（#なしで返す）
   例: ["一人暮らし", "女性ウケ", "プレゼント"]
3. "sns_caption": X/Bluesky シェア用（140文字以内）
   - タイトルっぽく「〇〇な男が〇〇を買ってみた」という引きで始める

JSON形式のみで返すこと。```jsonブロックは不要。
"""

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.85,
                max_output_tokens=800,
            ),
        )
        text = response.text.strip()
        # JSONブロック除去
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        result = json.loads(text)
        print(f"[review_generator] レビュー生成完了: {product['name'][:30]}")
        return result
    except Exception as e:
        print(f"[review_generator] Gemini エラー: {e}")
        return _mock_review(product)


def _mock_review(product: dict) -> dict:
    return {
        "comment": (
            f"【男が買ってみた正直レポ】{product['name'][:20]}\n\n"
            f"女性向けって思って敬遠してたけど、実際に使ってみたら普通に良かった。"
            f"価格{product['price']}円でこのクオリティは正直コスパいい。"
            f"プレゼントにも使えるし、自分用にリピートしてる👍"
        ),
        "hashtags": [
            "一人暮らし男子", "女性ウケ商品", "ガチレビュー",
            "プレゼント探し", product["category_tag"], "楽天ルーム", "コスパ最高"
        ],
        "sns_caption": (
            f"女性向けと思ってスルーしてた{product['category_tag']}商品を買ってみたら"
            f"普通に神だった話。{product['price']}円→リピ確定 #ガチレビュー"
        ),
    }
