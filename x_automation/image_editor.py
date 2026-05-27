"""
スマホ編集風レビュー画像生成
商品の実物写真（楽天/Amazon画像URL）をベースに、
Geminiが生成した生々しいレビューテキストをオーバーレイして
「人間がアプリでポチポチ編集した」感の1080x1080画像を生成する。

フロー:
  1. 白背景 1080x1080 キャンバス
  2. 商品画像URLからDL → 中央に配置
  3. 上部に商品名（短縮）
  4. 下部にベージュ帯 + レビューテキスト（全体を-3度傾け）
"""
import os
import io
import math
import tempfile
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime
from typing import Optional


# ─────────────────────────────────────────
# 定数
# ─────────────────────────────────────────
CANVAS_SIZE  = 1080          # 正方形
BG_COLOR     = (255, 255, 255)   # 白背景
NAME_COLOR   = (40, 40, 40)      # 商品名テキスト（濃いグレー）
REVIEW_BG    = (250, 243, 230)   # レビュー帯（温かみのあるベージュ）
REVIEW_COLOR = (50, 40, 30)      # レビューテキスト（ほぼ黒）
ACCENT_COLOR = (220, 80, 60)     # アクセント（レビュー星など）

TILT_ANGLE   = -3.0   # 傾き角度（度）。負 = 反時計回り

# フォント候補（OS別にフォールバック）
_FONT_CANDIDATES = [
    # macOS — 丸ゴシック系
    "/System/Library/Fonts/ヒラギノ丸ゴ ProN W4.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    # macOS — AppleGothic
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    # Ubuntu / GitHub Actions
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJKjp-Regular.otf",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    # 汎用フォールバック
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _get_font(size: int, bold: bool = False):
    """日本語対応フォントを取得。見つからなければデフォルトを返す。"""
    from PIL import ImageFont

    # ボールドはヒラギノ W6 を優先
    bold_candidates = []
    if bold:
        bold_candidates = [
            "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
            "/System/Library/Fonts/ヒラギノ角ゴシック W9.ttc",
        ]

    for path in (bold_candidates + _FONT_CANDIDATES):
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _download_image(url: str, timeout: int = 10):
    """URLから画像をダウンロードしてPIL Imageを返す。失敗時はNone。"""
    try:
        from PIL import Image
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        return Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception as e:
        print(f"  [ImageEditor] 画像DL失敗 ({url[:60]}...): {e}")
        return None


def _wrap_text(text: str, font, max_width: int, draw) -> list[str]:
    """テキストを指定幅で折り返す（日本語対応）"""
    lines = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            lines.append("")
            continue
        current = ""
        for char in paragraph:
            test = current + char
            try:
                bbox = draw.textbbox((0, 0), test, font=font)
                w = bbox[2] - bbox[0]
            except Exception:
                w = len(test) * (font.size if hasattr(font, "size") else 12)
            if w > max_width and current:
                lines.append(current)
                current = char
            else:
                current = test
        if current:
            lines.append(current)
    return lines


def _draw_rounded_rect(draw, xy, radius: int, fill):
    """角丸矩形を描画"""
    from PIL import ImageDraw
    x0, y0, x1, y1 = xy
    r = radius
    draw.rectangle([x0 + r, y0, x1 - r, y1], fill=fill)
    draw.rectangle([x0, y0 + r, x1, y1 - r], fill=fill)
    draw.ellipse([x0, y0, x0 + 2*r, y0 + 2*r], fill=fill)
    draw.ellipse([x1 - 2*r, y0, x1, y0 + 2*r], fill=fill)
    draw.ellipse([x0, y1 - 2*r, x0 + 2*r, y1], fill=fill)
    draw.ellipse([x1 - 2*r, y1 - 2*r, x1, y1], fill=fill)


def create_review_image(
    product_name: str,
    review_text: str,
    image_url: str,
    output_path: Optional[str] = None,
) -> str:
    """
    商品レビュー画像を生成してファイルパスを返す。

    Args:
        product_name: 商品名（長い場合は自動短縮）
        review_text:  Geminiが生成したレビューテキスト（改行含んでもOK）
        image_url:    商品画像のURL（楽天・Amazon）
        output_path:  保存先パス（省略時は /tmp に自動生成）

    Returns:
        生成した画像ファイルのパス。失敗時は空文字列。
    """
    try:
        from PIL import Image, ImageDraw, ImageFilter
    except ImportError:
        print("⚠️  Pillowが未インストール: pip install Pillow")
        return ""

    try:
        # ── キャンバス作成 ─────────────────────────────────
        canvas = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), BG_COLOR + (255,))
        draw   = ImageDraw.Draw(canvas)

        # ── 商品画像を中央に配置 ───────────────────────────
        product_img = None
        if image_url:
            product_img = _download_image(image_url)

        if product_img:
            # 商品画像エリア（キャンバスの上60%）
            img_area_h = int(CANVAS_SIZE * 0.60)
            img_area_w = CANVAS_SIZE - 80  # 左右40pxマージン

            # アスペクト比を維持してリサイズ
            orig_w, orig_h = product_img.size
            scale = min(img_area_w / orig_w, img_area_h / orig_h)
            new_w = int(orig_w * scale)
            new_h = int(orig_h * scale)
            product_img = product_img.resize((new_w, new_h), Image.LANCZOS)

            # 中央配置（上寄り）
            x_pos = (CANVAS_SIZE - new_w) // 2
            y_pos = 120 + (img_area_h - new_h) // 2  # 上部に商品名スペースを確保
            canvas.paste(product_img, (x_pos, y_pos), product_img)
        else:
            # 画像DL失敗時：プレースホルダー矩形
            draw.rectangle([(100, 120), (980, 700)],
                           fill=(240, 240, 240), outline=(200, 200, 200), width=2)
            draw.text((CANVAS_SIZE // 2, 410), "📦",
                      font=_get_font(80), fill=(180, 180, 180), anchor="mm")

        # ── 商品名（上部） ─────────────────────────────────
        font_name   = _get_font(36, bold=True)
        max_name_w  = CANVAS_SIZE - 80
        short_name  = product_name[:25] + "…" if len(product_name) > 25 else product_name

        # 商品名の背景（薄いホワイトのグラデーション帯）
        draw.rectangle([(0, 0), (CANVAS_SIZE, 110)], fill=(255, 255, 255, 220))
        try:
            draw.text((CANVAS_SIZE // 2, 55), short_name,
                      font=font_name, fill=NAME_COLOR, anchor="mm")
        except TypeError:
            # anchor未対応のフォントフォールバック
            bbox = draw.textbbox((0, 0), short_name, font=font_name)
            tx = (CANVAS_SIZE - (bbox[2] - bbox[0])) // 2
            draw.text((tx, 30), short_name, font=font_name, fill=NAME_COLOR)

        # ── レビューエリア（下部・傾けてオーバーレイ） ──────────
        _overlay_review_tilted(canvas, review_text)

        # ── 最終出力（RGB変換） ────────────────────────────
        result = canvas.convert("RGB")

        if output_path is None:
            ts = int(datetime.now().timestamp())
            output_path = os.path.join(tempfile.gettempdir(), f"review_card_{ts}.jpg")

        result.save(output_path, format="JPEG", quality=92, optimize=True)
        print(f"  [ImageEditor] レビュー画像生成: {output_path}")
        return output_path

    except Exception as e:
        print(f"  [ImageEditor] 生成エラー: {e}")
        return ""


def _overlay_review_tilted(canvas, review_text: str):
    """
    レビューテキストエリアを-3度傾けてキャンバスに合成する。
    「人間がスマホアプリで貼り付けた」ような見た目を演出。
    """
    from PIL import Image, ImageDraw

    # レビューエリアのサイズ（キャンバスよりやや広めに作って傾けた後でも収まるように）
    area_w = CANVAS_SIZE - 60   # 左右30pxはみ出し許容
    area_h = 310                 # 高さ固定

    font_review = _get_font(30)
    font_star   = _get_font(28)

    # 一時レビューレイヤー（透明背景）
    review_layer = Image.new("RGBA", (area_w, area_h), (0, 0, 0, 0))
    rd           = ImageDraw.Draw(review_layer)

    # ベージュ帯（角丸）
    _draw_rounded_rect(rd, (0, 0, area_w - 1, area_h - 1),
                       radius=18, fill=REVIEW_BG + (240,))

    # 左端のアクセントバー
    rd.rectangle([(14, 18), (20, area_h - 18)], fill=ACCENT_COLOR + (200,))

    # 星マーク（固定で ★★★★☆ 表示）
    star_text = "★★★★☆  実際に使ってみた感想"
    try:
        rd.text((36, 22), star_text, font=font_star, fill=ACCENT_COLOR + (230,))
    except Exception:
        rd.text((36, 22), star_text, font=font_star, fill=ACCENT_COLOR)

    # レビューテキスト
    text_y    = 70
    line_h    = 42
    max_txt_w = area_w - 60  # 左右マージン

    wrapped = _wrap_text(review_text, font_review, max_txt_w, rd)
    # 最大4行まで
    for i, line in enumerate(wrapped[:4]):
        if not line.strip():
            text_y += line_h // 2
            continue
        try:
            rd.text((36, text_y), line, font=font_review, fill=REVIEW_COLOR + (255,))
        except Exception:
            rd.text((36, text_y), line, font=font_review, fill=REVIEW_COLOR)
        text_y += line_h

    # ── 傾け処理 ────────────────────────────────────────────
    rotated = review_layer.rotate(
        TILT_ANGLE,
        expand=True,
        resample=Image.BICUBIC,
        fillcolor=(0, 0, 0, 0),
    )

    # 貼り付け位置（下部中央。傾けると少しはみ出るため微調整）
    rx = (CANVAS_SIZE - rotated.width) // 2
    ry = CANVAS_SIZE - rotated.height - 20  # 下から20px

    canvas.paste(rotated, (rx, ry), rotated)


# ─────────────────────────────────────────
# 単体テスト用
# ─────────────────────────────────────────
if __name__ == "__main__":
    test_url    = "https://thumbnail.image.rakuten.co.jp/@0_mall/biccamera/cabinet/product/1617/00000006036769_a01.jpg"
    test_name   = "パイロット フリクションボール3 スリム 0.38mm ブラック"
    test_review = "半信半疑で買ったんだけど、正直これはかなり良かった。\n書き味がなめらかで消えやすい。3色入ってるのに細くて\n持ち歩きしやすい。毎日使ってる。もう1本買うか迷ってる。"

    path = create_review_image(test_name, test_review, test_url,
                                output_path="/tmp/test_review_card.jpg")
    if path:
        print(f"テスト画像生成完了: {path}")
    else:
        print("テスト画像生成失敗")
