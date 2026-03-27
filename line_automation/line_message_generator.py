#!/usr/bin/env python3
"""
LINE Bot ステップ配信メッセージ生成
戦略: 1〜5日目のシナリオを自動生成
"""

import os
import json
import random
from datetime import datetime

# ============================
# 5日間ステップ配信テンプレート
# ============================

STEP_TEMPLATES = {
    1: {
        "theme": "AI副業の基本情報",
        "messages": [
            """こんにちは！🎉
LINE登録ありがとうございます！

ここでは「AIを使って副業で稼ぐ方法」を
5日間でお伝えします✨

まず今日は基本から👇

【AI副業って何？】
AIツールを使って
・文章を書く
・画像を作る
・翻訳する
・データ整理

これらの作業を代行するだけで
月1〜5万円が狙えます💡

明日は具体的なツールを紹介しますね！""",
            """【AI副業の良いところ】

✅ 初期費用ほぼゼロ
✅ スキルは後からでもOK
✅ スマホだけでもできる
✅ 副業禁止でもバレにくい

特にChatGPTやGeminiは
無料から使えるので
まずは試すだけでOK🙆‍♂️

気になることがあれば
いつでも返信してください！"""
        ]
    },
    2: {
        "theme": "おすすめAIツール紹介",
        "messages": [
            """2日目です！☀️

今日はおすすめのAIツールを
一挙紹介します👇

━━━━━━━━━━━
📝 文章系
━━━━━━━━━━━
・ChatGPT（無料〜）
・Gemini（完全無料）
・Claude（無料〜）

━━━━━━━━━━━
🎨 画像系
━━━━━━━━━━━
・Midjourney（月10$〜）
・DALL-E（ChatGPT内）
・Canva AI（無料〜）

全部無料から始められます🎯""",
            """【どこで稼ぐ？】

AIで作ったものを売る場所👇

📌 クラウドソーシング
→ ランサーズ・クラウドワークス

📌 SNS集客
→ X・Instagram・TikTok

📌 ブログ・note
→ 記事を書いて広告収入

まずはクラウドソーシングが
一番稼ぎやすいです💪

明日は実際の使い方を紹介！"""
        ]
    },
    3: {
        "theme": "実際の使い方",
        "messages": [
            """3日目です！🔥

今日は実際の手順を説明します

【AI記事代行の始め方】

1️⃣ ChatGPTに登録（無料）
2️⃣ ランサーズに登録（無料）
3️⃣ 「記事作成」で案件検索
4️⃣ 提案文を送る
5️⃣ 受注したらAIで執筆

これだけです！

最初は1記事500〜2000円から
慣れると5000円以上も狙えます💰""",
            """【ChatGPTの使い方（超簡単）】

例えば記事の依頼があったら

「〇〇について2000文字の記事を
書いてください。
初心者向けにわかりやすく。」

これだけ入力すればOK✅

あとは自分で少し修正して提出

最初から完璧じゃなくていい！
やりながら上手くなります😊

明日は成功例を紹介しますね！"""
        ]
    },
    4: {
        "theme": "体験談・成功例",
        "messages": [
            """4日目です！💫

今日は実際の成功例を紹介

━━━━━━━━━━━
Aさん（主婦・30代）
━━━━━━━━━━━
育児の隙間時間に
AI記事代行を開始

3ヶ月で月3万円達成✨

━━━━━━━━━━━
Bさん（会社員・20代）
━━━━━━━━━━━
残業後に1日1〜2時間

半年で月8万円の副収入

本業より稼いだ月もあるとか😳""",
            """【成功のポイント】

✅ 最初は安くても受注する
✅ とにかく数をこなす
✅ お客様の評価を集める
✅ 単価を少しずつ上げる

最初の1ヶ月は練習と思って
とにかく行動することが大事！

「完璧にやろう」より
「まず1件やる」が正解🎯

明日は私のおすすめサービスを
紹介しますね！"""
        ]
    },
    5: {
        "theme": "おすすめサービス紹介",
        "messages": [
            """最終日（5日目）です！🎊

5日間読んでくれてありがとう！

今日は私が実際に使って
良かったサービスを紹介します

【AI副業を加速するツール】

📌 Brain（情報商材プラットフォーム）
AI副業の教材が多数あります
→ 無料〜有料まで様々

📌 note
自分の知識を販売できる
最初の1記事は無料で書ける✅

📌 ランサーズPro
より単価の高い案件に応募可能
審査が通れば月10万以上も！""",
            """【まとめ・最後に】

5日間お疲れ様でした！🌟

AI副業の流れ、わかりましたか？

迷っている人へ👇

最初の一歩が一番大事です
完璧じゃなくていい
まず登録・まず1件応募

それだけで人生変わります✨

これからも役立つ情報を
不定期で送りますね！

何か質問があれば
いつでも返信してください😊"""
        ]
    }
}

# ============================
# SNS → LINE誘導文テンプレート
# ============================

SNS_LEAD_TEMPLATES = [
    # X用（短め）
    {
        "platform": "X",
        "type": "direct",
        "text": """AI副業で月3万円稼ぐ方法を
LINEで5日間無料でお伝えしています📱

✅ 初期費用ゼロ
✅ スマホだけでOK
✅ 副業初心者向け

↓ 登録はプロフィールから
（完全無料）"""
    },
    {
        "platform": "X",
        "type": "value_first",
        "text": """ChatGPTで記事を書いて
月5万円を稼ぐ手順👇

1. 無料登録
2. 案件を探す
3. AIで執筆
4. 提出→報酬

詳しい方法はLINEで解説中🔗
（プロフィールのリンクから）"""
    },
    # note/はてな誘導用
    {
        "platform": "note",
        "type": "article_cta",
        "text": """もっと詳しい手順を
LINEで5日間無料配信中です📩

✅ Day1: AI副業の基本
✅ Day2: ツール紹介
✅ Day3: 実際の手順
✅ Day4: 成功事例
✅ Day5: おすすめサービス

下のリンクから登録できます👇"""
    }
]

def generate_step_messages(day=None):
    """指定した日のステップメッセージを返す（全日指定なしで全件）"""
    if day:
        step = STEP_TEMPLATES.get(day)
        if step:
            return {day: step}
        return {}
    return STEP_TEMPLATES

def generate_sns_lead_text(platform="X", lead_type=None):
    """SNS誘導文を生成"""
    candidates = [t for t in SNS_LEAD_TEMPLATES if t["platform"] == platform]
    if lead_type:
        candidates = [t for t in candidates if t["type"] == lead_type]
    if not candidates:
        candidates = SNS_LEAD_TEMPLATES
    return random.choice(candidates)["text"]

def generate_with_gemini(theme, message_type, api_key):
    """Gemini APIでメッセージ生成"""
    try:
        from google import genai
        client = genai.Client(api_key=api_key)

        prompt = f"""LINEのステップ配信メッセージを作成してください。

テーマ: {theme}
メッセージタイプ: {message_type}

条件:
- 200〜400文字
- 改行を多めに使う
- 絵文字を適度に使う
- 親しみやすいトーン
- 押し売りしない
- AI副業・副業・稼ぐ方法に関する内容
- リンクは「プロフィールから」と書く

メッセージ本文のみ出力してください。"""

        response = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        return None

def generate_welcome_message():
    """登録直後のウェルカムメッセージ"""
    return """ご登録ありがとうございます！🎉

ここでは「AIを使った副業で稼ぐ方法」を
5日間でお伝えします✨

✅ 初期費用ゼロ
✅ 完全初心者OK
✅ スマホだけでも可

これから毎日1〜2通
役立つ情報をお届けします！

まずは今日の基本情報を
次のメッセージで送りますね👇"""

def save_scenarios(output_path="line_automation/step_scenarios.json"):
    """ステップシナリオをJSONで保存"""
    scenarios = {
        "generated_at": datetime.now().isoformat(),
        "welcome": generate_welcome_message(),
        "steps": STEP_TEMPLATES,
        "sns_lead": SNS_LEAD_TEMPLATES
    }

    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(scenarios, f, ensure_ascii=False, indent=2)

    print(f"✅ シナリオ保存: {output_path}")
    return scenarios

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "save":
            save_scenarios()
        elif sys.argv[1] == "preview":
            day = int(sys.argv[2]) if len(sys.argv) > 2 else 1
            step = STEP_TEMPLATES.get(day, {})
            print(f"\n=== Day{day}: {step.get('theme', '')} ===")
            for i, msg in enumerate(step.get("messages", []), 1):
                print(f"\n--- メッセージ{i} ---")
                print(msg)
        elif sys.argv[1] == "sns":
            platform = sys.argv[2] if len(sys.argv) > 2 else "X"
            print(f"\n=== {platform}用LINE誘導文 ===")
            print(generate_sns_lead_text(platform))
        elif sys.argv[1] == "welcome":
            print("\n=== ウェルカムメッセージ ===")
            print(generate_welcome_message())
    else:
        print("使い方:")
        print("  python3 line_message_generator.py preview [1-5]  # ステップ確認")
        print("  python3 line_message_generator.py sns [X/note]   # SNS誘導文")
        print("  python3 line_message_generator.py welcome         # ウェルカム")
        print("  python3 line_message_generator.py save            # JSON保存")
