"""
共通 JSON キャッシュマネージャー

モード:
  KV モード  : キーと値のマッピング、TTL付き（楽天APIキャッシュ向け）
  List モード: フィールドによる upsert、最大件数制限（A8キャッシュ向け）

使い方:
  from crawlers.cache_manager import CacheManager

  # KV モード（楽天 24h キャッシュ）
  cm = CacheManager(Path("cache.json"), ttl=86400)
  cm.kv_set("key", value)
  cm.kv_get("key")  # 期限切れなら None

  # List モード（A8 プログラム一覧）
  cm = CacheManager(Path("cache.json"), max_entries=30)
  cm.list_upsert(entry, key_field="ins_id")
  cm.list_load()
  cm.increment(key_field="ins_id", key_value="xxx")
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any


class CacheManager:
    def __init__(
        self,
        path: Path,
        max_entries: int | None = None,
        ttl: int | None = None,
    ):
        """
        path       : JSONファイルパス
        max_entries: List モードで保持する最大エントリ数
        ttl        : KV モードのデフォルト TTL（秒）
        """
        self._path = path
        self._max_entries = max_entries
        self._ttl = ttl

    # ── 内部 I/O ────────────────────────────────────────────────

    def _read_raw(self) -> dict | list:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _write_raw(self, data: dict | list) -> None:
        self._path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── KV モード ───────────────────────────────────────────────

    def kv_get(self, key: str, ttl: int | None = None) -> Any | None:
        """
        キーの値を返す。期限切れ or 存在しない場合は None。
        ttl（秒）を指定すると、コンストラクタの ttl を上書きする。
        """
        data = self._read_raw()
        if not isinstance(data, dict) or key not in data:
            return None
        entry = data[key]
        effective_ttl = ttl if ttl is not None else self._ttl
        if effective_ttl and (time.time() - entry.get("ts", 0)) >= effective_ttl:
            return None
        return entry.get("value")

    def kv_get_raw(self, key: str) -> dict | None:
        """期限に関係なく生のエントリ（ts + value）を返す。期限切れキャッシュへの fallback 用。"""
        data = self._read_raw()
        if not isinstance(data, dict):
            return None
        return data.get(key)

    def kv_set(self, key: str, value: Any) -> None:
        """キーに値をセット（タイムスタンプ付き）"""
        data = self._read_raw()
        if not isinstance(data, dict):
            data = {}
        data[key] = {"ts": time.time(), "value": value}
        self._write_raw(data)

    # ── List モード ─────────────────────────────────────────────

    def list_load(self) -> list:
        """全エントリをリストで返す"""
        data = self._read_raw()
        return data if isinstance(data, list) else []

    def list_save(self, entries: list) -> None:
        """リスト全体を保存（max_entries 超過分は先頭から削除）"""
        if self._max_entries:
            entries = entries[-self._max_entries:]
        self._write_raw(entries)

    def list_upsert(self, entry: dict, key_field: str) -> None:
        """
        key_field の値でエントリを検索し、存在すれば上書き・なければ末尾に追加。
        既存エントリの posted_count など引き継ぐべきフィールドは保持する。
        """
        entries = self.list_load()
        key_val = entry.get(key_field)

        existing = next(
            (e for e in entries if e.get(key_field) == key_val),
            None,
        )
        if existing:
            # posted_count など「状態系フィールド」を引き継ぐ
            for field in ("posted_count",):
                if field not in entry and field in existing:
                    entry[field] = existing[field]
                elif field in entry and field in existing:
                    # entry 側が初期値 0 のときは既存値を使う
                    if entry[field] == 0 and existing[field] > 0:
                        entry[field] = existing[field]

        entries = [e for e in entries if e.get(key_field) != key_val]
        entries.append(entry)

        if self._max_entries:
            entries = entries[-self._max_entries:]
        self._write_raw(entries)

    def list_fresh_entries(self, max_age_hours: float = 24.0) -> list:
        """processed_at が max_age_hours 以内のエントリだけ返す"""
        cutoff = time.time() - max_age_hours * 3600
        result = []
        for e in self.list_load():
            ts_str = e.get("processed_at", "")
            try:
                ts = datetime.fromisoformat(ts_str).timestamp()
            except Exception:
                ts = 0
            if ts >= cutoff:
                result.append(e)
        return result

    def increment(
        self,
        key_field: str,
        key_value: str,
        field: str = "posted_count",
    ) -> None:
        """key_field == key_value に一致するエントリの field をインクリメントする"""
        entries = self.list_load()
        for e in entries:
            if e.get(key_field) == key_value:
                e[field] = e.get(field, 0) + 1
                break
        self.list_save(entries)
