"""
AI画像生成 - Leonardo.ai API優先、グラデーション画像フォールバック
"""
import requests
import time
from pathlib import Path
from PIL import Image, ImageDraw
from config import LEONARDO_API_KEY, VIDEO_WIDTH, VIDEO_HEIGHT


def _gradient_placeholder(output_path: str) -> str:
    """APIなし時のグラデーション背景画像"""
    img = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT))
    draw = ImageDraw.Draw(img)
    for y in range(VIDEO_HEIGHT):
        t = y / VIDEO_HEIGHT
        r = int(15 + t * 40)
        g = int(0  + t * 15)
        b = int(60 + t * 100)
        draw.line([(0, y), (VIDEO_WIDTH, y)], fill=(r, g, b))
    img.save(output_path)
    return output_path


def generate_image(prompt: str, output_path: str) -> str:
    """
    Leonardo.ai APIで画像生成。APIキーがなければグラデーション画像を返す。
    """
    if not LEONARDO_API_KEY:
        print("⚠️  LEONARDO_API_KEY未設定、プレースホルダー画像を使用")
        return _gradient_placeholder(output_path)

    try:
        headers = {
            "Authorization": f"Bearer {LEONARDO_API_KEY}",
            "Content-Type": "application/json",
        }

        # 画像生成リクエスト
        res = requests.post(
            "https://cloud.leonardo.ai/api/rest/v1/generations",
            headers=headers,
            json={
                "prompt": prompt,
                "width": 576,    # 9:16の横幅（Leonardo推奨）
                "height": 1024,
                "num_images": 1,
                "modelId": "6bef9f1b-29cb-40c7-b9df-32b51c1f67d3",  # Leonardo Diffusion XL
                "ultra": False,
                "public": False,
            },
            timeout=30,
        )
        res.raise_for_status()
        generation_id = res.json()["sdGenerationJob"]["generationId"]

        # 生成完了を待つ（最大60秒）
        print(f"  🎨 Leonardo.ai生成中 (ID: {generation_id[:8]}...)")
        for _ in range(20):
            time.sleep(3)
            status_res = requests.get(
                f"https://cloud.leonardo.ai/api/rest/v1/generations/{generation_id}",
                headers=headers,
                timeout=10,
            )
            data = status_res.json().get("generations_by_pk", {})
            if data.get("status") == "COMPLETE":
                image_url = data["generated_images"][0]["url"]
                img_data = requests.get(image_url, timeout=15).content
                # 1080x1920にリサイズ
                img = Image.open(__import__("io").BytesIO(img_data))
                img = img.resize((VIDEO_WIDTH, VIDEO_HEIGHT), Image.LANCZOS)
                img.save(output_path)
                print(f"  ✅ 画像生成完了: {Path(output_path).name}")
                return output_path

        print("⚠️  Leonardo.aiタイムアウト、プレースホルダーを使用")
        return _gradient_placeholder(output_path)

    except Exception as e:
        print(f"⚠️  Leonardo.ai失敗: {e}、プレースホルダーを使用")
        return _gradient_placeholder(output_path)
