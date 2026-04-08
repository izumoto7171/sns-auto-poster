"""
Amazonアフィリエイト投稿用 アイキャッチ画像プロンプト生成

商品情報から DALL-E 3 / Midjourney / Stable Diffusion 対応の
プロンプトを自動生成する。クリック率（CTR）向上が目的。

【なぜ画像が効くか】
- Xの画像付き投稿はテキストのみより2〜3倍のクリック率
- 商品画像よりも「使用シーン」の方が購買意欲を引き出しやすい
- ガジェット系は「デスクセットアップ」「通勤シーン」が最も反応が高い

使い方:
  python3.11 x_automation/image_prompt_generator.py               # amazon_deals.jsonから生成
  python3.11 x_automation/image_prompt_generator.py --title "商品名" --features "特徴1,特徴2"
  python3.11 x_automation/image_prompt_generator.py --save        # image_prompts.jsonに保存
"""

import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
ROOT_DIR = BASE_DIR.parent

# .env 読み込み
env_path = ROOT_DIR / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


# ─────────────────────────────────────────
# カテゴリ別シーン定義（CTRが高いシーン）
# ─────────────────────────────────────────
SCENE_TEMPLATES = {
    "ガジェット": [
        "minimalist Japanese desk setup with soft morning light, wooden desk, laptop",
        "commuter on a train in Tokyo, using gadget, cinematic photo",
        "flat lay on white marble, gadget with coffee cup and notebook",
    ],
    "オーディオ": [
        "person wearing earphones on a train platform, Tokyo cityscape background, golden hour",
        "work from home setup, earphones on desk beside macbook, cozy room",
        "flat lay: wireless earphones on wooden surface with plant and coffee",
    ],
    "充電・バッテリー": [
        "compact charger and cable on a coffee shop table, minimal style",
        "travel flat lay: charger, passport, phone on white background",
        "close-up of charger connected to laptop on minimalist white desk",
    ],
    "PC周辺機器": [
        "clean desk setup: mechanical keyboard, mouse, monitor with soft lighting",
        "developer workspace at night, monitor glow, keyboard close-up",
        "flat lay tech accessories: keyboard, mouse, headphones, notebook",
    ],
    "スマートホーム": [
        "modern Japanese living room with smart speaker, soft evening light",
        "cozy bedroom with smart bulb warm glow, reading corner",
        "flat lay: smart home devices on white background, product photography style",
    ],
    "default": [
        "product photography on white background, professional studio lighting",
        "lifestyle photo in modern Japanese apartment, natural light",
        "flat lay with complementary accessories on wooden desk",
    ],
}

# プロンプトの共通スタイル指定
STYLE_SUFFIXES = {
    "dalle":      "photorealistic, high quality, 4K, professional product photography",
    "midjourney": "--style raw --ar 16:9 --q 2 --v 6",
    "sd":         "photorealistic, studio lighting, sharp focus, 8k uhd, dslr photo",
}

# ─────────────────────────────────────────
# Xリンク抑制対策: ツリー誘導テキスト overlay
# ─────────────────────────────────────────
# 親ツイートにリンクを載せないため、画像内にテキストを入れて
# 「詳細はツリーを見て」と誘導する。
# → リンクなし親ツイートのリーチを最大化しつつ、クリックへ誘導できる。

OVERLAY_STYLES = {
    "thread_cta": {
        # 画像右下に小さなテキストバナー
        "prompt_addition": (
            'with a subtle dark semi-transparent banner at the bottom-right corner '
            'containing white Japanese text "詳細はツリーをチェック ↓" '
            'in clean modern sans-serif font, minimal design'
        ),
        "label": "ツリー誘導（右下バナー）",
    },
    "arrow_cta": {
        # 画像下部に矢印付きCTA
        "prompt_addition": (
            'with a small white text overlay at the bottom center: '
            '"▼ 続きはリプライ欄へ" in Japanese, clean typography on dark translucent background'
        ),
        "label": "続きへの矢印CTA（下部中央）",
    },
    "badge_cta": {
        # 左上に価格バッジ + ツリー誘導
        "prompt_addition": (
            'with a red circular badge in the top-left corner showing '
            '"詳細▼" in white bold Japanese text, eye-catching design'
        ),
        "label": "詳細バッジ（左上）",
    },
    "none": {
        "prompt_addition": "",
        "label": "オーバーレイなし",
    },
}

DEFAULT_OVERLAY = "thread_cta"


# ─────────────────────────────────────────
# プロンプト生成（Gemini使用 or テンプレート）
# ─────────────────────────────────────────
def generate_image_prompt(
    product: dict,
    tool: str = "dalle",
    overlay: str = DEFAULT_OVERLAY,
) -> dict:
    """
    商品情報から画像生成プロンプトを生成する

    Args:
        product: 商品情報dict
        tool:    "dalle" / "midjourney" / "sd"
        overlay: ツリー誘導テキストのスタイル
                 "thread_cta" / "arrow_cta" / "badge_cta" / "none"
                 デフォルト: "thread_cta"（右下バナー）

    Returns:
        {
          "product_title":  str,
          "scene_prompt":   str,   # 使用シーン（英語）
          "full_prompt":    str,   # ツール向け完成プロンプト（overlay込み）
          "jp_description": str,   # 投稿文に使える日本語説明
          "overlay_style":  str,   # 使用したoverlayスタイル
          "overlay_label":  str,   # overlayの日本語説明
          "tool":           str,
        }
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        result = _generate_with_gemini(product, tool, api_key)
        if result:
            result = _apply_overlay(result, overlay, tool)
            return result

    result = _generate_from_template(product, tool)
    result = _apply_overlay(result, overlay, tool)
    return result


def _apply_overlay(result: dict, overlay: str, tool: str) -> dict:
    """
    生成済みプロンプトにツリー誘導テキスト overlay を付加する

    Midjourney の場合はスタイルフラグの前に挿入する。
    """
    style = OVERLAY_STYLES.get(overlay, OVERLAY_STYLES[DEFAULT_OVERLAY])
    addition = style["prompt_addition"]

    if not addition:
        result["overlay_style"] = "none"
        result["overlay_label"] = OVERLAY_STYLES["none"]["label"]
        return result

    full = result.get("full_prompt", "")

    if tool == "midjourney":
        # MJはフラグ（--ar等）の直前に挿入
        flag_idx = full.find(" --")
        if flag_idx != -1:
            full = full[:flag_idx] + f", {addition}" + full[flag_idx:]
        else:
            full = full + f", {addition}"
    else:
        # DALL-E / SD は末尾のスタイル指定の前に挿入
        for suffix in STYLE_SUFFIXES.values():
            if suffix in full:
                full = full.replace(suffix, f"{addition}, {suffix}")
                break
        else:
            full = full + f", {addition}"

    result["full_prompt"]    = full
    result["overlay_style"]  = overlay
    result["overlay_label"]  = style["label"]
    return result


def _generate_with_gemini(product: dict, tool: str, api_key: str) -> dict:
    """Gemini APIでプロンプトを生成"""
    try:
        from google import genai

        title    = product.get("title", "")
        brand    = product.get("brand", "")
        features = product.get("features", [])
        category = product.get("category", "ガジェット")
        why      = product.get("why_viral", "")

        feature_text = ", ".join(features[:3])

        prompt = f"""
あなたはAI画像生成の専門家です。以下の商品のアイキャッチ画像プロンプトを作成してください。

【商品情報】
- 商品名: {title}
- ブランド: {brand}
- カテゴリ: {category}
- 特徴: {feature_text}
- バズりポイント: {why}

【要件】
- 商品を「使っているシーン」や「ライフスタイル」を描写する（商品単体のみは避ける）
- ガジェット好き（20〜40代）が「これ欲しい」と思うビジュアル
- 日本の生活シーンが自然に入るとベター
- ツール: {tool.upper()}

以下の形式でJSONのみ出力（説明文不要）:
{{
  "scene_prompt": "英語の使用シーン描写（50語以内）",
  "full_prompt": "{tool.upper()}向けの完成プロンプト（英語・style指定含む）",
  "jp_description": "この画像の日本語説明（投稿に添えるキャプション・30文字以内）"
}}
"""

        client = genai.Client(api_key=api_key)
        resp   = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=prompt,
        )
        raw = resp.text.strip()
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        data = json.loads(raw)
        return {
            "product_title":   title,
            "scene_prompt":    data.get("scene_prompt", ""),
            "full_prompt":     data.get("full_prompt", ""),
            "jp_description":  data.get("jp_description", ""),
            "tool":            tool,
            "generated_at":    datetime.now().isoformat(),
        }

    except Exception as e:
        print(f"⚠️  Geminiプロンプト生成エラー: {e}")
        return {}


def _generate_from_template(product: dict, tool: str) -> dict:
    """テンプレートベースでプロンプト生成"""
    import random

    title    = product.get("title", "gadget")
    category = product.get("category", "default")
    brand    = product.get("brand", "")
    features = product.get("features", [])

    scenes = SCENE_TEMPLATES.get(category, SCENE_TEMPLATES["default"])
    scene  = random.choice(scenes)

    feature_hint = features[0] if features else "compact design"

    if tool == "midjourney":
        full_prompt = (
            f"{scene}, {brand} {title[:30]}, {feature_hint}, "
            f"photorealistic {STYLE_SUFFIXES['midjourney']}"
        )
    elif tool == "sd":
        full_prompt = (
            f"{scene}, featuring {brand} product, {feature_hint}, "
            f"{STYLE_SUFFIXES['sd']}"
        )
    else:  # dalle
        full_prompt = (
            f"{scene}. The scene includes a {brand} {title[:30]} prominently. "
            f"{feature_hint}. {STYLE_SUFFIXES['dalle']}"
        )

    jp_desc = f"{title[:20]}のある暮らし"

    return {
        "product_title":   title,
        "scene_prompt":    scene,
        "full_prompt":     full_prompt,
        "jp_description":  jp_desc,
        "tool":            tool,
        "generated_at":    datetime.now().isoformat(),
    }


# ─────────────────────────────────────────
# ビフォー／アフター対比プロンプト生成
# ─────────────────────────────────────────
def generate_before_after_prompt(
    product: dict,
    tool: str = "dalle",
    overlay: str = DEFAULT_OVERLAY,
) -> dict:
    """
    「ビフォー（問題）→アフター（解決）」の対比画像プロンプトを生成する。
    Tweet1の共感フックと視覚的に呼応させることで、クリック率を高める。

    Returns:
        generate_image_prompt と同じ構造の dict に before_prompt / after_prompt を追加
    """
    title    = product.get("title", "gadget")
    brand    = product.get("brand", "")
    features = product.get("features", [])
    hook     = product.get("story_hook", "")

    # ビフォー: 問題状態（hook から自動抽出、なければ汎用表現）
    before_scene = (
        "messy desk with tangled cables everywhere, multiple charging cables "
        "in a chaotic pile, stressful and cluttered workspace, dim lighting"
    )

    # アフター: 解決状態（ブランド商品が主役）
    feature_hint = features[0] if features else "magnetic cable holder"
    after_scene = (
        f"clean minimalist desk setup, {brand} magnetic cable holder organizing "
        f"cables neatly on white desk surface, satisfying tidy workspace, "
        f"soft natural light, {feature_hint}"
    )

    if tool == "midjourney":
        full_prompt = (
            f"Split image, left panel labeled 'BEFORE': {before_scene}, "
            f"right panel labeled 'AFTER': {after_scene}, "
            f"photorealistic {STYLE_SUFFIXES['midjourney']} --ar 16:9"
        )
    elif tool == "sd":
        full_prompt = (
            f"diptych comparison photo, left side: {before_scene}, "
            f"right side: {after_scene}, {STYLE_SUFFIXES['sd']}"
        )
    else:  # dalle (デフォルト)
        full_prompt = (
            f"A split-image comparison photo. LEFT side (labeled 'Before'): "
            f"{before_scene}. RIGHT side (labeled 'After'): {after_scene}. "
            f"High quality product lifestyle photography. {STYLE_SUFFIXES['dalle']}"
        )

    jp_desc = f"配線ビフォーアフター（{brand}使用前後）"

    result = {
        "product_title":  title,
        "scene_prompt":   f"Before: {before_scene[:60]}... / After: {after_scene[:60]}...",
        "full_prompt":    full_prompt,
        "jp_description": jp_desc,
        "before_prompt":  before_scene,
        "after_prompt":   after_scene,
        "tool":           tool,
        "generated_at":   datetime.now().isoformat(),
    }

    result = _apply_overlay(result, overlay, tool)
    return result


# ─────────────────────────────────────────
# 複数商品のプロンプトを一括生成
# ─────────────────────────────────────────
def generate_all_prompts(
    products: list,
    tool: str = "dalle",
    overlay: str = DEFAULT_OVERLAY,
) -> list:
    """商品リストからプロンプトを全件生成"""
    results = []
    for i, product in enumerate(products):
        print(f"  [{i+1}/{len(products)}] {product['title'][:40]}...")
        result = generate_image_prompt(product, tool, overlay)
        if result:
            results.append({**result, "product": product})
    return results


# ─────────────────────────────────────────
# 表示・保存
# ─────────────────────────────────────────
def print_prompts(prompts: list):
    """プロンプト一覧を整形表示"""
    print(f"\n{'=' * 65}")
    print(f"🎨 画像生成プロンプト ({len(prompts)}件)")
    print(f"{'=' * 65}")

    for i, p in enumerate(prompts, 1):
        print(f"\n【{i}】{p['product_title'][:45]}")
        print(f"  ツール    : {p['tool'].upper()}")
        print(f"  シーン    : {p['scene_prompt'][:70]}")
        print(f"  JP説明    : {p['jp_description']}")
        overlay_label = p.get("overlay_label", "なし")
        print(f"  CTA overlay: {overlay_label}  ← Xリンク抑制対策")
        print(f"  ─── プロンプト（コピー用）─────────────────────────────")
        # 長いプロンプトは折り返して表示
        fp = p['full_prompt']
        for chunk in [fp[j:j+80] for j in range(0, len(fp), 80)]:
            print(f"  {chunk}")


def save_prompts(prompts: list, output_path: Path = None):
    """プロンプトをJSONに保存"""
    if output_path is None:
        output_path = BASE_DIR / "image_prompts.json"

    output_path.write_text(
        json.dumps(prompts, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"\n💾 保存: {output_path}")


# ─────────────────────────────────────────
# CLI
# ─────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Amazonアフィリエイト用画像プロンプト生成")
    parser.add_argument("--title",    help="商品名（単品指定）")
    parser.add_argument("--features", help="特徴（カンマ区切り）")
    parser.add_argument("--category", default="ガジェット", help="カテゴリ")
    parser.add_argument("--tool",     default="dalle",
                        choices=["dalle", "midjourney", "sd"],
                        help="画像生成ツール（デフォルト: dalle）")
    parser.add_argument("--save",     action="store_true", help="image_prompts.jsonに保存")
    parser.add_argument("--overlay",  default=DEFAULT_OVERLAY,
                        choices=list(OVERLAY_STYLES.keys()),
                        help=f"ツリー誘導CTAのスタイル（デフォルト: {DEFAULT_OVERLAY}）\n"
                             + "\n".join(f"  {k}: {v['label']}"
                                         for k, v in OVERLAY_STYLES.items()))
    args = parser.parse_args()

    if args.title:
        # 単品モード
        product = {
            "title":    args.title,
            "brand":    "",
            "category": args.category,
            "features": [f.strip() for f in args.features.split(",")] if args.features else [],
            "why_viral": "",
        }
        result = generate_image_prompt(product, args.tool, args.overlay)
        if result:
            print_prompts([result])
            if args.save:
                save_prompts([result])
    else:
        # amazon_deals.json から一括生成
        deals_path = BASE_DIR / "amazon_deals.json"
        if not deals_path.exists():
            print("❌ amazon_deals.json がありません。先に fetch_amazon_deals.py を実行してください")
            sys.exit(1)

        products = json.loads(deals_path.read_text(encoding="utf-8"))
        overlay_label = OVERLAY_STYLES.get(args.overlay, {}).get("label", args.overlay)
        print(f"\n🎨 {len(products)}件の画像プロンプトを生成中")
        print(f"   ツール: {args.tool.upper()} / CTA overlay: {overlay_label}")

        prompts = generate_all_prompts(products, args.tool, args.overlay)
        print_prompts(prompts)

        if args.save:
            save_prompts(prompts)


if __name__ == "__main__":
    main()
