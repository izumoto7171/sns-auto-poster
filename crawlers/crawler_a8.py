"""
A8.net クローラー + X投稿用キャッシュ管理（永久機関版）

【2ファイル構成】
  a8_programs_cache.json   — 投稿キュー（新規案件が入り、投稿後に消える）
  a8_programs_history.json — 全履歴（重複なし・上限500件・永続保存）

【投稿選択ロジック】
  1. キャッシュ（キュー）に在庫あり → weighted_choice で1件選択 → 投稿後にキューから削除
  2. キャッシュが空               → 履歴からランダムに1件選択（投稿は続く・止まらない）

提供する公開 API:
  save_program(program, affiliate_url, hatena_url="")
      → キュー + 履歴に upsert（スクレイピング時に呼ぶ）

  select_for_post() -> (program: dict, source: str)
      → "cache" | "history" | "empty" を返す
      → x_post_generator.generate_a8_program_post() から呼ぶ

  pop_from_cache(ins_id)
      → 投稿完了後にキューから削除（消費キュー動作）

  increment_posted_history(ins_id)
      → 履歴の posted_count をインクリメント（分析用）

  # 後方互換（既存コードが壊れないよう残す）
  load_programs() -> list
  weighted_choice(candidates) -> dict
  increment_posted(ins_id)
  extract_hashtags(name, reward) -> list
"""
from __future__ import annotations

import re
import json
import random
import sys
from datetime import datetime
from pathlib import Path

_ROOT_DIR    = Path(__file__).parent.parent
_CACHE_PATH  = _ROOT_DIR / "money_agent" / "a8_programs_cache.json"
_HISTORY_PATH = _ROOT_DIR / "money_agent" / "a8_programs_history.json"
_CACHE_MAX   = 30   # キューの最大件数（古いものは履歴に残してキューから溢れる）
_HISTORY_MAX = 500  # 履歴の上限（半永久的に保持）

sys.path.insert(0, str(_ROOT_DIR))
from crawlers.cache_manager import CacheManager

_cache   = CacheManager(_CACHE_PATH,   max_entries=_CACHE_MAX)
_history = CacheManager(_HISTORY_PATH, max_entries=_HISTORY_MAX)


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


# ── 保存 ─────────────────────────────────────────────────────────

def save_program(
    program: dict,
    affiliate_url: str,
    hatena_url: str = "",
) -> None:
    """
    A8 プログラムをキュー（cache）と履歴（history）の両方に upsert する。

    - キュー : max 30件。投稿後に pop_from_cache() で削除される消費型。
    - 履歴   : max 500件。削除されない永続ストア。キューが空の場合のフォールバック。
    - ins_id が既存の場合は posted_count を引き継ぐ。
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

    ins_id = entry["ins_id"]

    try:
        _cache.list_upsert(entry, key_field="ins_id")
        print(f"  [A8Cache] キュー保存: {name}")
    except Exception as e:
        print(f"  [A8Cache] キュー保存失敗 ({ins_id}): {e}")

    try:
        _history.list_upsert(entry, key_field="ins_id")
        print(f"  [A8Cache] 履歴保存: {name}")
    except Exception as e:
        print(f"  [A8Cache] 履歴保存失敗 ({ins_id}): {e}")


# ── 投稿選択（永久機関の中核） ────────────────────────────────────

def select_for_post() -> tuple[dict, str]:
    """
    X投稿用に案件を1件選択する。

    Returns
    -------
    (program, source)
      source == "cache"   : キューから選択（投稿後に pop_from_cache() を呼ぶこと）
      source == "history" : 履歴フォールバック（キューは空のまま）
      source == "empty"   : キューも履歴も空（program は {}）
    """
    # 1. キュー（消費型）から weighted_choice
    queue = _cache.list_load()
    if queue:
        selected = weighted_choice(queue[-20:])
        print(f"  [A8Post] キューから選択: {selected.get('name','')} (残 {len(queue)} 件)")
        return selected, "cache"

    # 2. キューが空 → 履歴からランダム選択（投稿は止まらない）
    hist = _history.list_load()
    if hist:
        selected = random.choice(hist)
        print(f"  [A8Post] 履歴フォールバック: {selected.get('name','')} (履歴 {len(hist)} 件)")
        return selected, "history"

    print("  [A8Post] キューも履歴も空 → A8投稿スキップ")
    return {}, "empty"


def pop_from_cache(ins_id: str) -> None:
    """
    投稿完了後にキューから案件を削除する（消費キュー動作）。
    履歴には残るので再利用可能。
    """
    if not ins_id:
        return
    try:
        entries = _cache.list_load()
        before  = len(entries)
        entries = [e for e in entries if e.get("ins_id") != ins_id]
        _cache.list_save(entries)
        print(f"  [A8Post] キューから削除: {ins_id} (残 {len(entries)}/{before} 件)")
    except Exception as e:
        print(f"  [A8Post] キュー削除失敗 ({ins_id}): {e}")


def increment_posted_history(ins_id: str) -> None:
    """
    履歴の posted_count をインクリメントする（分析用）。
    キューが空で履歴から選ばれた場合に呼ぶ。
    """
    if not ins_id:
        return
    try:
        _history.increment(key_field="ins_id", key_value=ins_id, field="posted_count")
    except Exception as e:
        print(f"  [A8Post] 履歴 posted_count 更新失敗 ({ins_id}): {e}")


# ── 後方互換 API ─────────────────────────────────────────────────

def load_programs() -> list:
    """キャッシュ（キュー）から全プログラムを返す（後方互換）"""
    return _cache.list_load()


def weighted_choice(candidates: list) -> dict:
    """
    posted_count に基づいて加重ランダム選択する。
    weight = 1 / (posted_count + 1)
    """
    if not candidates:
        raise ValueError("候補が空です")
    weights = [1.0 / (p.get("posted_count", 0) + 1) for p in candidates]
    return random.choices(candidates, weights=weights, k=1)[0]


def increment_posted(ins_id: str) -> None:
    """キューの posted_count をインクリメントする（後方互換）"""
    try:
        _cache.increment(key_field="ins_id", key_value=ins_id, field="posted_count")
    except Exception as e:
        print(f"  [A8Cache] posted_count 更新失敗: {e}")
