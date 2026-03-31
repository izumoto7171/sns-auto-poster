"""
動画合成 - テロップ描画 + FFmpegで動画生成
"""
import os
import shutil
import subprocess
import wave
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from config import (
    VIDEO_WIDTH, VIDEO_HEIGHT, FPS,
    FONT_PATH, FONT_SIZE_LARGE, FONT_SIZE_SMALL,
    CAPTION_COLOR, CAPTION_OUTLINE, OUTLINE_WIDTH,
    OUTPUT_DIR,
)


def get_font(size: int) -> ImageFont.FreeTypeFont:
    # プロジェクト内フォント優先
    if Path(FONT_PATH).exists():
        return ImageFont.truetype(str(FONT_PATH), size)
    # システムフォントフォールバック
    fallbacks = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Regular.otf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    ]
    for path in fallbacks:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.Draw) -> list[str]:
    lines, current = [], ""
    for char in text:
        test = current + char
        if draw.textbbox((0, 0), test, font=font)[2] > max_width:
            if current:
                lines.append(current)
            current = char
        else:
            current = test
    if current:
        lines.append(current)
    return lines


def draw_caption(draw: ImageDraw.Draw, text: str, y_center: int, font: ImageFont.FreeTypeFont):
    """黄色テキスト＋黒縁取りで中央描画"""
    lines = wrap_text(text, font, VIDEO_WIDTH - 80, draw)
    line_h = font.size + 10
    total_h = line_h * len(lines)
    y = y_center - total_h // 2

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        x = (VIDEO_WIDTH - (bbox[2] - bbox[0])) // 2
        # 縁取り
        for dx in range(-OUTLINE_WIDTH, OUTLINE_WIDTH + 1, 2):
            for dy in range(-OUTLINE_WIDTH, OUTLINE_WIDTH + 1, 2):
                if dx != 0 or dy != 0:
                    draw.text((x + dx, y + dy), line, font=font, fill=CAPTION_OUTLINE)
        # 本文
        draw.text((x, y), line, font=font, fill=CAPTION_COLOR)
        y += line_h


def get_wav_duration(wav_path: str) -> float:
    try:
        with wave.open(wav_path, "r") as f:
            return f.getnframes() / f.getframerate()
    except Exception:
        return 3.0


def compose_video(script: dict, bg_image_path: str, voice_paths: list[str],
                  bgm_path: str = None, output_path: str = None) -> str:
    """
    背景画像 + セクションごとの音声 + テロップ → MP4に合成

    Args:
        script: generate_script.pyの出力dict
        bg_image_path: 背景画像パス
        voice_paths: セクションごとの音声ファイルパスリスト
        bgm_path: BGM音声ファイルパス（任意）
        output_path: 出力MP4パス
    """
    if output_path is None:
        from datetime import datetime
        output_path = str(OUTPUT_DIR / f"shorts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")

    frames_dir = Path("/tmp/shorts_frames")
    frames_dir.mkdir(exist_ok=True)

    bg = Image.open(bg_image_path).resize((VIDEO_WIDTH, VIDEO_HEIGHT), Image.LANCZOS).convert("RGB")
    font_large = get_font(FONT_SIZE_LARGE)
    font_small = get_font(FONT_SIZE_SMALL)

    sections = script.get("sections", [])
    hook_text = script.get("hook", "")
    cta_text = script.get("cta", "")

    # セクションを構築（hook + sections + cta）
    all_sections = []
    if hook_text:
        hook_voice = voice_paths[0] if voice_paths else None
        all_sections.append({"text": hook_text, "voice": hook_voice, "is_hook": True})

    for i, sec in enumerate(sections):
        vpath = voice_paths[i + (1 if hook_text else 0)] if i + (1 if hook_text else 0) < len(voice_paths) else None
        all_sections.append({"text": sec.get("text", ""), "voice": vpath, "is_hook": False})

    if cta_text:
        cta_voice = voice_paths[-1] if voice_paths else None
        all_sections.append({"text": cta_text, "voice": cta_voice, "is_hook": False})

    # フレーム生成 + 音声リスト収集
    frame_idx = 0
    audio_parts = []

    for sec in all_sections:
        vpath = sec.get("voice")
        duration = get_wav_duration(vpath) if vpath else 3.0
        n_frames = max(1, int(duration * FPS))
        font = font_large if sec.get("is_hook") else font_small
        text = sec["text"]

        for _ in range(n_frames):
            frame = bg.copy()
            draw = ImageDraw.Draw(frame)
            # テロップ位置：下部1/3
            draw_caption(draw, text, int(VIDEO_HEIGHT * 0.78), font)
            frame.save(frames_dir / f"frame_{frame_idx:05d}.png")
            frame_idx += 1

        if vpath and Path(vpath).exists():
            audio_parts.append(vpath)

    total_frames = frame_idx
    print(f"  📸 {total_frames}フレーム生成完了")

    # 音声ファイルを結合
    audio_concat = str(OUTPUT_DIR / "audio_concat.wav")
    _concat_wavs(audio_parts, audio_concat, total_frames / FPS)

    # FFmpegで動画合成
    print("  🎞️  FFmpegで動画合成中...")
    _run_ffmpeg(str(frames_dir), audio_concat, bgm_path, output_path, total_frames / FPS)

    shutil.rmtree(frames_dir, ignore_errors=True)
    Path(audio_concat).unlink(missing_ok=True)

    size_mb = Path(output_path).stat().st_size / 1024 / 1024
    print(f"  ✅ 動画完成: {Path(output_path).name} ({size_mb:.1f}MB)")
    return output_path


def _concat_wavs(wav_paths: list[str], output_path: str, target_duration: float):
    """複数WAVを結合"""
    import struct
    if not wav_paths:
        # 無音
        sample_rate = 24000
        n = int(sample_rate * target_duration)
        with wave.open(output_path, "w") as f:
            f.setnchannels(1); f.setsampwidth(2); f.setframerate(sample_rate)
            f.writeframes(struct.pack("<" + "h" * n, *([0] * n)))
        return

    frames_all = b""
    params = None
    for p in wav_paths:
        try:
            with wave.open(p, "r") as wf:
                if params is None:
                    params = wf.getparams()
                frames_all += wf.readframes(wf.getnframes())
        except Exception:
            pass

    if params is None:
        return

    with wave.open(output_path, "w") as out:
        out.setparams(params)
        out.writeframes(frames_all)


def _run_ffmpeg(frames_dir: str, audio_path: str, bgm_path: str, output_path: str, duration: float):
    if bgm_path and Path(bgm_path).exists():
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(FPS),
            "-i", f"{frames_dir}/frame_%05d.png",
            "-i", audio_path,
            "-stream_loop", "-1", "-i", bgm_path,
            "-filter_complex", "[1:a][2:a]amix=inputs=2:duration=first:weights=1 0.3[aout]",
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest",
            "-af", f"afade=t=out:st={max(0, duration-2)}:d=2",
            output_path,
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(FPS),
            "-i", f"{frames_dir}/frame_%05d.png",
            "-i", audio_path,
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest",
            output_path,
        ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ FFmpegエラー: {result.stderr[-300:]}")
