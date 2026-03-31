"""
設定ファイル - .envから読み込む
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

# API Keys
CLAUDE_API_KEY       = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY       = os.getenv("GEMINI_API_KEY", "")
LEONARDO_API_KEY     = os.getenv("LEONARDO_API_KEY", "")
YOUTUBE_TOKEN_PATH   = Path(__file__).parent.parent / "youtube_automation" / "token.pickle"
YOUTUBE_SECRETS_PATH = Path(__file__).parent.parent / "youtube_automation" / "client_secrets.json"

# Video settings
VIDEO_WIDTH    = 1080
VIDEO_HEIGHT   = 1920
FPS            = 30
DURATION_SEC   = 30

# Font
FONT_PATH       = Path(__file__).parent / "fonts" / "NotoSansJP-Bold.ttf"
FONT_SIZE_LARGE = 90
FONT_SIZE_SMALL = 50

# Caption style
CAPTION_COLOR   = (255, 215, 0)   # 黄色
CAPTION_OUTLINE = (0, 0, 0)       # 黒縁取り
OUTLINE_WIDTH   = 8

# VOICEVOX
VOICEVOX_URL   = "http://localhost:50021"
VOICEVOX_SPEAKER = 1

# Output
OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
