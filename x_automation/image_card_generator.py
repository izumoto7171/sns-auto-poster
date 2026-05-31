"""
X投稿用 テキストカード画像生成（Pillow）
フック文章を視覚化したカードを生成。
画像付き投稿はテキストのみより2〜3倍インプレッションが増える。

サイズ: 1200x675 (16:9, Xに最適)
色テーマ: post_typeごとに変わる
"""
import os
import io
import random
from pathlib import Path
from datetime import datetime


# ─────────────────────────────────────────
# カード設定
# ─────────────────────────────────────────
CARD_W = 1200
CARD_H = 675

# post_typeごとの色テーマ
COLOR_THEMES = {
    "useful": {
        "bg_top":    (22, 36, 71),
        "bg_bottom": (14, 24, 50),
        "accent":    (79, 172, 254),
        "text":      (255, 255, 255),
        "sub_text":  (160, 190, 230),
    },
    "empathy": {
        "bg_top":    (45, 22, 60),
        "bg_bottom": (30, 14, 42),
        "accent":    (200, 120, 255),
        "text":      (255, 255, 255),
        "sub_text":  (200, 170, 230),
    },
    "trivia": {
        "bg_top":    (20, 52, 40),
        "bg_bottom": (12, 36, 26),
        "accent":    (80, 230, 150),
        "text":      (255, 255, 255),
        "sub_text":  (160, 220, 190),
    },
    "product": {
        "bg_top":    (55, 30, 10),
        "bg_bottom": (38, 18, 5),
        "accent":    (255, 170, 60),
        "text":      (255, 255, 255),
        "sub_text":  (230, 195, 150),
    },
    "verification": {
        "bg_top":    (22, 36, 71),
        "bg_bottom": (14, 24, 50),
        "accent":    (79, 172, 254),
        "text":      (255, 255, 255),
        "sub_text":  (160, 190, 230),
    },
    "lifehack": {
        "bg_top":    (20, 52, 40),
        "bg_bottom": (12, 36, 26),
        "accent":    (80, 230, 150),
        "text":      (255, 255, 255),
        "sub_text":  (160, 220, 190),
    },
}

DEFAULT_THEME = COLOR_THEMES["useful"]

# タグライン（左下に表示）
TAGLINES = {
    "useful":       "AI副業・ライフハック",
    "empathy":      "副業体験談",
    "trivia":       "AI・テクノロジー雑学",
    "product":      "おすすめAIツール",
    "verification": "副業AI検証ログ",
    "lifehack":     "AIで時間を生む",
}


def _is_pillow_available() -> bool:
    try:
        from PIL import Image
        return True
    except ImportError:
        return False


_ASSETS_FONTS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "fonts")

_FONT_PATHS = [
    # ① リポジトリ内（環境非依存・最優先）
    os.path.join(_ASSETS_FONTS_DIR, "NotoSansJP-Regular.ttf"),
    os.path.join(_ASSETS_FONTS_DIR, "NotoSansJP-Bold.ttf"),
    os.path.join(_ASSETS_FONTS_DIR, "NotoSansCJK-Regular.ttc"),
    # ② Ubuntu / GitHub Actions（fonts-noto-cjk）
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    # ③ macOS
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/Library/Fonts/Arial Unicode MS.ttf",
    # ④ 汎用フォールバック
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _fc_list_fonts() -> list:
    """fc-list で日本語フォントパスを動的に取得。失敗時は空リスト。"""
    try:
        import subprocess
        result = subprocess.run(
            ["fc-list", ":lang=ja", "--format=%{file}\n"],
            capture_output=True, text=True, timeout=3,
        )
        if result.returncode == 0:
            return [l.strip() for l in result.stdout.splitlines() if l.strip()]
    except Exception:
        pass
    return []


def _get_font(size: int):
    """日本語対応フォントを取得（なければデフォルト）"""
    from PIL import ImageFont
    for path in _FONT_PATHS + _fc_list_fonts():
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _draw_gradient(draw, w: int, h: int, color_top: tuple, color_bottom: tuple):
    """縦グラデーション背景"""
    for y in range(h):
        t = y / h
        r = int(color_top[0] * (1 - t) + color_bottom[0] * t)
        g = int(color_top[1] * (1 - t) + color_bottom[1] * t)
        b = int(color_top[2] * (1 - t) + color_bottom[2] * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))


def _wrap_text(text: str, font, max_width: int, draw) -> list:
    """テキストを指定幅で折り返す（日本語対応）"""
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


def generate_card(hook_text: str, post_type: str = "useful", username: str = "") -> bytes:
    """
    フック文章からテキストカード画像を生成してバイト列で返す

    Args:
        hook_text: 投稿の最初の1〜2行（フック部分）
        post_type: "useful" / "empathy" / "trivia" / "product" / "verification" / "lifehack"
        username:  Xのユーザー名 (@なし)

    Returns:
        PNG画像のバイト列。Pillowが使えない場合は空のbytes。
    """
    if not _is_pillow_available():
        print("⚠️ Pillow未インストール: pip install Pillow")
        return b""

    try:
        from PIL import Image, ImageDraw

        theme = COLOR_THEMES.get(post_type, DEFAULT_THEME)
        img   = Image.new("RGB", (CARD_W, CARD_H))
        draw  = ImageDraw.Draw(img)

        # グラデーション背景
        _draw_gradient(draw, CARD_W, CARD_H, theme["bg_top"], theme["bg_bottom"])

        # 左端のアクセントバー
        accent = theme["accent"]
        draw.rectangle([(56, 70), (64, CARD_H - 70)], fill=accent)

        # フォント
        font_hook = _get_font(54)
        font_sub  = _get_font(28)

        margin = 96
        max_text_w = CARD_W - margin * 2

        # フックテキストを最大3行に
        hook_lines_raw = hook_text.split("\n")[:3]
        hook_text_trimmed = "\n".join(l for l in hook_lines_raw if l.strip())

        wrapped = _wrap_text(hook_text_trimmed, font_hook, max_text_w, draw)
        # 最大4行
        if len(wrapped) > 4:
            wrapped = wrapped[:4]

        line_h = 72
        total_text_h = len(wrapped) * line_h
        y_start = (CARD_H - total_text_h) // 2 - 30

        for i, line in enumerate(wrapped):
            if line:
                draw.text((margin, y_start + i * line_h), line,
                          font=font_hook, fill=theme["text"])

        # アクセントアンダーライン
        y_line = y_start + total_text_h + 18
        draw.line([(margin, y_line), (margin + 180, y_line)],
                  fill=accent, width=3)

        # ユーザー名（右下）
        if username:
            draw.text((CARD_W - 340, CARD_H - 55),
                      f"@{username}", font=font_sub, fill=theme["sub_text"])

        # タグライン（左下）
        tagline = TAGLINES.get(post_type, "AI副業情報")
        draw.text((margin, CARD_H - 55), tagline,
                  font=font_sub, fill=theme["sub_text"])

        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()

    except Exception as e:
        print(f"⚠️ 画像カード生成エラー: {e}")
        return b""


def extract_hook(text: str) -> str:
    """投稿全文からフック（最初の1〜2行）を抽出"""
    lines = [l for l in text.split("\n") if l.strip()]
    return "\n".join(lines[:2]) if lines else text[:50]


def generate_and_save(
    hook_text: str,
    post_type: str = "useful",
    username: str = "",
    output_path: str = None,
) -> str:
    """
    カードを生成してファイルに保存し、パスを返す。
    失敗した場合は空文字列を返す。
    """
    data = generate_card(hook_text, post_type, username)
    if not data:
        return ""

    if output_path is None:
        ts = int(datetime.now().timestamp())
        output_path = str(Path(__file__).parent / f"card_{post_type}_{ts}.png")

    with open(output_path, "wb") as f:
        f.write(data)
    print(f"画像カード保存: {output_path}")
    return output_path


if __name__ == "__main__":
    # テスト生成
    test_cases = [
        ("AI副業で月3万円なら、今すぐ始められます。\n「副業って難しそう」と思ってる人へ。", "useful", "ai_fuka"),
        ("副業始めた最初の1ヶ月、1円も稼げなかった。\n正直めちゃくちゃ焦った。", "empathy", "ai_fuka"),
        ("Gemini APIで記事自動生成を1週間試した結果。\n1記事40分 → 8分に短縮。", "verification", "ai_fuka"),
    ]
    for hook, ptype, uname in test_cases:
        path = generate_and_save(hook, ptype, uname)
        if path:
            print(f"生成完了: {path}")
        else:
            print(f"生成失敗（Pillow未インストールの可能性）")
