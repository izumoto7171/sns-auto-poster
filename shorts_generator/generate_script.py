"""
台本生成 - Claude API優先、Gemini APIフォールバック
"""
import json
import re
from config import CLAUDE_API_KEY, GEMINI_API_KEY

PROMPT_TEMPLATE = """あなたはYouTube Shortsのバズる台本ライターです。
以下の条件で台本をJSON形式のみで出力してください。

テーマ：{theme}
条件：
- 冒頭3秒以内に視聴者を引きつける驚きまたは疑問を入れる
- 全体30秒以内に収まるセリフ量にする
- 口語・話し言葉で書く（です/ます調は避ける）
- キャラクターが喋っているような感情のあるセリフにする
- image_promptは縦9:16、Pixar風3Dキャラクター、背景はリアルな環境で書く
- JSON以外は一切出力しない

出力形式：
{{
  "title": "動画タイトル（25文字以内）",
  "hook": "冒頭0〜3秒のセリフ（驚き・疑問形）",
  "sections": [
    {{
      "text": "テロップに表示するテキスト",
      "voice": "VOICEVOX音声に渡すセリフ",
      "duration": 5
    }}
  ],
  "cta": "最後のCTA（チャンネル登録お願いします 等）",
  "image_prompt": "Leonardo.ai用の英語プロンプト（3Dキャラ・Pixarスタイル）",
  "hashtags": ["#雑学", "#豆知識", "#Shorts"]
}}"""


def _extract_json(text: str) -> dict:
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError("JSONが見つかりません")


def generate_with_claude(theme: str) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": PROMPT_TEMPLATE.format(theme=theme)}],
    )
    return _extract_json(message.content[0].text)


def generate_with_gemini(theme: str) -> dict:
    from google import genai
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model="gemini-2.0-flash-lite",
        contents=PROMPT_TEMPLATE.format(theme=theme),
    )
    return _extract_json(response.text)


def generate_fallback(theme: str) -> dict:
    """APIなしのフォールバック台本"""
    return {
        "title": theme[:25],
        "hook": f"え、{theme}って知ってた？",
        "sections": [
            {"text": f"実は{theme}には驚きの事実がある", "voice": f"実は{theme}には驚きの事実があるんだ", "duration": 5},
            {"text": "研究で証明されているんだけど", "voice": "これ、ちゃんと研究で証明されてるんだよ", "duration": 5},
            {"text": "知らないと損する情報だよ", "voice": "知らないと絶対損するから覚えておいて", "duration": 5},
        ],
        "cta": "チャンネル登録して次の動画も見てね！",
        "image_prompt": f"Pixar style 3D character explaining {theme}, colorful background, 9:16 vertical",
        "hashtags": ["#雑学", "#豆知識", "#Shorts"],
    }


def generate_script(theme: str) -> dict:
    if CLAUDE_API_KEY:
        try:
            print(f"✍️  Claude APIで台本生成: {theme}")
            return generate_with_claude(theme)
        except Exception as e:
            print(f"⚠️  Claude失敗: {e}")

    if GEMINI_API_KEY:
        try:
            print(f"✍️  Gemini APIで台本生成: {theme}")
            return generate_with_gemini(theme)
        except Exception as e:
            print(f"⚠️  Gemini失敗: {e}")

    print(f"✍️  フォールバック台本を使用: {theme}")
    return generate_fallback(theme)
