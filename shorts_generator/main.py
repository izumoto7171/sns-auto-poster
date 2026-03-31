"""
AI雑学ショート 生成ツール

使い方：
  python main.py --theme "お肉を水で洗ってはいけない理由"
  python main.py --theme "バナナは木ではなく草になる" --upload
  python main.py --theme "卵の正しい保存方法" --private
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import OUTPUT_DIR
from generate_script import generate_script
from generate_image import generate_image
from generate_voice import generate_voice
from compose_video import compose_video
from upload_youtube import upload_shorts


def main():
    parser = argparse.ArgumentParser(description="AI雑学ショート自動生成")
    parser.add_argument("--theme", required=True, help="動画のテーマ")
    parser.add_argument("--upload", action="store_true", help="YouTubeにアップロード")
    parser.add_argument("--private", action="store_true", help="限定公開でアップロード")
    args = parser.parse_args()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    print("=" * 55)
    print(f"🎬 AI雑学ショート生成開始")
    print(f"   テーマ: {args.theme}")
    print("=" * 55)

    # 1. 台本生成
    print("\n📝 STEP 1: 台本生成")
    script = generate_script(args.theme)
    print(f"   タイトル: {script.get('title', '')}")
    print(f"   フック: {script.get('hook', '')[:40]}")
    print(f"   セクション数: {len(script.get('sections', []))}個")

    # 2. AI画像生成
    print("\n🎨 STEP 2: 背景画像生成")
    bg_path = str(OUTPUT_DIR / f"bg_{ts}.png")
    generate_image(script.get("image_prompt", "abstract colorful background"), bg_path)

    # 3. 音声生成（hook + sections + cta）
    print("\n🎤 STEP 3: 音声生成")
    voice_paths = []
    voice_texts = []

    if script.get("hook"):
        voice_texts.append(script["hook"])
    for sec in script.get("sections", []):
        voice_texts.append(sec.get("voice") or sec.get("text", ""))
    if script.get("cta"):
        voice_texts.append(script["cta"])

    for i, text in enumerate(voice_texts):
        vpath = str(OUTPUT_DIR / f"voice_{ts}_{i:02d}.wav")
        generate_voice(text, vpath)
        voice_paths.append(vpath)
        print(f"   [{i+1}/{len(voice_texts)}] {text[:30]}...")

    # 4. 動画合成
    print("\n🎞️  STEP 4: 動画合成")
    bgm_path = str(Path(__file__).parent.parent / "bgm_chord.mp3")
    if not Path(bgm_path).exists():
        bgm_path = None

    output_path = str(OUTPUT_DIR / f"shorts_{ts}.mp4")
    compose_video(script, bg_path, voice_paths, bgm_path=bgm_path, output_path=output_path)

    # 中間ファイルを削除
    for p in voice_paths:
        Path(p).unlink(missing_ok=True)
    Path(bg_path).unlink(missing_ok=True)

    # 5. YouTube アップロード（--uploadフラグがある場合のみ）
    youtube_url = None
    if args.upload or args.private:
        print("\n📺 STEP 5: YouTube Shortsにアップロード")
        privacy = "private" if args.private else "public"
        youtube_url = upload_shorts(output_path, script, privacy=privacy)
    else:
        print(f"\n💡 アップロードするには --upload を付けて実行してください")

    # 完了
    print("\n" + "=" * 55)
    print("✅ 完了！")
    print(f"   動画: {output_path}")
    if youtube_url:
        print(f"   YouTube: {youtube_url}")
    print("=" * 55)


if __name__ == "__main__":
    main()
