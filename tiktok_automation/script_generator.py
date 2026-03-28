"""
ショート動画台本 + 画像プロンプト 自動生成
Gemini APIを使ってTikTok/Reels向け10秒台本とキャラクター画像プロンプトを生成する
"""
import os
import json
import random
from datetime import datetime
from pathlib import Path

# ─────────────────────────────────────────
# テーマ設定（ライフハック系・バズりやすいもの）
# ─────────────────────────────────────────
THEMES = [
    {"category": "掃除", "topic": "鏡のウロコ汚れが5秒で落ちる裏技"},
    {"category": "掃除", "topic": "排水口の臭いを即消しする方法"},
    {"category": "掃除", "topic": "レンジの油汚れをラップだけで落とす"},
    {"category": "収納", "topic": "100均グッズで冷蔵庫を2倍使いやすくする"},
    {"category": "収納", "topic": "クローゼットが劇的に広くなる畳み方"},
    {"category": "収納", "topic": "シンク下収納を3倍に増やすテク"},
    {"category": "料理", "topic": "玉ねぎを涙なしで切る最速テク"},
    {"category": "料理", "topic": "炊飯器だけで作れる絶品チーズケーキ"},
    {"category": "料理", "topic": "お弁当が10分で作れる時短術"},
    {"category": "美容", "topic": "寝る前3分でむくみ顔がすっきりするマッサージ"},
    {"category": "美容", "topic": "乾燥肌が1週間で変わる洗顔方法"},
    {"category": "健康", "topic": "デスクワーカーの肩こりが即解消するストレッチ"},
    {"category": "健康", "topic": "寝つきが悪い人に試してほしい睡眠術"},
]

LINE_STAMP_URL = "https://store.line.me/search/sticker/ja?q=lifehack"  # 実際のスタンプURLに変更


def load_env():
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


def load_affiliate_links() -> dict:
    links_path = Path(__file__).parent / "affiliate_links.json"
    with open(links_path, encoding="utf-8") as f:
        return json.load(f)


def generate_script_and_prompt(theme: dict) -> dict:
    """Geminiで台本と画像プロンプトを生成"""
    try:
        from google import genai
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

        prompt = f"""あなたはTikTok・Reelsバズり専門のクリエイターです。

テーマ: 【{theme['category']}】{theme['topic']}

以下の形式でJSONを出力してください（他の文章は一切不要）:

{{
  "script": {{
    "hook": "最初の2秒で視聴者を引き込む一言（例: 知らないと損！鏡の掃除、間違えてます）",
    "step1": "ステップ1の説明（1文・15文字以内）",
    "step2": "ステップ2の説明（1文・15文字以内）",
    "step3": "ステップ3の説明（1文・15文字以内）",
    "cta": "行動喚起（保存して・コメントで・スタンプも等）"
  }},
  "image_prompt": "Cute anime girl character with big eyes, doing {theme['category']} task, kawaii style, clean background, 9:16 vertical format, vibrant colors, TikTok thumbnail style, ultra detailed",
  "hashtags": ["#{theme['category']}", "#ライフハック", "#裏技", "#知らなきゃ損", "#TikTok"],
  "sns_caption": "SNS投稿用キャプション（50文字以内・絵文字あり）"
}}"""

        response = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=prompt,
        )
        text = response.text.strip()
        # JSONブロック抽出
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        return json.loads(text)

    except Exception as e:
        print(f"⚠️ Gemini失敗、テンプレート使用: {e}")
        return _fallback_content(theme)


def _fallback_content(theme: dict) -> dict:
    """Gemini失敗時のフォールバックテンプレート"""
    return {
        "script": {
            "hook": f"知らないと損！{theme['topic']}",
            "step1": "まず準備するのはこれだけ",
            "step2": "あとはこすって待つだけ",
            "step3": "たった30秒でこの仕上がり",
            "cta": "保存して後で試してみて！"
        },
        "image_prompt": f"Cute anime girl character with big eyes, doing {theme['category']} cleaning task, kawaii style, clean white background, 9:16 vertical format, vibrant pastel colors, TikTok thumbnail style",
        "hashtags": [f"#{theme['category']}", "#ライフハック", "#裏技", "#知らなきゃ損"],
        "sns_caption": f"✨ {theme['topic']}【保存推奨】"
    }


def build_sns_post(theme: dict, content: dict, affiliate_links: dict) -> dict:
    """SNS投稿文を組み立てる（アフィリエイト＋LINEスタンプ誘導付き）"""
    script = content["script"]
    hashtags = " ".join(content["hashtags"][:5])
    caption = content.get("sns_caption", f"✨ {theme['topic']}")

    # カテゴリに対応するアフィリエイトリンクを選ぶ
    links = affiliate_links.get(theme["category"], affiliate_links["デフォルト"])
    link = links[0]  # 最初のリンクを使用

    # X/Bluesky向け（140文字以内）
    short_text = (
        f"{caption}\n\n"
        f"🎬 {script['hook']}\n"
        f"① {script['step1']}\n"
        f"② {script['step2']}\n"
        f"③ {script['step3']}\n\n"
        f"👇 使った道具はこちら\n{link['url']}\n\n"
        f"{hashtags}"
    )

    # note/はてな向け（長文）
    long_text = f"""## {theme['topic']}

{script['hook']}

### やり方

1. {script['step1']}
2. {script['step2']}
3. {script['step3']}

### 使ったもの

**[{link['name']}（{link['price']}）]({link['url']})**

---

### 💬 LINEスタンプも配布中！

このキャラクターのLINEスタンプを無料配布しています。
気に入ったらぜひ使ってください😊

👉 [LINEスタンプをダウンロード]({LINE_STAMP_URL})

---

{hashtags}
"""

    return {
        "theme": theme,
        "script": script,
        "image_prompt": content["image_prompt"],
        "short_text": short_text,
        "long_text": long_text,
        "affiliate": link,
        "hashtags": content["hashtags"],
    }


def generate(category: str = None) -> dict:
    """今日のショート動画コンテンツを生成して返す"""
    load_env()
    affiliate_links = load_affiliate_links()

    # テーマ選択（カテゴリ指定があれば絞り込み）
    pool = [t for t in THEMES if t["category"] == category] if category else THEMES
    theme = random.choice(pool)

    print(f"🎬 テーマ: 【{theme['category']}】{theme['topic']}")

    content = generate_script_and_prompt(theme)
    post = build_sns_post(theme, content, affiliate_links)

    print(f"✅ 台本生成完了")
    print(f"   Hook: {post['script']['hook']}")
    print(f"   画像プロンプト: {post['image_prompt'][:60]}...")

    return post


def save_output(post: dict):
    """生成コンテンツをJSONで保存"""
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)

    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = output_dir / f"script_{date_str}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(post, f, ensure_ascii=False, indent=2)
    print(f"💾 保存: {out_path}")
    return out_path


if __name__ == "__main__":
    import sys
    load_env()

    cmd = sys.argv[1] if len(sys.argv) > 1 else "generate"

    if cmd == "generate":
        post = generate()
        save_output(post)

        print("\n" + "=" * 50)
        print("📱 SNS投稿文（X/Bluesky）:")
        print("=" * 50)
        print(post["short_text"])

        print("\n" + "=" * 50)
        print("🖼️  画像生成プロンプト（Nano Banana 2 等に貼る）:")
        print("=" * 50)
        print(post["image_prompt"])

    elif cmd == "post":
        # SNSに直接投稿
        post = generate()
        save_output(post)
        _post_to_sns(post)
