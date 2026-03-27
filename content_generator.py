"""
ライフハックのコンテンツを生成
Gemini APIキーがあれば使う、なければテンプレートを使用
"""
import random
import os

# テンプレートベースのライフハック（APIなしでも動く）
LIFEHACK_TEMPLATES = {
    "時短": [
        {
            "title": "朝の準備が3分短くなる方法",
            "tips": [
                "前日夜に服を選んでおく",
                "朝食はスムージーにまとめる",
                "カバンの中身は毎晩リセット"
            ]
        },
        {
            "title": "料理が倍速になる5つの裏技",
            "tips": [
                "野菜は週末にまとめカット",
                "冷凍食材を上手に活用",
                "調味料は計量せずに目分量で慣れる",
                "電子レンジを積極的に使う",
                "洗い物は料理中に並行して減らす"
            ]
        }
    ],
    "節約": [
        {
            "title": "月1万円節約できる買い物術",
            "tips": [
                "買い物リストを作ってから行く",
                "空腹時のスーパーは避ける",
                "プライベートブランドを活用する"
            ]
        },
        {
            "title": "電気代を自動で下げる方法",
            "tips": [
                "待機電力をコンセントから抜く",
                "エアコンは自動運転モードが最安",
                "LED電球に全部変える"
            ]
        }
    ],
    "睡眠": [
        {
            "title": "寝つきが劇的に良くなる習慣",
            "tips": [
                "寝る1時間前はスマホをやめる",
                "室温は18〜20度が最適",
                "足を温めると眠くなる"
            ]
        }
    ],
    "集中力": [
        {
            "title": "集中力が2倍になるデスク環境",
            "tips": [
                "机の上は必要なものだけ",
                "25分作業＋5分休憩のポモドーロ法",
                "作業前に水を一杯飲む"
            ]
        }
    ],
    "掃除": [
        {
            "title": "部屋が常にキレイになる1日5分術",
            "tips": [
                "使ったらすぐ元の場所に戻す",
                "1日1箇所だけ集中して掃除",
                "床にものを置かないルールを作る"
            ]
        }
    ]
}

def generate_with_template(keyword=None):
    """テンプレートからライフハックを生成"""
    # キーワードに合うカテゴリを探す
    category = None
    if keyword:
        for cat in LIFEHACK_TEMPLATES:
            if cat in keyword:
                category = cat
                break

    # 合うカテゴリがなければランダム
    if not category:
        category = random.choice(list(LIFEHACK_TEMPLATES.keys()))

    content = random.choice(LIFEHACK_TEMPLATES[category])
    return content

def generate_with_gemini(keyword, api_key):
    """Gemini APIでライフハックを生成（google-genai SDK使用）"""
    try:
        from google import genai
        import json, re

        client = genai.Client(api_key=api_key)

        prompt = f"""
「{keyword}」に関するTikTok向けライフハック動画のスクリプトを作成してください。

以下のJSON形式のみ出力してください（説明文不要）：
{{
  "title": "タイトル（20文字以内）",
  "tips": ["ライフハック1", "ライフハック2", "ライフハック3"]
}}

条件：
- タイトルは思わずタップしたくなるもの（「知らないと損！」「99%が知らない」など）
- ライフハックは3〜5個
- 1つのライフハックは30文字以内
- 日本語で
"""
        response = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=prompt,
        )
        text = response.text.strip()

        # JSON部分を抽出
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        else:
            return generate_with_template(keyword)

    except Exception as e:
        print(f"⚠️ Gemini API失敗、テンプレートを使用: {e}")
        return generate_with_template(keyword)

def generate_content(keyword=None):
    """メインの生成関数（APIキーがあればGemini、なければテンプレート）"""
    api_key = os.getenv("GEMINI_API_KEY")

    if api_key:
        print(f"✅ Gemini APIでコンテンツ生成中: {keyword}")
        return generate_with_gemini(keyword, api_key)
    else:
        print(f"✅ テンプレートでコンテンツ生成: {keyword}")
        return generate_with_template(keyword)

if __name__ == "__main__":
    content = generate_content("時短術")
    print("生成されたコンテンツ:")
    print(f"タイトル: {content['title']}")
    print(f"ヒント: {content['tips']}")
