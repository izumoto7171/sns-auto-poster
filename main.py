"""
TikTok ライフハック動画 自動生成ツール
使い方: python3 main.py
"""
import os
import sys
from datetime import datetime

# .envファイルから環境変数を読み込む
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenvがなくてもファイルを直接読む
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

from trend_fetcher import get_trending_keywords
from content_generator import generate_content
from video_creator import create_video

def main():
    print("=" * 50)
    print("🎬 TikTok ライフハック動画 自動生成")
    print("=" * 50)

    # 動画の本数（デフォルト1本）
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 1

    # 出力フォルダ
    output_dir = "./output"
    os.makedirs(output_dir, exist_ok=True)

    # BGMパス（あれば自動で付与）
    bgm_path = os.path.join(os.path.dirname(__file__), "bgm_chord.mp3")
    if not os.path.exists(bgm_path):
        bgm_path = None

    # STEP 1: トレンドキーワード取得
    print("\n📊 STEP 1: トレンドキーワード取得中...")
    keywords = get_trending_keywords(top_n=count)

    generated_videos = []

    for i, keyword in enumerate(keywords[:count]):
        print(f"\n--- 動画 {i+1}/{count}: {keyword} ---")

        # STEP 2: コンテンツ生成
        print("✍️  STEP 2: ライフハック内容生成中...")
        content = generate_content(keyword)
        print(f"   タイトル: {content['title']}")
        print(f"   ヒント数: {len(content['tips'])}個")

        # STEP 3: 動画生成
        print("🎬 STEP 3: 動画生成中（少し時間がかかります）...")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"{output_dir}/lifehack_{timestamp}_{i+1}.mp4"
        create_video(content, output_path, duration=15, bgm_path=bgm_path)
        generated_videos.append(output_path)

    # 完了
    print("\n" + "=" * 50)
    print("✅ 全動画生成完了！")
    for v in generated_videos:
        print(f"   📹 {v}")
    print("\nTikTokにアップロードしてください！")
    print("=" * 50)

if __name__ == "__main__":
    main()
