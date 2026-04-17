"""
A8.net クローラー + X投稿用キャッシュ管理

提供する公開 API:
  save_program(program, affiliate_url, hatena_url="")  → キャッシュへ upsert
  load_programs() -> list                              → キャッシュ全件取得
  weighted_choice(programs) -> dict                    → 投稿頻度加重選択
  increment_posted(ins_id)                             → 投稿回数インクリメント
  extract_hashtags(name, reward) -> list               → Gemini でハッシュタグ抽出

キャッシュ先: money_agent/a8_programs_cache.json（max 30件、List モード）
"""
from __future__ import annotations

import re
import json
import sys
from datetime import datetime
from pathlib import Path

_ROOT_DIR   = Path(__file__).parent.parent        # tiktok-lifehack/
_CACHE_PATH = _ROOT_DIR / "money_agent" / "a8_programs_cache.json"
_CACHE_MAX  = 30

sys.path.insert(0, str(_ROOT_DIR))
from crawlers.cache_manager import CacheManager

_cache = CacheManager(_CACHE_PATH, max_entries=_CACHE_MAX)


# ── ハッシュタグ抽出 ─────────────────────────────────────────────

def extract_hashtags(name: str, reward: str) -> list:
    """
    Gemini でプログラムのジャンルに合った X ハッシュタグを 2〜3 個抽出する。
    失敗時は空リストを返す（呼び出し元でデフォルト値を設定すること）。
    """
    try:
        sys.path.insert(0, str(_ROOT_DIR / "money_agent"))
        from gemini_client import generate as gemini_generate
    except ImportError:
        return []

    prompt = f"""以下のアフィリエイトプログラムに最適な X（Twitter）ハッシュタグを 2〜3 個選んでください。

サービス名: {name}
報酬・特徴: {reward}

ルール:
- #PR は除く（別途付加するため）
- ジャンルを表す具体的なタグ（例: #クラウド会計 #副業 #美容 #投資 #節約）
- 検索ボリュームが多い一般的なタグを優先する
- JSON 配列のみで返す（コードブロック不要）: ["#タグ1", "#タグ2"]"""

    try:
        result = gemini_generate(prompt, use_cache=True)
        if result:
            m = re.search(r'\[.*?\]', result, re.DOTALL)
            if m:
                tags = json.loads(m.group())
                return [t for t in tags if isinstance(t, str) and t.startswith("#")][:3]
    except Exception:
        pass
    return []


# ── キャッシュ操作 ───────────────────────────────────────────────

def save_program(
    program: dict,
    affiliate_url: str,
    hatena_url: str = "",
) -> None:
    """
    A8 プログラムを X投稿用キャッシュに upsert する。
    ins_id が既存の場合は posted_count を引き継ぐ。
    ハッシュタグは Gemini で自動抽出する（失敗時は #副業）。
    """
    name   = program.get("name", "")
    reward = program.get("reward", "")

    hashtags = extract_hashtags(name, reward) or ["#副業"]
    print(f"  [A8Cache] ハッシュタグ: {hashtags}")

    entry = {
        "ins_id":        program.get("ins_id", ""),
        "name":          name,
        "company":       program.get("company", ""),
        "reward":        reward,
        "affiliate_url": affiliate_url,
        "hatena_url":    hatena_url,
        "hashtags":      hashtags,
        "posted_count":  0,
        "processed_at":  datetime.now().isoformat(),
    }

    try:
        _cache.list_upsert(entry, key_field="ins_id")
        print(f"  [A8Cache] キャッシュ保存: {name}")
    except Exception as e:
        print(f"  [A8Cache] キャッシュ保存失敗: {e}")


def load_programs() -> list:
    """キャッシュから全プログラムを返す"""
    return _cache.list_load()


def weighted_choice(candidates: list) -> dict:
    """
    posted_count に基づいて加重ランダム選択する。
    weight = 1 / (posted_count + 1)
      posted_count=0 → weight 1.0
      posted_count=1 → weight 0.5
      posted_count=2 → weight 0.33 …
    """
    import random
    if not candidates:
        raise ValueError("候補が空です")
    weights = [1.0 / (p.get("posted_count", 0) + 1) for p in candidates]
    return random.choices(candidates, weights=weights, k=1)[0]


def increment_posted(ins_id: str) -> None:
    """ins_id に対応するエントリの posted_count をインクリメントする"""
    try:
        _cache.increment(key_field="ins_id", key_value=ins_id, field="posted_count")
    except Exception as e:
        print(f"  [A8Cache] posted_count 更新失敗: {e}")
