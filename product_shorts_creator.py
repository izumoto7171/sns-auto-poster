"""
商品写真を使ったYouTube Shorts 動画生成
docs/products.json の商品データ（実写真）からTopview AI風の動画を作る

使い方:
  python3.11 product_shorts_creator.py                    # ローテーションで1本生成+投稿
  python3.11 product_shorts_creator.py --id 1             # 商品ID指定
  python3.11 product_shorts_creator.py --id 6 --dry-run   # 動画生成のみ（投稿しない）
  python3.11 product_shorts_creator.py --list              # 商品一覧
"""
import os
import sys
import json
import io
import subprocess
import textwrap
import argparse
import urllib.request
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

BASE_DIR = Path(__file__).parent

# .env 読み込み
env_path = BASE_DIR / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

PRODUCTS_JSON = BASE_DIR / "docs" / "products.json"
OUTPUT_DIR    = BASE_DIR / "output" / "product_shorts"
POSTED_LOG    = BASE_DIR / "output" / "product_shorts_posted.json"

# Shorts サイズ（縦型）
W, H = 1080, 1920
FPS  = 30

# カテゴリ別カラーテーマ
CATEGORY_THEME = {
    "ガジェット":         {"bg": (10, 20, 50),  "accent": (0, 180, 255),   "text": (255, 255, 255)},
    "PC周辺機器":         {"bg": (10, 20, 50),  "accent": (0, 220, 180),   "text": (255, 255, 255)},
    "家具・デスク環境":   {"bg": (30, 20, 10),  "accent": (255, 180, 0),   "text": (255, 255, 255)},
    "サービス・サブスク": {"bg": (20, 10, 40),  "accent": (180, 100, 255), "text": (255, 255, 255)},
    "AIツール・アプリ":   {"bg": (10, 30, 30),  "accent": (0, 255, 160),   "text": (255, 255, 255)},
    "金融・カード":       {"bg": (40, 20, 5),   "accent": (255, 200, 50),  "text": (255, 255, 255)},
    "アニメグッズ":       {"bg": (40, 5, 30),   "accent": (255, 80, 180),  "text": (255, 255, 255)},
    "日本の文房具":       {"bg": (5, 30, 40),   "accent": (80, 200, 255),  "text": (255, 255, 255)},
    "日本のキッチングッズ":{"bg": (30, 40, 5),  "accent": (120, 220, 50),  "text": (255, 255, 255)},
    "日本の伝統アイテム": {"bg": (40, 10, 5),   "accent": (255, 120, 60),  "text": (255, 255, 255)},
    "日本のスキンケア":   {"bg": (40, 20, 30),  "accent": (255, 150, 200), "text": (255, 255, 255)},
    "日本のお菓子":       {"bg": (40, 25, 5),   "accent": (255, 180, 60),  "text": (255, 255, 255)},
}
DEFAULT_THEME = {"bg": (15, 15, 30), "accent": (0, 200, 255), "text": (255, 255, 255)}


# ─────────────────────────────────────────────
# ユーティリティ
# ─────────────────────────────────────────────
def load_products() -> list:
    with open(PRODUCTS_JSON, encoding="utf-8") as f:
        return json.load(f)


def load_font(size: int, bold: bool = False):
    """フォント読み込み（日本語対応）"""
    candidates = [
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/Library/Fonts/Arial Unicode MS.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def download_image(url: str, cache_dir: Path) -> Image.Image | None:
    """商品画像をダウンロード（キャッシュあり）"""
    cache_dir.mkdir(parents=True, exist_ok=True)
    fname = cache_dir / (url.split("/")[-1].split("?")[0] + ".png")
    if fname.exists():
        try:
            return Image.open(fname).convert("RGBA")
        except Exception:
            pass
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
        img = Image.open(io.BytesIO(data)).convert("RGBA")
        img.save(fname, format="PNG")
        return img
    except Exception as e:
        print(f"  画像DL失敗: {e}")
        return None


def wrap_text(text: str, font, max_width: int) -> list:
    """テキストを最大幅で折り返す"""
    lines = []
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    for paragraph in text.split("\n"):
        words = list(paragraph)
        current = ""
        for char in words:
            test = current + char
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] > max_width and current:
                lines.append(current)
                current = char
            else:
                current = test
        if current:
            lines.append(current)
    return lines


def draw_text_with_shadow(draw, pos, text, font, color, shadow_color=(0, 0, 0), shadow_offset=3):
    x, y = pos
    for dx in [-shadow_offset, 0, shadow_offset]:
        for dy in [-shadow_offset, 0, shadow_offset]:
            if dx != 0 or dy != 0:
                draw.text((x + dx, y + dy), text, font=font, fill=shadow_color)
    draw.text((x, y), text, font=font, fill=color)


def draw_multiline_centered(draw, text_lines: list, font, color, center_x, start_y, line_spacing=10):
    y = start_y
    for line in text_lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        draw_text_with_shadow(draw, (center_x - w // 2, y), line, font, color)
        y += bbox[3] - bbox[1] + line_spacing
    return y


# ─────────────────────────────────────────────
# フレーム生成
# ─────────────────────────────────────────────
def create_product_frame(
    product: dict,
    product_img: Image.Image | None,
    phase: str,  # "hook" | "product" | "benefits" | "cta"
    progress: float,  # 0.0〜1.0
    theme: dict,
) -> Image.Image:
    """1フレームを生成"""
    frame = Image.new("RGBA", (W, H), theme["bg"] + (255,))
    draw  = ImageDraw.Draw(frame)

    name     = product["name"]
    desc     = product.get("description", "")
    category = product.get("category", "")
    amazon   = product.get("amazonUrl", "")

    # フォント
    font_xl  = load_font(80, bold=True)
    font_lg  = load_font(58, bold=True)
    font_md  = load_font(46)
    font_sm  = load_font(38)
    font_xs  = load_font(32)

    accent = theme["accent"]
    white  = theme["text"]

    # ────────── グラデーション背景 ──────────
    bg_r, bg_g, bg_b = theme["bg"]
    for y in range(H):
        ratio = y / H
        r = int(bg_r + (accent[0] - bg_r) * ratio * 0.15)
        g = int(bg_g + (accent[1] - bg_g) * ratio * 0.15)
        b = int(bg_b + (accent[2] - bg_b) * ratio * 0.15)
        draw.line([(0, y), (W, y)], fill=(r, g, b, 255))

    # ────────── フェーズ別レイアウト ──────────
    if phase == "hook":
        # フック: 大きなテキスト + 商品名
        # 上部バー
        draw.rectangle([(0, 0), (W, 12)], fill=accent + (255,))
        draw.rectangle([(0, H - 12), (W, H)], fill=accent + (255,))

        # 「知ってた？」テキスト
        hook_lines = wrap_text("これ知ってた？", font_xl, W - 120)
        y = H // 2 - 200
        y = draw_multiline_centered(draw, hook_lines, font_xl, accent, W // 2, y, 20)

        # 商品名
        name_lines = wrap_text(name, font_lg, W - 120)
        y += 60
        y = draw_multiline_centered(draw, name_lines, font_lg, white, W // 2, y, 15)

        # カテゴリバッジ
        badge_text = f"  {category}  "
        bbox = draw.textbbox((0, 0), badge_text, font=font_sm)
        bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        bx = W // 2 - bw // 2
        by = y + 50
        draw.rounded_rectangle([(bx - 10, by - 8), (bx + bw + 10, by + bh + 8)],
                                radius=20, fill=accent + (200,))
        draw_text_with_shadow(draw, (bx, by), badge_text, font_sm, (0, 0, 0))

    elif phase == "product":
        # 商品写真メイン表示
        if product_img:
            # 写真を画面中央に大きく配置
            img_area_w = W - 80
            img_area_h = int(H * 0.62)
            img = product_img.copy().convert("RGBA")
            img.thumbnail((img_area_w, img_area_h), Image.LANCZOS)

            # 白い背景で商品を浮き立たせる
            pad = 30
            bg_w, bg_h = img.width + pad * 2, img.height + pad * 2
            bg_x = (W - bg_w) // 2
            bg_y = (H - bg_h) // 2 - 80
            draw.rounded_rectangle(
                [(bg_x, bg_y), (bg_x + bg_w, bg_y + bg_h)],
                radius=28,
                fill=(255, 255, 255, 240)
            )
            frame.paste(img, (bg_x + pad, bg_y + pad), img)

        # 商品名（下部）
        name_lines = wrap_text(name, font_md, W - 100)
        draw_multiline_centered(draw, name_lines, font_md, white, W // 2, H - 340, 12)

        # アクセントライン
        draw.rectangle([(60, H - 280), (W - 60, H - 274)], fill=accent + (255,))

    elif phase == "benefits":
        # ベネフィット表示（商品写真 小 + テキスト）
        if product_img:
            # 左上に小さく商品写真
            img = product_img.copy().convert("RGBA")
            img.thumbnail((280, 280), Image.LANCZOS)
            pad = 15
            bg_size = max(img.width, img.height) + pad * 2
            img_bg = Image.new("RGBA", (bg_size, bg_size), (255, 255, 255, 230))
            img_bg_draw = ImageDraw.Draw(img_bg)
            ix = (bg_size - img.width) // 2
            iy = (bg_size - img.height) // 2
            img_bg.paste(img, (ix, iy), img)
            frame.paste(img_bg, (60, 120), img_bg)

        # 商品名
        name_lines = wrap_text(name, font_md, W - 420)
        y = 130
        for line in name_lines:
            draw_text_with_shadow(draw, (380, y), line, font_md, white)
            bbox = draw.textbbox((0, 0), line, font=font_md)
            y += bbox[3] - bbox[1] + 8

        # 説明文をポイントに分解
        points = []
        sentences = desc.replace("。", "。\n").split("\n")
        for s in sentences:
            s = s.strip()
            if s and len(s) > 3:
                points.append(s)

        check_font = font_sm
        y = 500
        for i, point in enumerate(points[:4]):
            # チェックマーク
            draw.ellipse([(60, y + 4), (100, y + 44)], fill=accent + (255,))
            draw_text_with_shadow(draw, (74, y + 4), "✓", load_font(32), (0, 0, 0))

            # テキスト
            point_lines = wrap_text(point, check_font, W - 180)
            for line in point_lines[:2]:
                draw_text_with_shadow(draw, (120, y), line, check_font, white)
                bbox = draw.textbbox((0, 0), line, font=check_font)
                y += bbox[3] - bbox[1] + 6
            y += 30

        # アクセントライン
        draw.rectangle([(60, 460), (W - 60, 464)], fill=accent + (255,))

    elif phase == "cta":
        # CTA (Call to Action)
        # 背景を少し明るく
        draw.rectangle([(0, 0), (W, H)], fill=theme["bg"] + (180,))

        # 商品写真（中央上）
        if product_img:
            img = product_img.copy().convert("RGBA")
            img.thumbnail((500, 500), Image.LANCZOS)
            pad = 20
            bg_size = max(img.width, img.height) + pad * 2
            img_bg = Image.new("RGBA", (bg_size, bg_size), (255, 255, 255, 245))
            ix = (bg_size - img.width) // 2
            iy = (bg_size - img.height) // 2
            img_bg.paste(img, (ix, iy), img)
            px = (W - bg_size) // 2
            py = 200
            frame.paste(img_bg, (px, py), img_bg)

        # 商品名
        name_lines = wrap_text(name, font_md, W - 120)
        draw_multiline_centered(draw, name_lines, font_md, white, W // 2, 820, 10)

        # CTAボタン風
        btn_y = 1050
        draw.rounded_rectangle(
            [(80, btn_y), (W - 80, btn_y + 120)],
            radius=30, fill=accent + (255,)
        )
        cta_text = "Amazonで見る →"
        bbox = draw.textbbox((0, 0), cta_text, font=font_lg)
        bw = bbox[2] - bbox[0]
        draw_text_with_shadow(draw, ((W - bw) // 2, btn_y + 28), cta_text, font_lg, (0, 0, 0), shadow_color=(0, 0, 0, 100), shadow_offset=2)

        # プロフィールリンク誘導
        link_y = 1250
        draw.rectangle([(60, link_y - 10), (W - 60, link_y - 4)], fill=accent + (150,))
        link_lines = wrap_text("詳細はプロフィールのリンクから", font_sm, W - 120)
        draw_multiline_centered(draw, link_lines, font_sm, accent, W // 2, link_y, 8)

        # チャンネル名
        ch_text = "@JapanAdCheck"
        bbox = draw.textbbox((0, 0), ch_text, font=font_xs)
        draw_text_with_shadow(
            draw, ((W - (bbox[2] - bbox[0])) // 2, H - 220),
            ch_text, font_xs, (180, 180, 180)
        )

    # ── 共通: 上部ロゴ（hookとproduct以外はミニ）
    if phase not in ("hook",):
        logo_text = "Japan AdCheck"
        bbox = draw.textbbox((0, 0), logo_text, font=font_xs)
        bw = bbox[2] - bbox[0]
        draw.text((W - bw - 30, 30), logo_text, font=font_xs, fill=accent + (200,))

    return frame.convert("RGB")


# ─────────────────────────────────────────────
# 動画生成
# ─────────────────────────────────────────────
def create_product_video(product: dict, output_path: str) -> bool:
    """商品写真使用のYouTube Shorts動画を生成"""
    print(f"\n動画生成: {product['name']}")

    theme = CATEGORY_THEME.get(product.get("category", ""), DEFAULT_THEME)

    # 商品画像ダウンロード
    img_url = product.get("image", "")
    cache_dir = BASE_DIR / "output" / "img_cache"
    product_img = None
    if img_url:
        print(f"  画像DL: {img_url[:60]}...")
        product_img = download_image(img_url, cache_dir)
        if product_img:
            print("  画像OK")

    # フェーズ設定（合計25秒）
    phases = [
        ("hook",     3),   # 3秒: フック
        ("product",  9),   # 9秒: 商品写真メイン
        ("benefits", 9),   # 9秒: ベネフィット
        ("cta",      4),   # 4秒: CTA
    ]

    # ffmpeg パイプ経由でフレームを渡す
    output_path = str(output_path)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    total_frames = sum(secs * FPS for _, secs in phases)
    print(f"  {total_frames}フレーム生成中 ({total_frames // FPS}秒)...")

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{W}x{H}",
        "-pix_fmt", "rgb24",
        "-r", str(FPS),
        "-i", "pipe:0",
        "-vcodec", "libx264",
        "-pix_fmt", "yuv420p",
        "-crf", "23",
        "-preset", "fast",
        output_path
    ]

    try:
        proc = subprocess.Popen(
            ffmpeg_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        frame_count = 0
        for phase, secs in phases:
            n_frames = secs * FPS
            for i in range(n_frames):
                progress = i / n_frames
                frame = create_product_frame(product, product_img, phase, progress, theme)
                proc.stdin.write(frame.tobytes())
                frame_count += 1
                if frame_count % 60 == 0:
                    print(f"  {frame_count}/{total_frames}フレーム", end="\r")

        proc.stdin.close()
        proc.wait()

        if proc.returncode == 0 and Path(output_path).exists():
            size_mb = Path(output_path).stat().st_size / 1024 / 1024
            print(f"\n  動画生成完了: {output_path} ({size_mb:.1f}MB)")
            return True
        else:
            print(f"\n  ffmpegエラー (code: {proc.returncode})")
            return False

    except Exception as e:
        print(f"\n  エラー: {e}")
        return False


def generate_description(product: dict) -> str:
    """YouTube説明文（アフィリエイトリンク付き）"""
    name    = product["name"]
    desc    = product.get("description", "")
    amazon  = product.get("amazonUrl", "")
    rakuten = product.get("rakutenUrl", "")
    cat     = product.get("category", "")

    lines = [
        f"【{name}】",
        "",
        desc,
        "",
    ]
    if amazon:
        lines += [f"▶ Amazon: {amazon}", ""]
    if rakuten:
        lines += [f"▶ 楽天市場: {rakuten}", ""]

    lines += [
        "━━━━━━━━━━━━━━━━",
        "商品まとめサイト → プロフィールのリンクから",
        "https://izumoto7171.github.io/sns-auto-poster/",
        "━━━━━━━━━━━━━━━━",
        "",
        f"#{cat} #日本 #おすすめ #便利グッズ #Shorts",
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────
# 投稿済みログ
# ─────────────────────────────────────────────
def load_log() -> list:
    if POSTED_LOG.exists():
        with open(POSTED_LOG, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_log(log: list):
    POSTED_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(POSTED_LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def get_next_product(products: list, log: list) -> dict | None:
    posted_ids = {e["product_id"] for e in log}
    for p in products:
        if p["id"] not in posted_ids:
            return p
    # 全部投稿済み → リセット
    print("全商品投稿済み。ローテーションをリセット。")
    return products[0] if products else None


# ─────────────────────────────────────────────
# メイン
# ─────────────────────────────────────────────
def run(product_id: int = None, dry_run: bool = False):
    products = load_products()
    log      = load_log()

    if product_id:
        product = next((p for p in products if p["id"] == product_id), None)
        if not product:
            print(f"商品ID {product_id} が見つかりません")
            sys.exit(1)
    else:
        product = get_next_product(products, log)
        if not product:
            print("商品データなし")
            sys.exit(1)

    print(f"商品: [{product['id']}] {product['name']} ({product.get('category','')})")

    output_path = OUTPUT_DIR / f"product_{product['id']:02d}_{product['name'][:20].replace(' ', '_')}.mp4"
    success = create_product_video(product, str(output_path))
    if not success:
        sys.exit(1)

    if dry_run:
        print(f"\n[DRY RUN] 動画生成のみ: {output_path}")
        return

    # YouTube アップロード
    sys.path.insert(0, str(BASE_DIR / "youtube_automation"))
    from youtube_uploader import upload_video

    name = product["name"]
    title = f"【日本の{product.get('category','')}】{name} #Shorts"
    if len(title) > 60:
        title = f"{name} #Shorts"

    desc = generate_description(product)

    tags = [name, "日本", "便利グッズ", "おすすめ", product.get("category",""),
            "Shorts", "shorts", "Japan", "Japanese"]

    video_id = upload_video(
        video_path=str(output_path),
        title=title,
        description=desc,
        tags=tags,
        privacy="public",
        category_id="22",
    )

    if video_id:
        entry = {
            "product_id":   product["id"],
            "product_name": product["name"],
            "video_id":     video_id,
            "url":          f"https://www.youtube.com/shorts/{video_id}",
            "datetime":     __import__("datetime").datetime.now().isoformat(),
        }
        log.append(entry)
        save_log(log)
        print(f"\n投稿完了: https://www.youtube.com/shorts/{video_id}")
    else:
        print("アップロード失敗")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="商品写真でYouTube Shorts生成・投稿")
    parser.add_argument("--id", type=int, default=None, help="商品ID (products.jsonのid)")
    parser.add_argument("--dry-run", action="store_true", help="動画生成のみ（投稿しない）")
    parser.add_argument("--list", action="store_true", help="商品一覧")
    args = parser.parse_args()

    if args.list:
        products = load_products()
        log_ids  = {e["product_id"] for e in load_log()}
        print(f"\n商品一覧 ({len(products)}件):")
        for p in products:
            posted = " [投稿済]" if p["id"] in log_ids else ""
            print(f"  [{p['id']:2d}] {p['name'][:30]:<30}  {p.get('category','')}{posted}")
    else:
        run(product_id=args.id, dry_run=args.dry_run)
