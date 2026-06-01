"""
一人暮らしライフハック 投稿テキスト生成（Gemini API）
テーマ1行 → 4枚画像用テキスト + X投稿本文を返す
"""
import json
import os
import re
import sys
from pathlib import Path


# デフォルトテーマリスト（テーマ未指定時にランダム選択）
DEFAULT_THEMES = [
    "tower マグネット収納ラック（¥2,980）と山崎実業の洗剤ボトル（¥1,200）、キッチン整理テーマ",
    "無印良品 ポリプロピレン収納ボックス、クローゼット整理テーマ",
    "山崎実業 ドライヤーホルダー（¥1,500）と洗面台収納グッズ、洗面台すっきりテーマ",
    "ニトリ シューズラック（¥3,000）と玄関マット、玄関整理テーマ",
    "ケーブル収納ボックス（¥1,800）とケーブルクリップ、デスク周りすっきりテーマ",
    "珪藻土バスマット（¥2,000）とシャンプーラック（¥1,500）、浴室収納テーマ",
    "冷蔵庫収納トレー（¥800×3）と野菜ケース（¥600）、冷蔵庫整理テーマ",
    "折りたたみテーブル（¥5,000）とチェア、6畳部屋の省スペーステーマ",
]

GEMINI_PROMPT_TEMPLATE = """
あなたは「一人暮らしのライフハック・QOL向上」を発信するXアカウントの投稿クリエイターです。
以下のルールを100%守って、画像テキスト（4枚分）とXの投稿本文をJSON形式で出力してください。

# 今回のテーマ・商品
{theme}

# 絶対に守るルール
- 1枚の画像に含める情報は最大3点まで
- ターゲット：20〜30代前半の一人暮らし、または新生活を始める人
- 文体：友人に話しかけるような口語体（「です・ます」は使わない）
- 価格は必ず記載する

# タイトルはいずれかのパターンを使うこと
① 数字 × 意外性（例：「歴5年が本当に買ってよかった3選」）
② 後悔フォーマット（例：「引っ越し初日に買えばよかった」）
③ 比較 × 決断支援（例：「3,000円 vs 800円。正直どっちでも良かった話」）
④ 共感 × 解決予告（例：「部屋が狭くてストレス。→ これで解決した」）
⑤ ランキング × 限定感（例：「QOL上がった買い物、正直ランキング」）

# 出力フォーマット（JSONのみ。余分なテキスト・マークダウンコードブロックは不要）
{{
  "cover": {{
    "category": "カテゴリ名（10文字以内・英字大文字でも可）",
    "title": "メインタイトル（改行は\\nで表現、2行以内）",
    "sub_copy": "サブコピー（ターゲット明示、30文字以内）"
  }},
  "item1": {{
    "item_name": "商品名（20文字以内）",
    "points": ["ポイント1（25文字以内）", "ポイント2（25文字以内）", "ポイント3（25文字以内）"],
    "price": "¥X,XXX"
  }},
  "item2": {{
    "item_name": "商品名（20文字以内）",
    "points": ["ポイント1（25文字以内）", "ポイント2（25文字以内）", "ポイント3（25文字以内）"],
    "price": "¥X,XXX"
  }},
  "summary": {{
    "items": ["アイテム1の短い名前", "アイテム2の短い名前"]
  }},
  "x_post": "Xに投稿する本文（改行は\\nで表現）。構成：①共感・問いかけ1〜2行 → ②予告1〜2行 → ③本文3〜5行 → ④区切り線（──────）→ ⑤プロフ誘導（📦 購入リンクはプロフへ\\n保存で後から見返せます）→ ⑥区切り線 → ⑦ハッシュタグ5〜7個（#一人暮らし #QOL向上 #買ってよかったもの を必ず含む）"
}}
"""


def generate_with_gemini(theme: str):
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from money_agent.gemini_client import generate as gemini_generate
    except ImportError:
        print("⚠️ gemini_client が見つかりません")
        return None

    try:
        prompt = GEMINI_PROMPT_TEMPLATE.format(theme=theme)
        raw = gemini_generate(prompt, use_cache=False, temperature=0.85)
        if not raw:
            return None

        # コードブロック除去
        raw = raw.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        data = json.loads(raw)
        _validate(data)
        return data

    except json.JSONDecodeError as e:
        print(f"⚠️ JSONパースエラー: {e}")
        return None
    except Exception as e:
        print(f"⚠️ Gemini生成エラー: {e}")
        return None


def _validate(data: dict):
    required = ["cover", "item1", "item2", "summary", "x_post"]
    for key in required:
        if key not in data:
            raise ValueError(f"レスポンスに '{key}' が含まれていません")
    cover = data["cover"]
    if not all(k in cover for k in ["category", "title", "sub_copy"]):
        raise ValueError("cover の構造が不正")
    for item_key in ["item1", "item2"]:
        item = data[item_key]
        if not all(k in item for k in ["item_name", "points", "price"]):
            raise ValueError(f"{item_key} の構造が不正")
        if len(item["points"]) < 1:
            raise ValueError(f"{item_key}.points が空")
    if "items" not in data["summary"]:
        raise ValueError("summary.items が見つかりません")


def generate_post_data(theme=None):
    """
    テーマを渡すと4枚画像用テキスト+投稿文を返す。
    テーマ未指定の場合はデフォルトリストからランダム選択。

    Returns:
        dict（画像生成・投稿に必要なデータ）or None（失敗時）
    """
    import random
    if not theme:
        theme = random.choice(DEFAULT_THEMES)
        print(f"[テーマ自動選択] {theme}")
    else:
        print(f"[テーマ] {theme}")

    # リトライ最大2回
    for attempt in range(2):
        data = generate_with_gemini(theme)
        if data:
            return data
        if attempt == 0:
            print("[リトライ] Gemini再呼び出し...")

    print("❌ テキスト生成失敗")
    return None


if __name__ == "__main__":
    theme = sys.argv[1] if len(sys.argv) > 1 else None
    data = generate_post_data(theme)
    if data:
        print(json.dumps(data, ensure_ascii=False, indent=2))
