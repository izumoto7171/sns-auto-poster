"""
アフィリエイト商品特化 YouTube Shorts 動画生成
Topview AI 相当の機能をPython + Gemini で実装

使い方:
  python affiliate_video_creator.py                    # テスト動画
  python affiliate_video_creator.py --product rakuten_card
"""
import os
import sys
import io
import random
import subprocess
import textwrap
import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = Path(__file__).parent

# ─────────────────────────────────────────────
# .env 読み込み
# ─────────────────────────────────────────────
def load_env():
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

load_env()

# ─────────────────────────────────────────────
# サイズ定数（YouTube Shorts縦型）
# ─────────────────────────────────────────────
W, H = 1080, 1920
FPS = 30

# ─────────────────────────────────────────────
# カテゴリ別カラーテーマ
# ─────────────────────────────────────────────
CATEGORY_THEMES = {
    "投資": {
        "bg":      [(10, 20, 50), (5, 10, 30)],
        "accent":  (0, 200, 100),
        "accent2": (0, 150, 70),
        "text":    (255, 255, 255),
        "emoji":   "📈",
    },
    "クレカ": {
        "bg":      [(20, 5, 50), (10, 2, 30)],
        "accent":  (255, 180, 0),
        "accent2": (220, 140, 0),
        "text":    (255, 255, 255),
        "emoji":   "💳",
    },
    "副業": {
        "bg":      [(0, 20, 50), (0, 10, 30)],
        "accent":  (0, 180, 255),
        "accent2": (0, 120, 200),
        "text":    (255, 255, 255),
        "emoji":   "💰",
    },
    "生産性": {
        "bg":      [(30, 10, 0), (15, 5, 0)],
        "accent":  (255, 120, 0),
        "accent2": (200, 80, 0),
        "text":    (255, 255, 255),
        "emoji":   "⚡",
    },
    "default": {
        "bg":      [(15, 15, 40), (5, 5, 20)],
        "accent":  (160, 80, 255),
        "accent2": (120, 40, 220),
        "text":    (255, 255, 255),
        "emoji":   "✨",
    },
}

# ─────────────────────────────────────────────
# フォント取得
# ─────────────────────────────────────────────
def get_font(size: int, bold: bool = False):
    """macOS / Linux で使えるフォントを優先順で試す"""
    candidates = [
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/Supplemental/Hiragino Sans GB.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


# ─────────────────────────────────────────────
# グラデーション背景
# ─────────────────────────────────────────────
def draw_gradient_bg(draw, colors):
    top, bottom = colors
    for y in range(H):
        ratio = y / H
        r = int(top[0] + (bottom[0] - top[0]) * ratio)
        g = int(top[1] + (bottom[1] - top[1]) * ratio)
        b = int(top[2] + (bottom[2] - top[2]) * ratio)
        draw.line([(0, y), (W, y)], fill=(r, g, b))


# ─────────────────────────────────────────────
# テキスト折り返し描画
# ─────────────────────────────────────────────
def draw_wrapped_text(draw, text, font, color, center_x, start_y, max_width, line_spacing=1.3):
    """折り返しテキストを中央寄せで描画。最後のy座標を返す"""
    chars_per_line = max(1, max_width // (font.size if hasattr(font, 'size') else 40))
    lines = []
    for para in text.split("\n"):
        if not para:
            lines.append("")
            continue
        wrapped = textwrap.wrap(para, width=chars_per_line)
        lines.extend(wrapped if wrapped else [para])

    font_h = font.size if hasattr(font, 'size') else 40
    total_h = int(len(lines) * font_h * line_spacing)
    y = start_y - total_h // 2

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        x = center_x - tw // 2
        # 影
        draw.text((x + 3, y + 3), line, font=font, fill=(0, 0, 0, 150))
        draw.text((x, y), line, font=font, fill=color)
        y += int(font_h * line_spacing)

    return y


# ─────────────────────────────────────────────
# アクセントバー
# ─────────────────────────────────────────────
def draw_accent_bar(draw, y, color, width=W-80):
    x0 = (W - width) // 2
    draw.rounded_rectangle([x0, y, x0 + width, y + 6], radius=3, fill=color)


# ─────────────────────────────────────────────
# フレーム: フック（0〜2秒）
# ─────────────────────────────────────────────
def create_hook_frame(theme, product_name, hook_text, frame_i, total_hook):
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    draw_gradient_bg(draw, theme["bg"])

    progress = frame_i / max(1, total_hook)
    alpha_scale = min(1.0, progress * 3)  # フェードイン

    # アクセント装飾
    emoji = theme["emoji"]
    draw.text((W // 2 - 60, 280), emoji * 3, font=get_font(80), fill=theme["accent"])

    # フックテキスト
    hook_font = get_font(72, bold=True)
    draw_wrapped_text(draw, hook_text, hook_font, theme["text"], W // 2, H // 2 - 100, W - 120)

    # 商品名
    name_font = get_font(52)
    draw_accent_bar(draw, H // 2 + 80, theme["accent"])
    draw_wrapped_text(draw, product_name, name_font, theme["accent"], W // 2, H // 2 + 200, W - 160)

    # 下部注目帯
    draw.rectangle([0, H - 200, W, H], fill=(*theme["accent2"], 200))
    sub_font = get_font(44)
    draw_wrapped_text(draw, "詳細はプロフィールのリンクから👇", sub_font,
                      theme["text"], W // 2, H - 100, W - 80)

    return img


# ─────────────────────────────────────────────
# フレーム: ベネフィット（3〜12秒）
# ─────────────────────────────────────────────
def create_benefit_frame(theme, product_name, benefit, idx, total_benefits, progress):
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    draw_gradient_bg(draw, theme["bg"])

    # 上部：商品名ヘッダー
    draw.rectangle([0, 0, W, 160], fill=theme["accent2"])
    name_font = get_font(48, bold=True)
    draw_wrapped_text(draw, product_name, name_font, theme["text"], W // 2, 80, W - 80)

    # 連番バッジ
    badge_x, badge_y = 80, 240
    draw.ellipse([badge_x - 50, badge_y - 50, badge_x + 50, badge_y + 50], fill=theme["accent"])
    num_font = get_font(56, bold=True)
    draw.text((badge_x - 20, badge_y - 35), str(idx + 1), font=num_font, fill=(0, 0, 0))

    # 見出しライン
    draw_accent_bar(draw, 320, theme["accent"], width=W - 160)

    # ベネフィットテキスト
    ben_font = get_font(68, bold=True)
    draw_wrapped_text(draw, benefit, ben_font, theme["text"], W // 2, H // 2 - 50, W - 120)

    # プログレスバー
    bar_w = W - 120
    bar_x = 60
    bar_y = H - 240
    draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + 16],
                            radius=8, fill=(60, 60, 60))
    filled = int(bar_w * progress)
    if filled > 0:
        draw.rounded_rectangle([bar_x, bar_y, bar_x + filled, bar_y + 16],
                                radius=8, fill=theme["accent"])

    # カウント
    count_font = get_font(36)
    draw.text((bar_x, bar_y + 30), f"{idx + 1}/{total_benefits}",
              font=count_font, fill=theme["accent"])

    return img


# ─────────────────────────────────────────────
# フレーム: オファー（最後の2〜3秒）
# ─────────────────────────────────────────────
def create_offer_frame(theme, product_name, offer_text, commission, cta):
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    draw_gradient_bg(draw, theme["bg"])

    # 背景強調パネル
    panel_y1 = H // 2 - 350
    panel_y2 = H // 2 + 350
    draw.rounded_rectangle([40, panel_y1, W - 40, panel_y2],
                            radius=40, fill=(30, 30, 70, 220))

    # キラキラ装飾
    draw.text((W // 2 - 80, panel_y1 + 30), "🎁✨🎁", font=get_font(60), fill=theme["accent"])

    # オファーテキスト
    offer_font = get_font(66, bold=True)
    y = draw_wrapped_text(draw, offer_text, offer_font, theme["accent"],
                          W // 2, panel_y1 + 200, W - 120)

    # アクセントライン
    draw_accent_bar(draw, y + 20, theme["accent"])

    # 報酬テキスト（もしあれば）
    if commission:
        com_font = get_font(48)
        y = draw_wrapped_text(draw, f"報酬：{commission}", com_font,
                              (200, 255, 150), W // 2, y + 80, W - 140)

    # CTA
    cta_font = get_font(52, bold=True)
    draw_wrapped_text(draw, cta, cta_font, theme["text"], W // 2, panel_y2 - 100, W - 100)

    # 下部バナー
    draw.rectangle([0, H - 180, W, H], fill=theme["accent"])
    banner_font = get_font(44, bold=True)
    draw_wrapped_text(draw, "👆 プロフィールのリンクをチェック！", banner_font,
                      (0, 0, 0), W // 2, H - 90, W - 80)

    return img


# ─────────────────────────────────────────────
# Gemini でベネフィット生成
# ─────────────────────────────────────────────
def generate_benefits_with_gemini(product: dict) -> dict:
    """Gemini API で商品ベネフィット・フック・CTAを生成"""
    try:
        import google.generativeai as genai
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY が未設定")

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash-lite")

        prompt = f"""
あなたはYouTube Shorts向けアフィリエイト動画の台本ライターです。

商品情報:
- 商品名: {product['name']}
- カテゴリ: {product.get('category', '副業')}
- 説明: {product.get('description', '')}
- CTA: {product.get('cta', '今すぐチェック →')}

以下をJSON形式で出力してください（他のテキスト不要）:
{{
  "hook": "視聴者を引き込む1行フックテキスト（20文字以内、疑問形か驚き系）",
  "benefits": [
    "ベネフィット1（15文字以内、具体的な数字や実益を含む）",
    "ベネフィット2（15文字以内）",
    "ベネフィット3（15文字以内）",
    "ベネフィット4（15文字以内）"
  ],
  "offer_text": "限定オファーや特典のテキスト（20文字以内）",
  "hashtags": "#副業 #AI副業 #おすすめ #お金 #節約"
}}
"""
        response = model.generate_content(prompt)
        text = response.text.strip()

        # JSON部分を抽出
        import json, re
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        print(f"⚠️  Gemini生成失敗: {e}")

    # フォールバック
    return {
        "hook": f"{product['name']}知ってる？",
        "benefits": [
            "スマホだけで始められる",
            "無料登録でスタート",
            "初心者でも安心サポート",
            "今すぐ収益化できる",
        ],
        "offer_text": "今なら無料で始められる！",
        "hashtags": "#副業 #AI副業 #おすすめ",
    }


# ─────────────────────────────────────────────
# メイン動画生成
# ─────────────────────────────────────────────
def create_affiliate_video(product: dict, output_path: str,
                           duration: int = 15, bgm_path: str = None) -> str:
    """
    商品情報からYouTube Shorts動画を生成

    product: {
        name, category, description, cta, url,
        commission (optional)
    }
    output_path: 出力MP4パス
    """
    print(f"🎬 アフィリエイト動画生成: {product['name']}")

    # テーマ選択
    category = product.get("category", "default")
    theme = CATEGORY_THEMES.get(category, CATEGORY_THEMES["default"])

    # Gemini でコンテンツ生成
    print("  ✍️  Gemini でベネフィット生成中...")
    ai_content = generate_benefits_with_gemini(product)

    hook_text   = ai_content.get("hook", f"{product['name']}を使ってみた")
    benefits    = ai_content.get("benefits", ["メリット1", "メリット2", "メリット3", "メリット4"])
    offer_text  = ai_content.get("offer_text", "今すぐチェック！")
    hashtags    = ai_content.get("hashtags", "#副業 #AI副業")

    product_name = product["name"]
    commission   = product.get("commission", "")
    cta          = product.get("cta", "プロフィールから登録 →")

    # フレーム配分
    total_frames   = duration * FPS
    hook_frames    = FPS * 3                              # 3秒
    benefit_frames = FPS * (duration - 5)                # 中間
    offer_frames   = FPS * 2                             # 2秒
    frames_per_ben = benefit_frames // max(1, len(benefits))

    frames_dir = "/tmp/affiliate_frames"
    import shutil
    shutil.rmtree(frames_dir, ignore_errors=True)
    os.makedirs(frames_dir, exist_ok=True)

    print(f"  📸 {total_frames}フレーム生成中...")
    frame_idx = 0

    # フック
    for i in range(hook_frames):
        f = create_hook_frame(theme, product_name, hook_text, i, hook_frames)
        f.save(f"{frames_dir}/frame_{frame_idx:04d}.png")
        frame_idx += 1

    # ベネフィット
    for b_idx, benefit in enumerate(benefits):
        for i in range(frames_per_ben):
            progress = (b_idx * frames_per_ben + i) / benefit_frames
            f = create_benefit_frame(theme, product_name, benefit, b_idx, len(benefits), progress)
            f.save(f"{frames_dir}/frame_{frame_idx:04d}.png")
            frame_idx += 1

    # 余剰フレームを最後のベネフィットで埋める
    while frame_idx < total_frames - offer_frames:
        f = create_benefit_frame(theme, product_name, benefits[-1], len(benefits) - 1, len(benefits), 1.0)
        f.save(f"{frames_dir}/frame_{frame_idx:04d}.png")
        frame_idx += 1

    # オファー
    while frame_idx < total_frames:
        f = create_offer_frame(theme, product_name, offer_text, commission, cta)
        f.save(f"{frames_dir}/frame_{frame_idx:04d}.png")
        frame_idx += 1

    print("  🎞️  動画に変換中...")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if bgm_path and os.path.exists(bgm_path):
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(FPS),
            "-i", f"{frames_dir}/frame_%04d.png",
            "-stream_loop", "-1",
            "-i", bgm_path,
            "-c:v", "libx264", "-c:a", "aac", "-b:a", "128k",
            "-shortest", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "fast",
            "-af", f"volume=0.5,afade=t=in:st=0:d=1,afade=t=out:st={duration-2}:d=2",
            output_path,
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(FPS),
            "-i", f"{frames_dir}/frame_%04d.png",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-crf", "20", "-preset", "fast",
            output_path,
        ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    shutil.rmtree(frames_dir, ignore_errors=True)

    if result.returncode == 0:
        size_mb = Path(output_path).stat().st_size / 1024 / 1024
        print(f"✅ 動画生成完了: {output_path} ({size_mb:.1f}MB)")
    else:
        print(f"❌ ffmpegエラー: {result.stderr[-500:]}")
        return None

    return output_path


# ─────────────────────────────────────────────
# YouTube 説明文生成
# ─────────────────────────────────────────────
def generate_youtube_description(product: dict, ai_content: dict = None) -> str:
    """YouTube Shorts 説明文（アフィリエイトリンク付き）"""
    name       = product["name"]
    url        = product.get("url", "")
    desc       = product.get("description", "")
    commission = product.get("commission", "")
    hashtags   = (ai_content or {}).get("hashtags", "#副業 #AI副業 #おすすめ")

    lines = [
        f"【{name}】気になる方はこちら👇",
        url,
        "",
        f"📌 {desc}",
    ]
    if commission:
        lines.append(f"💰 報酬単価: {commission}")
    lines += [
        "",
        "━━━━━━━━━━━━━━━━",
        "✅ 他のおすすめもプロフィールから！",
        "━━━━━━━━━━━━━━━━",
        "",
        hashtags,
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="アフィリエイト動画生成")
    parser.add_argument("--product", "-p", default="rakuten_card",
                        help="商品ID (keywords_db の AFFILIATE_PROGRAMS キー)")
    parser.add_argument("--output", "-o", default=None, help="出力パス")
    parser.add_argument("--duration", "-d", type=int, default=15, help="動画秒数")
    args = parser.parse_args()

    # .env 読み込み
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    sys.path.insert(0, str(BASE_DIR))
    try:
        from money_agent.keywords_db import AFFILIATE_PROGRAMS, _resolve_affiliate_url
        product = AFFILIATE_PROGRAMS.get(args.product)
        if product:
            product = _resolve_affiliate_url(product)
        if not product:
            print(f"⚠️  商品ID '{args.product}' が見つかりません。使用可能: {list(AFFILIATE_PROGRAMS.keys())}")
            # テスト用フォールバック
            product = {
                "name": "楽天カード",
                "commission": "7,000〜10,000円/件",
                "category": "クレカ",
                "url": "https://card.rakuten.co.jp/",
                "description": "年会費永年無料・ポイント還元率1%・新規入会で最大8,000ポイント",
                "cta": "楽天カードを申し込む →",
            }
    except ImportError:
        product = {
            "name": "楽天カード",
            "commission": "7,000〜10,000円/件",
            "category": "クレカ",
            "url": "https://card.rakuten.co.jp/",
            "description": "年会費永年無料・ポイント還元率1%・新規入会で最大8,000ポイント",
            "cta": "楽天カードを申し込む →",
        }

    output = args.output or str(BASE_DIR / "output" / f"affiliate_{args.product}.mp4")
    bgm = str(BASE_DIR / "bgm_upbeat.mp3")

    create_affiliate_video(product, output, duration=args.duration,
                           bgm_path=bgm if Path(bgm).exists() else None)
    print(f"\n説明文プレビュー:\n{generate_youtube_description(product)}")
