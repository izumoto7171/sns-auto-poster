"""
キャラクター画像 + 日本語音声 → TikTok用縦型動画（9:16）を自動生成
gTTS（無料）で音声、ffmpeg（標準搭載）で合成
"""
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


# ─────────────────────────────────────────
# 音声生成（gTTS / 無料）
# ─────────────────────────────────────────
def generate_audio(script: dict, output_path: Path) -> bool:
    """スクリプトから日本語ナレーション音声を生成"""
    try:
        from gtts import gTTS

        # ナレーション文を組み立て（10秒程度に収まる量）
        lines = [
            script.get("hook", ""),
            script.get("step1", ""),
            script.get("step2", ""),
            script.get("step3", ""),
            script.get("cta", ""),
        ]
        narration = "。".join(l for l in lines if l) + "。"
        print(f"🎙️  ナレーション: {narration[:60]}...")

        tts = gTTS(text=narration, lang="ja", slow=False)
        tts.save(str(output_path))
        print(f"✅ 音声生成: {output_path.name} ({output_path.stat().st_size // 1024}KB)")
        return True

    except ImportError:
        print("⚠️ gTTS未インストール: pip install gtts")
        return False
    except Exception as e:
        print(f"❌ 音声生成エラー: {e}")
        return False


# ─────────────────────────────────────────
# 動画合成（ffmpeg）
# ─────────────────────────────────────────
def generate_video(image_path: Path, audio_path: Path, output_path: Path, topic: str = "") -> bool:
    """画像 + 音声 → 9:16縦型MP4（TikTok/Reels対応）"""
    try:
        # 字幕テキスト（ファイル名に使えない文字を除去）
        safe_topic = topic[:20].replace("'", "").replace('"', "")

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", str(image_path),
            "-i", str(audio_path),
            "-shortest",
            "-c:v", "libx264",
            "-tune", "stillimage",
            "-c:a", "aac",
            "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            # 9:16 縦型（1080x1920）にリサイズ・パディング
            "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
            "-movflags", "+faststart",  # スマホ再生最適化
            str(output_path),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            print(f"❌ ffmpegエラー: {result.stderr[-200:]}")
            return False

        size_mb = output_path.stat().st_size / 1024 / 1024
        print(f"✅ 動画生成: {output_path.name} ({size_mb:.1f}MB)")
        return True

    except FileNotFoundError:
        print("⚠️ ffmpegが見つかりません。インストールしてください")
        return False
    except Exception as e:
        print(f"❌ 動画生成エラー: {e}")
        return False


# ─────────────────────────────────────────
# フルパイプライン
# ─────────────────────────────────────────
def generate_full_video(post: dict, date_str: str = None) -> Path | None:
    """スクリプト + 画像 → 完成動画を返す"""
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d_%H%M%S")

    script = post["script"]
    topic = post["theme"]["topic"]

    # 画像パスを確認
    image_path = Path(post.get("image_path", ""))
    if not image_path.exists():
        # デフォルト画像を探す
        candidates = sorted(OUTPUT_DIR.glob("character_*.png"), reverse=True)
        if candidates:
            image_path = candidates[0]
            print(f"📁 最新の画像を使用: {image_path.name}")
        else:
            print("⚠️ キャラクター画像なし。画像生成が先に必要です")
            return None

    # 音声生成
    audio_path = OUTPUT_DIR / f"audio_{date_str}.mp3"
    if not generate_audio(script, audio_path):
        return None

    # 動画合成
    video_path = OUTPUT_DIR / f"video_{date_str}.mp4"
    if not generate_video(image_path, audio_path, video_path, topic):
        return None

    # 一時音声ファイルを削除
    audio_path.unlink(missing_ok=True)

    return video_path


if __name__ == "__main__":
    # テスト用
    sys.path.insert(0, str(Path(__file__).parent))
    from script_generator import generate, load_env, save_output
    load_env()

    post = generate()
    out = save_output(post, generate_image=True)

    video = generate_full_video(post)
    if video:
        print(f"\n🎬 完成動画: {video}")
        print("GitHubにコミット後、iPhoneからダウンロードしてTikTokに投稿できます")
