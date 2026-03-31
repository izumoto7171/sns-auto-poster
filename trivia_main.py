"""
AI雑学ショート 自動生成ツール
使い方:
  python3 trivia_main.py              # 1本生成（カテゴリランダム）
  python3 trivia_main.py 10           # 10本生成
  python3 trivia_main.py 20 危険      # 20本・危険カテゴリ固定
  python3 trivia_main.py 30 all       # 全カテゴリから30本
"""
import os
import sys
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

from trivia_content_generator import generate_trivia, CATEGORIES
from trivia_video_creator import create_trivia_video


def main():
    print("=" * 50)
    print("🧠 AI雑学ショート 自動生成")
    print("=" * 50)

    # 引数パース
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    category_arg = sys.argv[2] if len(sys.argv) > 2 else None

    if category_arg == "all" or category_arg is None:
        fixed_category = None
        print(f"📂 カテゴリ: ランダム（{', '.join(CATEGORIES)}）")
    elif category_arg in CATEGORIES:
        fixed_category = category_arg
        print(f"📂 カテゴリ: {fixed_category}")
    else:
        print(f"⚠️ 不明なカテゴリ: {category_arg}")
        print(f"   使えるカテゴリ: {', '.join(CATEGORIES)}")
        fixed_category = None

    print(f"📹 生成本数: {count}本")

    # 出力フォルダ
    output_dir = "./output/trivia"
    os.makedirs(output_dir, exist_ok=True)

    # BGM
    bgm_path = os.path.join(os.path.dirname(__file__), "bgm_chord.mp3")
    if not os.path.exists(bgm_path):
        bgm_path = None

    generated = []

    for i in range(count):
        print(f"\n--- 動画 {i+1}/{count} ---")

        # コンテンツ生成
        print("✍️  台本生成中...")
        content = generate_trivia(fixed_category)
        print(f"   フック: {content.get('hook_display', content.get('hook', ''))[:40]}")
        print(f"   カテゴリ: {content.get('category', '雑学')}")

        # 動画生成
        print("🎬 動画生成中...")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        cat_slug = content.get("category", "trivia").replace(" ", "_").replace("の", "")
        output_path = f"{output_dir}/{cat_slug}_{timestamp}_{i+1}.mp4"
        create_trivia_video(content, output_path, duration=15, bgm_path=bgm_path)
        generated.append((output_path, content))

    # 完了サマリー
    print("\n" + "=" * 50)
    print(f"✅ 完了！ {len(generated)}本の雑学ショートを生成")
    print("=" * 50)
    for path, c in generated:
        category = c.get("category", "")
        hook = c.get("hook", "")[:30]
        print(f"  📹 [{category}] {hook}...")
        print(f"      → {path}")
    print()
    print("TikTok / YouTube Shorts / Instagram Reels にアップロードしてください！")
    print("=" * 50)


if __name__ == "__main__":
    main()
