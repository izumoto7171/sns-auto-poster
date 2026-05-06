"""
Gemini API 共通クライアント

全モジュールはこのファイル経由で Gemini を呼ぶ。直接 genai.Client を使わない。

機能:
  - 指数バックオフ付きリトライ（429 / 503 / 500）
  - JSON ファイルキャッシュ（TTL: 24 時間）
    ・同一プロンプトの重複呼び出しを防ぎ API 消費を節約
  - コード例:
      from money_agent.gemini_client import generate
      text = generate(prompt)          # キャッシュあり
      text = generate(prompt, use_cache=False)  # キャッシュなし（SNS投稿など毎回違う内容）
"""

import hashlib
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.decorators import api_retry

# ── 定数 ────────────────────────────────────────────────
DEFAULT_MODEL  = "gemini-2.0-flash"
BLOG_MODEL     = "gemini-1.5-flash"       # ブログ記事など重い生成用（クォータバケツを分散）
X_POST_MODEL   = "gemini-2.0-flash-lite"  # X投稿生成用（軽量・高速）
CACHE_FILE     = Path(__file__).parent / "gemini_cache.json"
CACHE_TTL_H    = 24   # キャッシュ有効期間（時間）
MAX_CACHE_SIZE = 500  # エントリ上限（古い順に削除）


# ── キャッシュ操作 ────────────────────────────────────────
def _cache_key(model: str, prompt: str) -> str:
    return hashlib.md5(f"{model}:{prompt[:500]}".encode()).hexdigest()


def _load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cache(cache: dict):
    # サイズ上限を超えたら古いエントリを削除
    if len(cache) > MAX_CACHE_SIZE:
        sorted_keys = sorted(
            cache.keys(),
            key=lambda k: cache[k].get("cached_at", ""),
        )
        for k in sorted_keys[: len(cache) - MAX_CACHE_SIZE]:
            del cache[k]
    try:
        CACHE_FILE.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def _is_fresh(entry: dict) -> bool:
    try:
        ts = datetime.fromisoformat(entry["cached_at"])
        return datetime.now() - ts < timedelta(hours=CACHE_TTL_H)
    except Exception:
        return False


# ── メイン関数 ───────────────────────────────────────────
def generate(
    prompt: str,
    model: str = DEFAULT_MODEL,
    cache_key: str = None,
    use_cache: bool = True,
    max_retries: int = 4,   # 後方互換のために残す（utils/decorators.py の設定が優先）
    initial_wait: int = 35, # 後方互換のために残す（utils/decorators.py の設定が優先）
    temperature: float = 0.7,
) -> "str | None":
    """
    Gemini API を呼び出してテキストを返す。

    Parameters
    ----------
    prompt       : 送信するプロンプト文字列
    model        : 使用モデル（デフォルト: gemini-2.0-flash）
    cache_key    : キャッシュキーを手動指定する場合（省略時はプロンプトの MD5）
    use_cache    : True = キャッシュを使用。SNS 投稿など毎回違う内容には False を渡す
    max_retries  : 後方互換のために残す（リトライ設定は utils/decorators.py が管理）
    initial_wait : 後方互換のために残す（リトライ設定は utils/decorators.py が管理）
    temperature  : 生成の多様性 (0.0〜1.0)。停滞検知時は 0.9〜1.0 を渡す

    Returns
    -------
    str または None（全リトライ失敗時）
    """
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("  [Gemini] GEMINI_API_KEY 未設定")
        return None

    key = cache_key or _cache_key(model, prompt)

    # キャッシュ確認
    cache = {}
    if use_cache:
        cache = _load_cache()
        entry = cache.get(key)
        if entry and _is_fresh(entry):
            print(f"  [Gemini] キャッシュヒット ({key[:8]}...)")
            return entry["text"]

    # API 呼び出し（tenacity ベースのリトライ付き）
    try:
        from google import genai
        from google.genai import types as genai_types
    except ImportError:
        print("  [Gemini] google-genai 未インストール")
        return None

    client = genai.Client(api_key=api_key)
    config = genai_types.GenerateContentConfig(temperature=temperature)

    @api_retry("gemini", context=f"gemini.generate: {prompt[:60]}")
    def _call_api() -> str:
        resp = client.models.generate_content(model=model, contents=prompt, config=config)
        return resp.text.strip()

    text = _call_api()
    if text is None:
        print(f"  [Gemini] 全リトライ消耗 → スキップ")
        return None

    # キャッシュ保存
    if use_cache:
        cache[key] = {
            "text":      text,
            "cached_at": datetime.now().isoformat(),
            "model":     model,
        }
        _save_cache(cache)

    return text


def strip_code_block(text: str) -> str:
    """Gemini がコードブロックで返してきたとき JSON 部分だけ抜き出す"""
    if text.startswith("```"):
        lines = text.split("\n")
        # 最初と最後の ``` 行を除去
        inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        # 先頭が "json" ならそれも除去
        if inner and inner[0].strip().lower() == "json":
            inner = inner[1:]
        return "\n".join(inner).strip()
    return text
