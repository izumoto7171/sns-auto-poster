"""
AI雑学ショート動画生成
構成: フック(0-3s) → 解説(3-12s) → オチ(12-15s)
"""
from PIL import Image, ImageDraw, ImageFont
import os
import subprocess
import random
import math

WIDTH = 1080
HEIGHT = 1920

THEMES = [
    {
        "name": "impact_red",
        "bg_top":    (40, 0, 0),
        "bg_mid":    (20, 0, 0),
        "bg_bottom": (8, 0, 0),
        "accent":    (255, 60, 60),
        "accent2":   (255, 160, 0),
        "text":      (255, 255, 255),
        "card_bg":   (50, 10, 10),
        "card_border": (220, 40, 40),
    },
    {
        "name": "neon_purple",
        "bg_top":    (20, 0, 40),
        "bg_mid":    (10, 0, 25),
        "bg_bottom": (5, 0, 15),
        "accent":    (200, 80, 255),
        "accent2":   (255, 60, 200),
        "text":      (255, 255, 255),
        "card_bg":   (35, 10, 55),
        "card_border": (180, 60, 240),
    },
    {
        "name": "cyber_blue",
        "bg_top":    (0, 10, 40),
        "bg_mid":    (0, 5, 25),
        "bg_bottom": (0, 0, 15),
        "accent":    (0, 200, 255),
        "accent2":   (0, 120, 220),
        "text":      (255, 255, 255),
        "card_bg":   (5, 20, 50),
        "card_border": (0, 180, 255),
    },
    {
        "name": "toxic_green",
        "bg_top":    (0, 25, 10),
        "bg_mid":    (0, 12, 5),
        "bg_bottom": (0, 5, 2),
        "accent":    (0, 255, 100),
        "accent2":   (180, 255, 0),
        "text":      (255, 255, 255),
        "card_bg":   (5, 30, 15),
        "card_border": (0, 220, 80),
    },
]

CATEGORY_EMOJIS = {
    "雑学": "🧠",
    "危険": "⚠️",
    "世界のヤバい法律": "⚖️",
    "歴史": "📜",
    "科学": "🔬",
}


def get_font(size):
    font_paths = [
        "/System/Library/Fonts/ヒラギノ角ゴシック W8.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/Library/Fonts/Arial Unicode MS.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def wrap_text(text, font, max_width, draw):
    if not text:
        return []
    lines = []
    current = ""
    for char in text:
        test = current + char
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] > max_width:
            if current:
                lines.append(current)
            current = char
        else:
            current = test
    if current:
        lines.append(current)
    return lines


def lerp_color(c1, c2, t):
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def draw_gradient_bg(draw, theme):
    top = theme["bg_top"]
    mid = theme["bg_mid"]
    bot = theme["bg_bottom"]
    for y in range(HEIGHT):
        t = y / HEIGHT
        if t < 0.5:
            color = lerp_color(top, mid, t * 2)
        else:
            color = lerp_color(mid, bot, (t - 0.5) * 2)
        draw.line([(0, y), (WIDTH, y)], fill=color)


def draw_scanlines(draw, theme):
    """サイバー感のあるスキャンライン効果"""
    for y in range(0, HEIGHT, 6):
        c = tuple(max(0, c - 8) for c in theme["bg_mid"])
        draw.line([(0, y), (WIDTH, y)], fill=c)


def draw_glow_text(draw, x, y, text, font, color, glow_radius=5):
    """グロー付きテキスト"""
    glow_color = tuple(max(0, c // 3) for c in color)
    for dx in range(-glow_radius, glow_radius + 1, 2):
        for dy in range(-glow_radius, glow_radius + 1, 2):
            if dx != 0 or dy != 0:
                draw.text((x + dx, y + dy), text, font=font, fill=glow_color)
    draw.text((x + 2, y + 2), text, font=font, fill=(0, 0, 0))
    draw.text((x, y), text, font=font, fill=color)


def draw_text_centered(draw, y, text, font, color, glow=False):
    bbox = draw.textbbox((0, 0), text, font=font)
    x = (WIDTH - (bbox[2] - bbox[0])) // 2
    if glow:
        draw_glow_text(draw, x, y, text, font, color)
    else:
        draw.text((x + 2, y + 2), text, font=font, fill=(0, 0, 0))
        draw.text((x, y), text, font=font, fill=color)
    return bbox[3] - bbox[1]


def draw_progress_bar(draw, theme, progress):
    h = 12
    y = HEIGHT - 55
    margin = 80
    w = WIDTH - margin * 2
    draw.rounded_rectangle([margin, y, margin + w, y + h], radius=6, fill=(30, 30, 30))
    fw = int(w * progress)
    if fw > 10:
        for px in range(fw):
            t = px / fw
            c = lerp_color(theme["accent2"], theme["accent"], t)
            draw.line([(margin + px, y), (margin + px, y + h)], fill=c)


# ─────────────────────────────────
# 1. フック画面（0〜3秒）
# ─────────────────────────────────
def create_hook_frame(content, frame_num, hook_frames, theme):
    img = Image.new("RGB", (WIDTH, HEIGHT), color=theme["bg_bottom"])
    draw = ImageDraw.Draw(img)
    draw_gradient_bg(draw, theme)
    draw_scanlines(draw, theme)

    t = frame_num / max(hook_frames - 1, 1)
    ease = 1 - (1 - min(t * 2, 1.0)) ** 3

    category = content.get("category", "雑学")
    emoji = CATEGORY_EMOJIS.get(category, "💡")

    # カテゴリバッジ（上部）
    badge_font = get_font(52)
    badge_text = f"{emoji}  {category}"
    badge_bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
    bw = badge_bbox[2] - badge_bbox[0]
    bx = (WIDTH - bw) // 2
    by = 120
    pad = 22
    draw.rounded_rectangle(
        [bx - pad, by - pad // 2, bx + bw + pad, by + badge_bbox[3] + pad // 2],
        radius=30, fill=theme["card_bg"]
    )
    draw.rounded_rectangle(
        [bx - pad, by - pad // 2, bx + bw + pad, by + badge_bbox[3] + pad // 2],
        radius=30, outline=theme["accent"], width=2
    )
    draw.text((bx, by), badge_text, font=badge_font, fill=theme["accent"])

    # 警告ライン（上下）
    for g in range(10, 0, -2):
        c = tuple(max(0, v // (g + 1)) for v in theme["accent"])
        draw.rectangle([0, 0, WIDTH, g * 2], fill=c)
        draw.rectangle([0, HEIGHT - g * 2, WIDTH, HEIGHT], fill=c)

    # ❗アイコン（フェードイン）
    icon_size = int(120 + 30 * ease)
    icon_font = get_font(icon_size)
    icon_y = HEIGHT // 2 - 500
    draw_text_centered(draw, icon_y, "❗", icon_font, theme["accent2"], glow=True)

    # フックテキスト（大きく・中央）
    hook_display = content.get("hook_display", content.get("hook", ""))
    hook_font = get_font(72)
    hook_lines = wrap_text(hook_display, hook_font, WIDTH - 80, draw)
    total_h = len(hook_lines) * 90
    hook_start_y = HEIGHT // 2 - total_h // 2 - 80

    for line in hook_lines:
        draw_text_centered(draw, hook_start_y, line, hook_font, theme["text"], glow=False)
        hook_start_y += 95

    # 「続きは→」テキスト（バウンス）
    bounce_y = HEIGHT // 2 + 320 + int(math.sin(t * math.pi * 6) * 18)
    cont_font = get_font(56)
    draw_text_centered(draw, bounce_y, "続きを見て👇", cont_font, theme["accent2"])

    draw_progress_bar(draw, theme, 0)
    return img


# ─────────────────────────────────
# 2. 解説画面（3〜12秒）
# ─────────────────────────────────
def create_explanation_frame(content, frame_num, exp_start, exp_end, theme):
    local_t = (frame_num - exp_start) / max(exp_end - exp_start - 1, 1)

    img = Image.new("RGB", (WIDTH, HEIGHT), color=theme["bg_bottom"])
    draw = ImageDraw.Draw(img)
    draw_gradient_bg(draw, theme)
    draw_scanlines(draw, theme)

    # 上部タイトルバー
    draw.rectangle([0, 0, WIDTH, 160], fill=theme["card_bg"])
    draw.rectangle([0, 160, WIDTH, 166], fill=theme["accent"])

    category = content.get("category", "雑学")
    emoji = CATEGORY_EMOJIS.get(category, "💡")
    title_font = get_font(56)
    hook_short = content.get("hook", "")
    hook_lines = wrap_text(hook_short, title_font, WIDTH - 120, draw)
    ty = 18
    for line in hook_lines[:2]:
        draw_text_centered(draw, ty, line, title_font, theme["accent"])
        ty += 68

    # 「解説」ラベル
    label_font = get_font(52)
    label_y = 210
    draw_text_centered(draw, label_y, f"{emoji} 解説", label_font, theme["accent2"])

    # 解説テキスト（フェードイン・スクロール）
    exp_text = content.get("explanation", "")
    exp_font = get_font(54)
    exp_lines = wrap_text(exp_text, exp_font, WIDTH - 100, draw)

    card_x1 = 50
    card_x2 = WIDTH - 50
    card_y1 = 310
    card_y2 = HEIGHT - 200

    # カード背景
    draw.rounded_rectangle([card_x1, card_y1, card_x2, card_y2],
                            radius=24, fill=theme["card_bg"])
    draw.rounded_rectangle([card_x1, card_y1, card_x2, card_y2],
                            radius=24, outline=theme["card_border"], width=3)
    # 左アクセントライン
    draw.rounded_rectangle([card_x1, card_y1, card_x1 + 8, card_y2],
                            radius=24, fill=theme["accent"])

    # テキストを順番に表示（タイプライター風）
    total_chars = sum(len(ln) for ln in exp_lines)
    show_chars = int(local_t * total_chars * 1.3)
    text_y = card_y1 + 40
    chars_drawn = 0
    line_h = 68
    for line in exp_lines:
        if text_y + line_h > card_y2 - 20:
            break
        if chars_drawn >= show_chars:
            break
        visible = line[:max(0, show_chars - chars_drawn)]
        if visible:
            draw.text((card_x1 + 40, text_y), visible, font=exp_font, fill=theme["text"])
        chars_drawn += len(line)
        text_y += line_h

    draw_progress_bar(draw, theme, local_t * 0.8)
    return img


# ─────────────────────────────────
# 3. オチ画面（12〜15秒）
# ─────────────────────────────────
def create_punchline_frame(content, frame_num, punch_start, total_frames, theme):
    local_t = (frame_num - punch_start) / max(total_frames - punch_start - 1, 1)

    img = Image.new("RGB", (WIDTH, HEIGHT), color=theme["bg_bottom"])
    draw = ImageDraw.Draw(img)
    draw_gradient_bg(draw, theme)
    draw_scanlines(draw, theme)

    # 放射グロー
    for r in range(600, 0, -60):
        alpha = max(0, 12 - r // 50)
        gc = tuple(min(255, c + alpha) for c in theme["bg_mid"])
        draw.ellipse([WIDTH // 2 - r, HEIGHT // 2 - r,
                      WIDTH // 2 + r, HEIGHT // 2 + r], fill=gc)

    ease = 1 - (1 - min(local_t * 2, 1.0)) ** 3

    # 💡アイコン
    icon_size = int(150 + 30 * ease)
    icon_font = get_font(icon_size)
    draw_text_centered(draw, HEIGHT // 2 - 500, "💡", icon_font, theme["accent2"], glow=True)

    # 「オチ」ラベル
    label_font = get_font(60)
    draw_text_centered(draw, HEIGHT // 2 - 280, "── オチ ──", label_font, theme["accent"])

    # オチテキスト
    punchline = content.get("punchline", "")
    punch_font = get_font(70)
    punch_lines = wrap_text(punchline, punch_font, WIDTH - 100, draw)
    py = HEIGHT // 2 - 160
    for line in punch_lines:
        draw_text_centered(draw, py, line, punch_font, theme["text"], glow=True)
        py += 85

    # CTA ボタン
    pulse = 0.93 + 0.07 * math.sin(local_t * math.pi * 8)
    cta_font = get_font(int(58 * pulse))
    cta_items = [
        ("❤️  いいね & フォロー", theme["accent"], (0, 0, 0)),
        ("🔔  保存して見返そう！", theme["card_bg"], theme["accent"]),
    ]
    cy = HEIGHT // 2 + 180
    for text, bg, fg in cta_items:
        bbox = draw.textbbox((0, 0), text, font=cta_font)
        bw = bbox[2] - bbox[0]
        bh = bbox[3] - bbox[1]
        bx = (WIDTH - bw) // 2
        pad = 26
        glow_c = tuple(max(0, c // 3) for c in theme["accent"])
        draw.rounded_rectangle(
            [bx - pad - 4, cy - pad - 4, bx + bw + pad + 4, cy + bh + pad + 4],
            radius=52, fill=glow_c
        )
        draw.rounded_rectangle(
            [bx - pad, cy - pad, bx + bw + pad, cy + bh + pad],
            radius=50, fill=bg
        )
        draw.rounded_rectangle(
            [bx - pad, cy - pad, bx + bw + pad, cy + bh + pad],
            radius=50, outline=theme["accent"], width=3
        )
        draw.text((bx, cy), text, font=cta_font, fill=fg)
        cy += bh + pad * 2 + 50

    draw_progress_bar(draw, theme, 1.0)
    return img


# ─────────────────────────────────
# メイン生成関数
# ─────────────────────────────────
def create_trivia_video(content, output_path, duration=15, bgm_path=None):
    print(f"🎬 雑学動画生成: {content.get('hook', '')[:30]}")

    theme = random.choice(THEMES)
    print(f"  🎨 テーマ: {theme['name']} | カテゴリ: {content.get('category', '雑学')}")

    fps = 30
    total_frames = duration * fps
    hook_frames = fps * 3          # 0-3s
    punch_frames = fps * 3         # 12-15s
    exp_frames   = total_frames - hook_frames - punch_frames  # 3-12s
    exp_start    = hook_frames
    exp_end      = hook_frames + exp_frames
    punch_start  = exp_end

    frames_dir = "/tmp/trivia_frames"
    os.makedirs(frames_dir, exist_ok=True)

    print(f"  📸 {total_frames}フレーム生成中...")
    for i in range(total_frames):
        if i < hook_frames:
            frame = create_hook_frame(content, i, hook_frames, theme)
        elif i < exp_end:
            frame = create_explanation_frame(content, i, exp_start, exp_end, theme)
        else:
            frame = create_punchline_frame(content, i, punch_start, total_frames, theme)

        frame.save(f"{frames_dir}/frame_{i:04d}.png")
        if i % 90 == 0:
            pct = int(i / total_frames * 100)
            print(f"  　{pct}% ({i}/{total_frames})")

    print("  🎞️  動画に変換中...")

    if bgm_path and os.path.exists(bgm_path):
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", f"{frames_dir}/frame_%04d.png",
            "-stream_loop", "-1",
            "-i", bgm_path,
            "-c:v", "libx264",
            "-c:a", "aac",
            "-b:a", "128k",
            "-shortest",
            "-pix_fmt", "yuv420p",
            "-crf", "20",
            "-preset", "fast",
            "-af", f"volume=0.5,afade=t=in:st=0:d=1,afade=t=out:st={duration-2}:d=2",
            output_path,
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", f"{frames_dir}/frame_%04d.png",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-crf", "20",
            "-preset", "fast",
            output_path,
        ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        bgm_label = "🎵 BGM付き" if (bgm_path and os.path.exists(bgm_path)) else "🔇 BGMなし"
        print(f"✅ 完了 {bgm_label}: {output_path}  ({size_mb:.1f}MB)")
    else:
        print(f"❌ エラー: {result.stderr[-500:]}")

    import shutil
    shutil.rmtree(frames_dir, ignore_errors=True)
    return output_path


if __name__ == "__main__":
    sample = {
        "hook": "蚊に刺されるのは血液型O型が多い",
        "hook_display": "99%が知らない：蚊に刺されるのは血液型O型が多い",
        "explanation": "研究によると、O型の人はA型・B型に比べて蚊に刺されやすい。蚊は皮膚から分泌される化学物質で血液型を嗅ぎ分けている。O型の人が出す分泌物が蚊を特に引き寄せるとされている。",
        "punchline": "O型のあなた、蚊除けスプレーは必須です。",
        "category": "雑学",
    }
    os.makedirs("./output", exist_ok=True)
    bgm = os.path.join(os.path.dirname(__file__), "bgm_chord.mp3")
    create_trivia_video(
        sample,
        "./output/trivia_test.mp4",
        duration=15,
        bgm_path=bgm if os.path.exists(bgm) else None,
    )
