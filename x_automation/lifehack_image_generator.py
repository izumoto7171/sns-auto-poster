"""
一人暮らしライフハック X投稿用 4枚画像生成（Pillow）
サイズ: 1080×1350px (4:5)
デザイン: オフホワイト背景 × くすみゴールド × ミニマル
"""
import io
import os
import sys
from pathlib import Path

# ─────────────────────────────────────────
# デザイン定数
# ─────────────────────────────────────────
IMG_W = 1080
IMG_H = 1350
MARGIN = 80

# カラーパレット
BG_COLOR      = (247, 244, 239)   # #F7F4EF オフホワイト
ACCENT_COLOR  = (201, 169, 110)   # #C9A96E くすみゴールド
TEXT_COLOR    = (44, 44, 44)      # #2C2C2C ほぼ黒
SUB_COLOR     = (120, 110, 100)   # サブテキスト
DIVIDER_COLOR = (217, 211, 201)  # #D9D3C9 区切り線
WHITE         = (255, 255, 255)

# フォントパス（既存の image_card_generator と同じ探索順）
_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "fonts")
_FONT_PATHS = [
    os.path.join(_ASSETS_DIR, "NotoSansJP-Bold.ttf"),
    os.path.join(_ASSETS_DIR, "NotoSansJP-Regular.ttf"),
    os.path.join(_ASSETS_DIR, "NotoSansCJK-Regular.ttc"),
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/Library/Fonts/Arial Unicode MS.ttf",
]


def _get_font(size: int, bold: bool = False):
    from PIL import ImageFont
    paths = _FONT_PATHS if not bold else [
        os.path.join(_ASSETS_DIR, "NotoSansJP-Bold.ttf"),
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    ] + _FONT_PATHS
    for path in paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _wrap_text(text: str, font, max_width: int, draw) -> list:
    lines = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            lines.append("")
            continue
        current = ""
        for char in paragraph:
            test = current + char
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] > max_width and current:
                lines.append(current)
                current = char
            else:
                current = test
        if current:
            lines.append(current)
    return lines


def _draw_divider(draw, y: int, x_start: int = MARGIN, length: int = 200):
    draw.line([(x_start, y), (x_start + length, y)], fill=DIVIDER_COLOR, width=1)


def _draw_accent_bar(draw, y: int):
    # 太めの縦線（幅6px、高さ50px）
    draw.rectangle([(MARGIN, y), (MARGIN + 6, y + 50)], fill=ACCENT_COLOR)


def _new_canvas():
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (IMG_W, IMG_H), BG_COLOR)
    draw = ImageDraw.Draw(img)
    return img, draw


def _to_bytes(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ─────────────────────────────────────────
# 1枚目: 表紙（フック）
# ─────────────────────────────────────────
def generate_cover(category: str, title: str, sub_copy: str) -> bytes:
    img, draw = _new_canvas()

    # カテゴリタグ（上部中央にゴールドの枠付きで配置）
    font_tag = _get_font(24, bold=True)
    tag_text = category.upper() if category else "SOLO LIFE"
    tag_bbox = draw.textbbox((0, 0), tag_text, font=font_tag)
    tag_w = tag_bbox[2] - tag_bbox[0]
    tag_x = (IMG_W - tag_w) // 2
    tag_y = 220
    draw.rounded_rectangle(
        [(tag_x - 20, tag_y - 10), (tag_x + tag_w + 20, tag_y + 35)],
        radius=6, outline=ACCENT_COLOR, width=2,
    )
    draw.text((tag_x, tag_y), tag_text, fill=ACCENT_COLOR, font=font_tag)

    # メインタイトル（中央・大きく、自動折り返し対応）
    font_title = _get_font(56, bold=True)
    max_w = IMG_W - (MARGIN * 2)
    lines = _wrap_text(title, font_title, max_w, draw)

    start_y = 480
    line_h = 85
    for i, line in enumerate(lines):
        l_bbox = draw.textbbox((0, 0), line, font=font_title)
        l_w = l_bbox[2] - l_bbox[0]
        l_x = (IMG_W - l_w) // 2
        draw.text((l_x, start_y + (i * line_h)), line, fill=TEXT_COLOR, font=font_title)

    # 中央の装飾ミニライン
    divider_y = start_y + (len(lines) * line_h) + 40
    _draw_divider(draw, divider_y, x_start=(IMG_W - 120) // 2, length=120)

    # サブコピー（ターゲット明示・タイトルの下にセンター配置）
    font_sub = _get_font(28, bold=False)
    sub_lines = _wrap_text(sub_copy, font_sub, max_w, draw)
    sub_start_y = divider_y + 60
    for i, s_line in enumerate(sub_lines):
        s_bbox = draw.textbbox((0, 0), s_line, font=font_sub)
        s_w = s_bbox[2] - s_bbox[0]
        s_x = (IMG_W - s_w) // 2
        draw.text((s_x, sub_start_y + (i * 45)), s_line, fill=SUB_COLOR, font=font_sub)

    # 下部スワイプ誘導
    font_hint = _get_font(22, bold=False)
    hint_text = "▶ スワイプして確認"
    h_bbox = draw.textbbox((0, 0), hint_text, font=font_hint)
    draw.text(
        ((IMG_W - (h_bbox[2] - h_bbox[0])) // 2, IMG_H - 120),
        hint_text, fill=ACCENT_COLOR, font=font_hint,
    )

    return _to_bytes(img)


# ─────────────────────────────────────────
# 2・3枚目: アイテム紹介
# ─────────────────────────────────────────
def generate_item(number: str, item_name: str, points: list, price: str) -> bytes:
    img, draw = _new_canvas()

    # 通し番号（左上）
    font_num = _get_font(32, bold=True)
    draw.text((MARGIN, 120), f"No.{number}", fill=ACCENT_COLOR, font=font_num)
    _draw_divider(draw, 175, x_start=MARGIN, length=80)

    # 商品名（アクセントの縦棒付き）
    name_y = 240
    _draw_accent_bar(draw, name_y)
    font_name = _get_font(46, bold=True)
    draw.text((MARGIN + 26, name_y - 2), item_name, fill=TEXT_COLOR, font=font_name)

    # 特徴・ポイントリスト（チェックマーク付き）
    font_point = _get_font(28, bold=False)
    font_check = _get_font(28, bold=True)
    point_start_y = 380
    point_gap = 75

    for i, pt in enumerate(points[:3]):
        current_y = point_start_y + (i * point_gap)
        draw.text((MARGIN, current_y), "✓", fill=ACCENT_COLOR, font=font_check)
        draw.text((MARGIN + 45, current_y), pt, fill=TEXT_COLOR, font=font_point)

    # 価格情報（右下にスタイリッシュに配置）
    if price:
        font_price = _get_font(30, bold=True)
        price_text = f"参考価格：{price}"
        p_bbox = draw.textbbox((0, 0), price_text, font=font_price)
        p_w = p_bbox[2] - p_bbox[0]
        draw.text((IMG_W - MARGIN - p_w, IMG_H - 160), price_text, fill=SUB_COLOR, font=font_price)

    return _to_bytes(img)


# ─────────────────────────────────────────
# 4枚目: まとめ + CTA
# ─────────────────────────────────────────
def generate_summary(items: list) -> bytes:
    img, draw = _new_canvas()

    # 見出し
    font_title = _get_font(48, bold=True)
    t_bbox = draw.textbbox((0, 0), "まとめ", font=font_title)
    t_x = (IMG_W - (t_bbox[2] - t_bbox[0])) // 2
    draw.text((t_x, 180), "まとめ", fill=TEXT_COLOR, font=font_title)
    _draw_divider(draw, 260, x_start=(IMG_W - 160) // 2, length=160)

    # 振り返りアイテムリスト（センター寄せ）
    font_item = _get_font(32, bold=False)
    item_start_y = 340
    item_gap = 75
    markers = ["①", "②", "③"]

    for i, item_name in enumerate(items[:3]):
        display_text = f"{markers[i]} {item_name}"
        i_bbox = draw.textbbox((0, 0), display_text, font=font_item)
        i_x = (IMG_W - (i_bbox[2] - i_bbox[0])) // 2
        draw.text((i_x, item_start_y + (i * item_gap)), display_text, fill=TEXT_COLOR, font=font_item)

    # 区切り線
    _draw_divider(draw, 640, x_start=MARGIN, length=IMG_W - (MARGIN * 2))

    # CTA（プロフィール誘導）
    font_cta1 = _get_font(40, bold=True)
    cta1_text = "🔗 購入リンクはプロフへ"
    c1_bbox = draw.textbbox((0, 0), cta1_text, font=font_cta1)
    c1_x = (IMG_W - (c1_bbox[2] - c1_bbox[0])) // 2
    draw.text((c1_x, 740), cta1_text, fill=ACCENT_COLOR, font=font_cta1)

    font_cta2 = _get_font(28, bold=False)
    cta2_text = "フォロー＆保存で後から見返せます"
    c2_bbox = draw.textbbox((0, 0), cta2_text, font=font_cta2)
    c2_x = (IMG_W - (c2_bbox[2] - c2_bbox[0])) // 2
    draw.text((c2_x, 820), cta2_text, fill=SUB_COLOR, font=font_cta2)

    return _to_bytes(img)


# ─────────────────────────────────────────
# まとめて4枚生成
# ─────────────────────────────────────────
def generate_all(data: dict) -> list:
    """
    期待する引数 data の構造:
    {
        "cover":   {"category": "...", "title": "...", "sub_copy": "..."},
        "item1":   {"item_name": "...", "points": ["...", "..."], "price": "..."},
        "item2":   {"item_name": "...", "points": ["...", "..."], "price": "..."},
        "summary": {"items": ["...", "..."]}
    }
    旧形式（フラット構造）との後方互換も保持。
    """
    try:
        from PIL import Image  # noqa
    except ImportError:
        print("⚠️ Pillow未インストール: pip install Pillow")
        return []

    # 旧形式（category/title/item1/item2 がトップレベル）を新形式に変換
    if "cover" not in data and "title" in data:
        data = {
            "cover": {
                "category": data.get("category", ""),
                "title":    data.get("title", ""),
                "sub_copy": data.get("sub_copy", ""),
            },
            "item1": {
                "item_name": data["item1"].get("name", ""),
                "points":    data["item1"].get("points", []),
                "price":     data["item1"].get("price", ""),
            },
            "item2": {
                "item_name": data["item2"].get("name", ""),
                "points":    data["item2"].get("points", []),
                "price":     data["item2"].get("price", ""),
            },
            "summary": {
                "items": data.get("summary_items", [
                    data["item1"].get("name", ""),
                    data["item2"].get("name", ""),
                ]),
            },
        }

    images = []
    try:
        c = data.get("cover", {})
        images.append(generate_cover(c.get("category", ""), c.get("title", ""), c.get("sub_copy", "")))

        i1 = data.get("item1", {})
        images.append(generate_item("1", i1.get("item_name", ""), i1.get("points", []), i1.get("price", "")))

        i2 = data.get("item2", {})
        images.append(generate_item("2", i2.get("item_name", ""), i2.get("points", []), i2.get("price", "")))

        s = data.get("summary", {})
        images.append(generate_summary(s.get("items", [])))

    except Exception as e:
        print(f"⚠️ 画像生成エラー: {e}")
        import traceback
        traceback.print_exc()

    return images


# ─────────────────────────────────────────
# 単体テスト用
# ─────────────────────────────────────────
if __name__ == "__main__":
    import tempfile

    sample = {
        "cover": {
            "category": "インテリア・収納",
            "title": "引っ越し初日に\n買えばよかった3選",
            "sub_copy": "一人暮らし歴5年が本音レポ",
        },
        "item1": {
            "item_name": "tower マグネット収納ラック",
            "points": [
                "冷蔵庫横のデッドスペースを活用",
                "取り付け1分・穴あけ不要",
                "耐荷重3kg・安定感あり",
            ],
            "price": "¥2,980",
        },
        "item2": {
            "item_name": "山崎実業 詰め替えボトル",
            "points": [
                "生活感ゼロのシンプルデザイン",
                "詰め替え口が大きく補充ラク",
                "3種セットで洗面台が統一",
            ],
            "price": "¥1,200",
        },
        "summary": {
            "items": ["tower マグネット収納ラック", "山崎実業 詰め替えボトル"],
        },
    }

    images = generate_all(sample)
    if images:
        out_dir = Path(tempfile.mkdtemp())
        for i, img_bytes in enumerate(images, 1):
            path = out_dir / f"card_{i}.png"
            path.write_bytes(img_bytes)
            print(f"保存: {path}")
        print(f"\n計{len(images)}枚生成完了 → {out_dir}")
    else:
        print("生成失敗")
