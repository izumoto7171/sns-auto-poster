"""
TikTok縦型動画（1080x1920）を自動生成
バズる動画スタイル：強いフック・大きなテキスト・スライドイン・プログレスバー
"""
from PIL import Image, ImageDraw, ImageFont
import os
import subprocess
import random
import math

# 動画サイズ（TikTok縦型）
WIDTH = 1080
HEIGHT = 1920

# ダークテーマ（改善版）
THEMES = [
    {
        "name": "purple_fire",
        "bg_top":    (20, 0, 40),
        "bg_mid":    (10, 0, 25),
        "bg_bottom": (5, 0, 15),
        "accent":    (200, 80, 255),
        "accent2":   (255, 60, 120),
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
        "name": "gold_black",
        "bg_top":    (25, 15, 0),
        "bg_mid":    (15, 8, 0),
        "bg_bottom": (8, 4, 0),
        "accent":    (255, 200, 0),
        "accent2":   (255, 130, 0),
        "text":      (255, 255, 255),
        "card_bg":   (35, 22, 5),
        "card_border": (220, 170, 0),
    },
    {
        "name": "matrix_green",
        "bg_top":    (0, 20, 10),
        "bg_mid":    (0, 12, 5),
        "bg_bottom": (0, 5, 2),
        "accent":    (0, 255, 100),
        "accent2":   (0, 200, 60),
        "text":      (255, 255, 255),
        "card_bg":   (5, 30, 15),
        "card_border": (0, 220, 80),
    },
]

HOOK_TEXTS = [
    "知らないと損！",
    "これ知ってた？",
    "99%が知らない",
    "今すぐ試して！",
    "保存必須✅",
    "マジで変わる",
]


def get_font(size):
    font_paths = [
        # Mac
        "/System/Library/Fonts/ヒラギノ角ゴシック W8.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/Library/Fonts/Arial Unicode MS.ttf",
        # Ubuntu / GitHub Actions（Noto CJK）
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Regular.otf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJKjp-Regular.otf",
    ]
    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def wrap_text(text, font, max_width, draw):
    if len(text) <= 12:
        return [text]
    lines = []
    current = ""
    for char in text:
        test = current + char
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] > max_width:
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
    """3色グラデーション背景"""
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


def draw_dot_pattern(draw, theme, alpha=30):
    """背景に薄いドットパターンを追加（奥行き感）"""
    dot_color = tuple(min(255, c + alpha) for c in theme["bg_mid"])
    for x in range(0, WIDTH, 60):
        for y in range(0, HEIGHT, 60):
            draw.ellipse([x - 2, y - 2, x + 2, y + 2], fill=dot_color)


def draw_glow_rect(draw, x1, y1, x2, y2, color, radius=20, glow_size=8):
    """グロー付き角丸矩形"""
    gc = tuple(max(0, c // 3) for c in color)
    for g in range(glow_size, 0, -2):
        draw.rounded_rectangle(
            [x1 - g, y1 - g, x2 + g, y2 + g],
            radius=radius + g,
            fill=gc,
        )
    draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=color)


def draw_text_centered(draw, y, text, font, color, shadow=True):
    bbox = draw.textbbox((0, 0), text, font=font)
    x = (WIDTH - (bbox[2] - bbox[0])) // 2
    if shadow:
        draw.text((x + 4, y + 4), text, font=font, fill=(0, 0, 0))
    draw.text((x, y), text, font=font, fill=color)
    return bbox[3] - bbox[1]


def draw_progress_bar(draw, theme, progress):
    h = 10
    y = HEIGHT - 50
    margin = 80
    w = WIDTH - margin * 2
    draw.rounded_rectangle([margin, y, margin + w, y + h], radius=5, fill=(40, 40, 40))
    fw = int(w * progress)
    if fw > 10:
        # グラデーション風プログレスバー
        for px in range(fw):
            t = px / fw
            c = lerp_color(theme["accent2"], theme["accent"], t)
            draw.line([(margin + px, y), (margin + px, y + h)], fill=c)


# ───────────────────────────────────────────────
# フック画面（0〜3秒）
# ───────────────────────────────────────────────
def create_hook_frame(content, frame_num, hook_frames, theme, hook_text):
    img = Image.new("RGB", (WIDTH, HEIGHT), color=theme["bg_bottom"])
    draw = ImageDraw.Draw(img)
    draw_gradient_bg(draw, theme)
    draw_dot_pattern(draw, theme)

    t = frame_num / max(hook_frames - 1, 1)

    # --- 上部グロー装飾ライン ---
    for g in range(12, 0, -3):
        alpha_c = tuple(max(0, c - g * 10) for c in theme["accent"])
        draw.rectangle([0, 0, WIDTH, g * 2], fill=alpha_c)

    # --- フック文言（中央・大）---
    # ズームイン: スケール 0.6 → 1.0
    ease = 1 - (1 - min(t * 2, 1.0)) ** 3
    hook_size = int(100 + 20 * ease)
    hook_font = get_font(hook_size)
    hook_y = HEIGHT // 2 - 280

    # グロー
    for dx in range(-6, 7, 3):
        for dy in range(-6, 7, 3):
            draw.text(
                (WIDTH // 2 - draw.textbbox((0,0), hook_text, font=hook_font)[2] // 2 + dx,
                 hook_y + dy),
                hook_text, font=hook_font, fill=theme["accent2"]
            )
    bbox = draw.textbbox((0, 0), hook_text, font=hook_font)
    hx = (WIDTH - (bbox[2] - bbox[0])) // 2
    draw.text((hx, hook_y), hook_text, font=hook_font, fill=theme["accent"])

    # --- タイトル（フックの下） ---
    title_font = get_font(70)
    title_lines = wrap_text(content["title"], title_font, WIDTH - 120, draw)
    ty = HEIGHT // 2 - 80
    for line in title_lines:
        h_line = draw_text_centered(draw, ty, line, title_font, theme["text"])
        ty += h_line + 18

    # --- ヒント数バッジ ---
    badge_font = get_font(56)
    badge_text = f"📌 {len(content['tips'])}つのコツを紹介"
    bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
    bw = bbox[2] - bbox[0]
    bx = (WIDTH - bw) // 2
    by = HEIGHT // 2 + 140
    pad = 24
    # バッジ背景
    draw_glow_rect(draw, bx - pad, by - pad, bx + bw + pad, by + bbox[3] + pad,
                   theme["card_bg"], radius=40, glow_size=6)
    # バッジ枠線
    draw.rounded_rectangle([bx - pad, by - pad, bx + bw + pad, by + bbox[3] + pad],
                            radius=40, outline=theme["accent"], width=3)
    draw.text((bx, by), badge_text, font=badge_font, fill=theme["accent"])

    # --- バウンス矢印 ---
    arrow_y = HEIGHT // 2 + 320 + int(math.sin(t * math.pi * 4) * 20)
    arrow_font = get_font(90)
    draw_text_centered(draw, arrow_y, "▼", arrow_font, theme["accent2"], shadow=False)

    draw_progress_bar(draw, theme, 0)
    return img


# ───────────────────────────────────────────────
# ヒント画面（3〜13秒）
# ───────────────────────────────────────────────
def create_tips_frame(content, frame_num, tips_start, tips_end, theme):
    local_t = (frame_num - tips_start) / max(tips_end - tips_start - 1, 1)

    img = Image.new("RGB", (WIDTH, HEIGHT), color=theme["bg_bottom"])
    draw = ImageDraw.Draw(img)
    draw_gradient_bg(draw, theme)
    draw_dot_pattern(draw, theme)

    tips = content["tips"]
    n = len(tips)

    # --- 上部タイトルエリア ---
    title_font = get_font(60)
    title_lines = wrap_text(content["title"], title_font, WIDTH - 140, draw)
    title_area_h = 150

    # タイトル背景（グロー付き半透明バー）
    draw.rectangle([0, 0, WIDTH, title_area_h], fill=theme["card_bg"])
    for g in range(8, 0, -2):
        ac = tuple(max(0, c // 4) for c in theme["accent"])
        draw.line([(0, title_area_h + g), (WIDTH, title_area_h + g)], fill=ac)
    draw.rectangle([0, title_area_h, WIDTH, title_area_h + 4], fill=theme["accent"])

    ty = 20
    for line in title_lines:
        draw_text_centered(draw, ty, line, title_font, theme["accent"], shadow=True)
        bbox = draw.textbbox((0, 0), line, font=title_font)
        ty += bbox[3] - bbox[1] + 8

    # --- ヒントカード（スライドイン） ---
    card_margin = 50
    card_start_y = title_area_h + 30
    available_h = HEIGHT - card_start_y - 80
    card_h = min(int(available_h / n) - 16, 200)

    tip_font = get_font(52)
    num_font = get_font(68)

    # 何個目まで表示するか
    show_count = min(n, int(local_t * (n + 1)) + 1)

    for i in range(n):
        card_y = card_start_y + i * (card_h + 16)

        if i < show_count:
            # スライドイン進捗（各カードの出現タイミング）
            card_appear_t = local_t * (n + 1) - i
            slide_ease = min(1.0, card_appear_t * 3)
            slide_ease = 1 - (1 - slide_ease) ** 2  # ease out

            # 左からスライドイン
            offset_x = int((1 - slide_ease) * (-WIDTH))
            cx1 = card_margin + offset_x
            cx2 = WIDTH - card_margin + offset_x

            # カード背景（グロー）
            glow_c = tuple(max(0, c // 3) for c in theme["card_border"])
            draw.rounded_rectangle(
                [cx1 - 4, card_y - 4, cx2 + 4, card_y + card_h + 4],
                radius=26, fill=glow_c
            )
            draw.rounded_rectangle(
                [cx1, card_y, cx2, card_y + card_h],
                radius=22, fill=theme["card_bg"]
            )
            # 左ボーダー（カラーライン）
            draw.rounded_rectangle(
                [cx1, card_y, cx1 + 10, card_y + card_h],
                radius=22, fill=theme["accent"]
            )

            # 番号（グロー）
            num_text = str(i + 1)
            num_bbox = draw.textbbox((0, 0), num_text, font=num_font)
            nx = cx1 + 30
            ny = card_y + (card_h - (num_bbox[3] - num_bbox[1])) // 2
            for dx in range(-3, 4, 3):
                for dy in range(-3, 4, 3):
                    draw.text((nx + dx, ny + dy), num_text,
                              font=num_font, fill=tuple(c // 3 for c in theme["accent"]))
            draw.text((nx, ny), num_text, font=num_font, fill=theme["accent"])

            # ヒントテキスト
            tip_lines = wrap_text(tips[i], tip_font, cx2 - cx1 - 130, draw)
            text_total_h = sum(
                draw.textbbox((0, 0), ln, font=tip_font)[3] + 8
                for ln in tip_lines
            )
            text_y = card_y + (card_h - text_total_h) // 2
            for line in tip_lines:
                draw.text((cx1 + 110, text_y), line, font=tip_font, fill=theme["text"])
                bbox = draw.textbbox((0, 0), line, font=tip_font)
                text_y += bbox[3] - bbox[1] + 8

        else:
            # 未表示：薄いプレースホルダー
            draw.rounded_rectangle(
                [card_margin, card_y, WIDTH - card_margin, card_y + card_h],
                radius=22, fill=(20, 20, 20)
            )
            num_font2 = get_font(52)
            draw.text((card_margin + 30, card_y + card_h // 2 - 30),
                      str(i + 1), font=num_font2, fill=(50, 50, 50))

    draw_progress_bar(draw, theme, local_t)
    return img


# ───────────────────────────────────────────────
# CTAエンディング（13〜15秒）
# ───────────────────────────────────────────────
def create_cta_frame(content, frame_num, cta_start, total_frames, theme):
    local_t = (frame_num - cta_start) / max(total_frames - cta_start - 1, 1)

    img = Image.new("RGB", (WIDTH, HEIGHT), color=theme["bg_bottom"])
    draw = ImageDraw.Draw(img)
    draw_gradient_bg(draw, theme)
    draw_dot_pattern(draw, theme)

    # --- 放射状グロー（中央から） ---
    for r in range(500, 0, -50):
        alpha = max(0, 15 - r // 35)
        gc = tuple(min(255, c + alpha) for c in theme["bg_mid"])
        draw.ellipse([WIDTH // 2 - r, HEIGHT // 2 - r,
                      WIDTH // 2 + r, HEIGHT // 2 + r], fill=gc)

    # --- ✅ アイコン（フェードイン＋スケール） ---
    ease = 1 - (1 - min(local_t * 2, 1.0)) ** 3
    icon_size = int(160 + 40 * ease)
    icon_font = get_font(icon_size)
    icon_y = HEIGHT // 2 - 460
    draw_text_centered(draw, icon_y, "✅", icon_font, theme["accent"], shadow=False)

    # --- まとめ完了！ ---
    done_font = get_font(88)
    draw_text_centered(draw, HEIGHT // 2 - 220, "まとめ完了！", done_font, theme["text"])

    # --- タイトル ---
    title_font = get_font(58)
    title_lines = wrap_text(content["title"], title_font, WIDTH - 120, draw)
    ty = HEIGHT // 2 - 90
    for line in title_lines:
        draw_text_centered(draw, ty, line, title_font, theme["accent"])
        bbox = draw.textbbox((0, 0), line, font=title_font)
        ty += bbox[3] - bbox[1] + 12

    # --- CTA ボタン（パルスアニメーション） ---
    pulse = 0.92 + 0.08 * math.sin(local_t * math.pi * 8)
    cta_data = [
        ("❤️  いいね & フォロー", theme["accent"],   (0, 0, 0)),
        ("🔔  保存して見返そう！", theme["card_bg"], theme["accent"]),
    ]
    cy = HEIGHT // 2 + 140
    for text, bg, fg in cta_data:
        cta_font = get_font(int(60 * pulse))
        bbox = draw.textbbox((0, 0), text, font=cta_font)
        bw = bbox[2] - bbox[0]
        bh = bbox[3] - bbox[1]
        bx = (WIDTH - bw) // 2
        pad = 28
        # ボタン描画
        draw_glow_rect(draw, bx - pad, cy - pad, bx + bw + pad, cy + bh + pad,
                       bg, radius=50, glow_size=5)
        draw.rounded_rectangle(
            [bx - pad, cy - pad, bx + bw + pad, cy + bh + pad],
            radius=50, outline=theme["accent"], width=3
        )
        draw.text((bx, cy), text, font=cta_font, fill=fg)
        cy += bh + 60 + pad * 2

    draw_progress_bar(draw, theme, 1.0)
    return img


# ───────────────────────────────────────────────
# メイン生成関数
# ───────────────────────────────────────────────
def create_video(content, output_path, duration=15, bgm_path=None):
    print(f"🎬 動画生成開始: {content['title']}")

    theme = random.choice(THEMES)
    hook_text = random.choice(HOOK_TEXTS)
    print(f"  🎨 テーマ: {theme['name']} | フック: {hook_text}")

    fps = 30
    total_frames = duration * fps
    hook_frames = fps * 3
    cta_frames  = fps * 2
    tips_frames = total_frames - hook_frames - cta_frames
    tips_start  = hook_frames
    tips_end    = hook_frames + tips_frames
    cta_start   = tips_end

    frames_dir = "/tmp/tiktok_frames"
    os.makedirs(frames_dir, exist_ok=True)

    print(f"  📸 {total_frames}フレーム生成中...")
    for i in range(total_frames):
        if i < hook_frames:
            frame = create_hook_frame(content, i, hook_frames, theme, hook_text)
        elif i < tips_end:
            frame = create_tips_frame(content, i, tips_start, tips_end, theme)
        else:
            frame = create_cta_frame(content, i, cta_start, total_frames, theme)

        frame.save(f"{frames_dir}/frame_{i:04d}.png")
        if i % 90 == 0:
            pct = int(i / total_frames * 100)
            print(f"  　{pct}% ({i}/{total_frames})")

    print("  🎞️  動画に変換中...")

    # BGMがある場合は合成、ない場合は映像のみ
    if bgm_path and os.path.exists(bgm_path):
        print(f"  🎵 BGM合成中: {bgm_path}")
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", f"{frames_dir}/frame_%04d.png",
            "-stream_loop", "-1",       # BGMをループ
            "-i", bgm_path,
            "-c:v", "libx264",
            "-c:a", "aac",
            "-b:a", "128k",
            "-shortest",                # 映像の長さに合わせる
            "-pix_fmt", "yuv420p",
            "-crf", "20",
            "-preset", "fast",
            "-af", f"volume=0.6,afade=t=in:st=0:d=1,afade=t=out:st={duration-2}:d=2",
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
        print(f"✅ 動画生成完了 {bgm_label}: {output_path}  ({size_mb:.1f}MB)")
    else:
        print(f"❌ エラー: {result.stderr[-500:]}")

    import shutil
    shutil.rmtree(frames_dir, ignore_errors=True)
    return output_path


if __name__ == "__main__":
    sample = {
        "title": "朝の準備が3分短くなる方法",
        "tips": [
            "前日に服を選んでおく",
            "朝食はスムージーに",
            "カバンは前夜にリセット",
            "シャワーは夜に済ます",
        ],
    }
    os.makedirs("./output", exist_ok=True)
    bgm = os.path.join(os.path.dirname(__file__), "bgm_chord.mp3")
    create_video(sample, "./output/test_video_v4.mp4", duration=15,
                 bgm_path=bgm if os.path.exists(bgm) else None)
