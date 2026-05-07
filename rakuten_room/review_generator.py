"""
Gemini API — 一人暮らし男性向け商品レビュー生成（節約・生活術テーマ）
"""

import os
import json
import random
from google import genai
from google.genai import types

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# 楽天ルームのコメント欄は最大1000文字程度
ROOM_COMMENT_MAX = 500

# 一人暮らし男性ペルソナのバリエーション
PERSONAS = [
    "一人暮らし2年目の26歳エンジニア。食費と日用品費を月2万円以下に抑えることを目標にしている節約男。",
    "25歳の会社員。自炊を始めて3ヶ月。コスパ重視で楽天をよく使う。作り置き派。",
    "28歳フリーランス。在宅メインなので生活用品・家電には投資する主義。レビューを読み込んでから買う慎重派。",
    "23歳大学院生。奨学金返済中で毎月の出費を細かく管理。コスパの鬼。",
    "27歳転職したての会社員。新生活で必要なものを一から揃え中。失敗した買い物も多いので正直レポを書く。",
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
   - 一人暮らし男性目線の「買う前の迷い → 使ってみた正直な感想」で書く
   - 節約・コスパ・時短・生活の質向上など具体的な観点を入れる
   - 「ガチレビュー」感を出す（欠点も正直に書く）
   - 価格の費用対効果に触れる
   - 絵文字は2〜3個まで
2. "hashtags": 5〜8個のハッシュタグ（#なしで返す）
   例: ["一人暮らし", "節約", "コスパ最高"]
3. "sns_caption": X/Bluesky シェア用（140文字以内）
   - 「一人暮らし男が〇〇買ってみた」「月○円節約できた」など引きになるフレーズで始める

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
            f"【一人暮らし男の正直レポ】{product['name'][:20]}\n\n"
            f"正直最初は必要か迷ってたけど、使い始めたら生活の質が上がった。"
            f"価格{product['price']}円でこのクオリティはコスパ高い。"
            f"一人暮らしには十分すぎる性能👍"
        ),
        "hashtags": [
            "一人暮らし", "節約", "コスパ最高",
            "一人暮らし男子", product["category_tag"], "楽天ルーム", "生活術"
        ],
        "sns_caption": (
            f"一人暮らし男が{product['category_tag']}に{product['price']}円かけてみた正直レポ。"
            f"結論: 買って正解だった #一人暮らし"
        ),
    }
