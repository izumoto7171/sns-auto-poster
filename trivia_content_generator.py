"""
AI雑学ショート コンテンツ生成
構成: フック（え？な一言）→ 解説 → オチ
"""
import random
import os

# カテゴリ別テンプレート（APIなしでも動く）
TRIVIA_TEMPLATES = {
    "雑学": [
        {
            "hook": "蚊に刺されるのは血液型O型が多い",
            "explanation": "研究によると、O型の人はA型・B型・AB型に比べて蚊に刺されやすいことが判明。蚊は皮膚から分泌される化学物質で血液型を嗅ぎ分けている。O型の人が出す分泌物が蚊を特に引き寄せるとされている。",
            "punchline": "O型のあなた、蚊除けスプレーは必須です。",
            "category": "雑学",
        },
        {
            "hook": "人間は目を開けたままくしゃみできない",
            "explanation": "くしゃみをする瞬間、脳は目を閉じるよう自動的に指令を出す。これは反射的な防御反応で、くしゃみの強力な圧力から目を守るためだとされている。意識的に目を開けようとしても、ほぼ不可能。",
            "punchline": "ぜひ今日試してみて。無理だから。",
            "category": "雑学",
        },
        {
            "hook": "バナナは木になっていない",
            "explanation": "バナナは「バナナの木」と呼ばれるが、実は草（多年生草本植物）。世界最大の草本植物のひとつで、幹に見える部分は実際には葉が重なったもの。本物の木材部分はない。",
            "punchline": "植物図鑑で確認してみよう。常識が覆る。",
            "category": "雑学",
        },
    ],
    "危険": [
        {
            "hook": "実はコンビニのレシートが超危険",
            "explanation": "多くのレシートに使われる感熱紙にはBPA（ビスフェノールA）という化学物質が含まれている。皮膚から吸収され、ホルモンバランスを乱す可能性が指摘されている。特に手が濡れているときは吸収率が大幅にアップ。",
            "punchline": "受け取ったらすぐ捨てるか、手を洗おう。",
            "category": "危険",
        },
        {
            "hook": "スマホを充電しながら使うのは実はヤバい",
            "explanation": "充電中のスマホは通常より温度が上昇する。さらに操作を加えると熱が倍増し、バッテリーの劣化を急加速させる。最悪の場合、過熱による膨張や発火事故につながるケースも報告されている。",
            "punchline": "寝る前の充電しながらスマホ操作、今日から卒業しよう。",
            "category": "危険",
        },
        {
            "hook": "毎日食べるあの食品に発がん性物質が入っている",
            "explanation": "加工肉（ソーセージ・ベーコン・ハムなど）はWHOがグループ1の発がん性物質に分類。毎日50g食べると大腸がんリスクが18%上昇するとされている。一方で適量なら問題ないとも言われており、食べ過ぎに注意が必要。",
            "punchline": "たまに食べる分にはOK。毎日ドカ食いはNG。",
            "category": "危険",
        },
    ],
    "世界のヤバい法律": [
        {
            "hook": "スイスでは日曜日に洗濯機を回すと罰せられる",
            "explanation": "スイスの一部地域では、日曜日は安息日として騒音を出す行為が禁止されている。洗濯機・芝刈り機の使用、さらには大声での会話も法律で規制されているケースがある。違反すると近隣住民から通報される。",
            "punchline": "日本に生まれてよかった、と思う瞬間。",
            "category": "世界のヤバい法律",
        },
        {
            "hook": "シンガポールでガムを噛むと最高100万円の罰金",
            "explanation": "シンガポールではガムの販売・所持が原則禁止。1992年に地下鉄のドアにガムが貼られて運行トラブルが多発したため法律で禁止された。医療用のガムは例外として薬局で買えるが、一般のチューインガムは完全アウト。",
            "punchline": "シンガポール旅行にガムを持ち込むのは絶対やめよう。",
            "category": "世界のヤバい法律",
        },
        {
            "hook": "イタリアではサンダルで運転すると違反になる",
            "explanation": "イタリアの道路交通法では、運転中は「適切なフットウェア」を着用しなければならないと定められている。サンダル・ハイヒール・裸足での運転はNG。違反すると罰金が科せられる。観光中のドライブには注意が必要。",
            "punchline": "イタリアのレンタカーは足元にも気をつけて。",
            "category": "世界のヤバい法律",
        },
    ],
    "歴史": [
        {
            "hook": "クレオパトラとティラノサウルスは同じ時代ではない",
            "explanation": "ティラノサウルスが絶滅したのは約6600万年前。クレオパトラが生きたのは約2000年前。つまりクレオパトラとティラノサウルスの間には6598万年の差がある。一方、クレオパトラとスマホの間はたった2000年。",
            "punchline": "歴史のスケール感、完全に狂う話。",
            "category": "歴史",
        },
        {
            "hook": "ピラミッドが建てられたとき、マンモスはまだ生きていた",
            "explanation": "ギザの大ピラミッドが完成したのは約4500年前。一方、最後のマンモスが絶滅したのは約4000年前とされている。つまり500年もの間、ピラミッドとマンモスが同時代に存在していた。",
            "punchline": "教科書で習う「古代」が一気に身近になる話。",
            "category": "歴史",
        },
    ],
    "科学": [
        {
            "hook": "人体の原子を全部くっつけると核爆弾になる",
            "explanation": "人体を構成する原子核の中には莫大なエネルギーが閉じ込められている。もし体内の全原子を核融合させたとすると、広島型原爆の約7倍のエネルギーが放出される計算になる。私たちは歩くエネルギー爆弾。",
            "punchline": "平和に暮らせているのは、核融合が起きないおかげ。",
            "category": "科学",
        },
        {
            "hook": "宇宙は音がしない、ではなく「音の概念がない」",
            "explanation": "音は空気などの媒質の振動で伝わる。宇宙空間はほぼ真空のため音が伝わらない。映画で宇宙船の爆発音が聞こえるのは完全なフィクション。ただし宇宙人がいて音を伝える媒質を持っていたら話は別。",
            "punchline": "映画「スター・ウォーズ」の爆発音は全部嘘。でも迫力は本物。",
            "category": "科学",
        },
    ],
}

HOOK_PREFIXES = [
    "99%が知らない",
    "え？マジで？",
    "実はコレ、ヤバい",
    "知らないと損する",
    "学校で教えない",
    "衝撃の事実",
    "信じられないけど本当",
]


def generate_with_template(category=None):
    """テンプレートから雑学コンテンツを生成"""
    if category and category in TRIVIA_TEMPLATES:
        items = TRIVIA_TEMPLATES[category]
    else:
        all_items = [item for items in TRIVIA_TEMPLATES.values() for item in items]
        items = all_items

    content = random.choice(items)
    prefix = random.choice(HOOK_PREFIXES)
    return {
        "hook": content["hook"],
        "hook_display": f"{prefix}：{content['hook']}",
        "explanation": content["explanation"],
        "punchline": content["punchline"],
        "category": content["category"],
    }


def generate_with_claude(category, api_key):
    """Claude APIで雑学コンテンツを生成"""
    try:
        import anthropic
        import json
        import re

        client = anthropic.Anthropic(api_key=api_key)

        category_examples = {
            "雑学": "「蚊に刺されやすい血液型がある」「バナナは木ではなく草」",
            "危険": "「コンビニのレシートに危険な化学物質」「充電しながらスマホを使うリスク」",
            "世界のヤバい法律": "「スイスで日曜日に洗濯機禁止」「シンガポールでガム禁止」",
            "歴史": "「ピラミッドとマンモスが同時代」「クレオパトラとティラノサウルスの時代差」",
            "科学": "「宇宙は音がない理由」「人体の原子のエネルギー量」",
        }
        example = category_examples.get(category, "驚きの雑学")

        prompt = f"""TikTok向けの「{category}」ジャンルの雑学ショート動画の台本を作成してください。
例: {example}

以下のJSON形式のみ出力してください（説明文不要）：
{{
  "hook": "え？ってなる衝撃的な一文（30文字以内）",
  "explanation": "わかりやすい解説（100〜150文字）",
  "punchline": "オチ・まとめの一言（40文字以内）",
  "category": "{category}"
}}

条件：
- hookは「99%が知らない」「実は○○は危険」「マジで？」となるような衝撃的な事実
- explanationは中学生でもわかる言葉で
- punchlineは「だから○○しよう」「○○に気をつけて」など行動や驚きで締める
- 必ず実在する事実か、科学的に根拠のある話にする
- 日本語で
"""
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text.strip()

        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            prefix = random.choice(HOOK_PREFIXES)
            data["hook_display"] = f"{prefix}：{data['hook']}"
            return data
        else:
            return generate_with_template(category)

    except Exception as e:
        print(f"⚠️ Claude API失敗、テンプレートを使用: {e}")
        return generate_with_template(category)


def generate_with_gemini(category, api_key):
    """Gemini APIで雑学コンテンツを生成"""
    try:
        from google import genai
        import json
        import re

        client = genai.Client(api_key=api_key)

        prompt = f"""TikTok向けの「{category}」ジャンルの雑学ショート動画の台本を作成してください。

以下のJSON形式のみ出力してください（説明文不要）：
{{
  "hook": "え？ってなる衝撃的な一文（30文字以内）",
  "explanation": "わかりやすい解説（100〜150文字）",
  "punchline": "オチ・まとめの一言（40文字以内）",
  "category": "{category}"
}}

条件：
- hookは衝撃的な事実
- explanationは中学生でもわかる言葉で
- punchlineは行動や驚きで締める
- 日本語で
"""
        response = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=prompt,
        )
        text = response.text.strip()

        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            prefix = random.choice(HOOK_PREFIXES)
            data["hook_display"] = f"{prefix}：{data['hook']}"
            return data
        else:
            return generate_with_template(category)

    except Exception as e:
        print(f"⚠️ Gemini API失敗、テンプレートを使用: {e}")
        return generate_with_template(category)


CATEGORIES = list(TRIVIA_TEMPLATES.keys())


def generate_trivia(category=None):
    """メインの雑学生成関数（APIキーがあればAI、なければテンプレート）"""
    if not category:
        category = random.choice(CATEGORIES)

    claude_key = os.getenv("ANTHROPIC_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")

    if claude_key:
        print(f"✅ Claude APIで雑学生成中: [{category}]")
        return generate_with_claude(category, claude_key)
    elif gemini_key:
        print(f"✅ Gemini APIで雑学生成中: [{category}]")
        return generate_with_gemini(category, gemini_key)
    else:
        print(f"✅ テンプレートで雑学生成: [{category}]")
        return generate_with_template(category)


if __name__ == "__main__":
    for cat in CATEGORIES:
        print(f"\n=== {cat} ===")
        content = generate_trivia(cat)
        print(f"フック: {content['hook_display']}")
        print(f"解説: {content['explanation']}")
        print(f"オチ: {content['punchline']}")
