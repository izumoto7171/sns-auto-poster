"""
pending/ 内の下書き記事を古い順に 1〜2 件ずつ投稿して posted/ に移動する
「フラッシュ・スクリプト」

【用途】
  pending/ に記事が溜まって投稿が止まっている場合の詰まり解消。
  money-agent.yml の ceo-agent ジョブ後に毎回実行される。

【動作】
  1. pending/*.json を古い順にソートして MAX_FLUSH 件取得
  2. Distributor.run() でX/Bluesky/note/はてなへ投稿
  3. 成功した記事を posted/ ディレクトリへ移動（削除はしない）
  4. agent_state.json の last_run と total_articles を更新

【実行】
  python3 money_agent/flush_pending.py            # 最大2件投稿
  python3 money_agent/flush_pending.py --count 1  # 1件のみ
  python3 money_agent/flush_pending.py --dry-run  # 投稿なし（確認用）
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import shutil
import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))


def _load_env():
    env_path = ROOT_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v)


_load_env()

PENDING_DIR = Path(__file__).parent / "data" / "pending"
POSTED_DIR = Path(__file__).parent / "posted"
STATE_FILE = Path(__file__).parent / "data" / "agent_state.json"

MAX_FLUSH = 2  # デフォルト最大件数


def _load_state() -> dict:
    """agent_state.json を読み込む（読めない場合はデフォルト）"""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"total_articles": 0, "today_articles": 0, "last_run": "", "daily_log": []}


def _save_state(state: dict):
    """agent_state.json に書き込む"""
    state["last_run"] = datetime.datetime.now().isoformat()
    try:
        STATE_FILE.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[Flush] agent_state.json 更新: last_run={state['last_run'][:16]}")
    except Exception as e:
        print(f"[Flush] agent_state.json 書き込み失敗: {e}")


def _get_pending_files(count: int) -> list[Path]:
    """pending/ を古い順にソートして count 件返す"""
    PENDING_DIR.mkdir(exist_ok=True)
    files = sorted(PENDING_DIR.glob("*.json"))
    return files[:count]


def _move_to_posted(filepath: Path) -> Path:
    """投稿済みファイルを posted/ に移動して移動先パスを返す"""
    POSTED_DIR.mkdir(exist_ok=True)
    dest = POSTED_DIR / filepath.name
    # 同名ファイルが存在する場合はタイムスタンプ付きでリネーム
    if dest.exists():
        ts = datetime.datetime.now().strftime("%H%M%S")
        dest = POSTED_DIR / f"{filepath.stem}_{ts}.json"
    shutil.move(str(filepath), str(dest))
    return dest


FLUSH_RESULT_FILE = Path("/tmp/flush_result.json")

# プラットフォーム表示名マッピング
_PLATFORM_LABELS = {
    "hatena":  "はてな",
    "note":    "note",
    "x":       "X",
    "bluesky": "Bluesky",
}


def flush(count: int = MAX_FLUSH, dry_run: bool = False):
    """pending/ の記事を最大 count 件投稿して posted/ へ移動する"""
    files = _get_pending_files(count)

    # GitHub Actions サマリー用の結果データ
    flush_result: dict = {
        "dry_run": dry_run,
        "target_count": len(files),
        "flushed": [],      # 投稿成功した記事のリスト
        "skipped": [],      # dry_run でスキップした記事のリスト
        "errors": [],       # エラーが起きた記事のリスト
    }

    if not files:
        print("[Flush] pending/ に記事はありません")
        FLUSH_RESULT_FILE.write_text(json.dumps(flush_result, ensure_ascii=False), encoding="utf-8")
        return

    print(f"\n{'=' * 50}")
    print(f"  [Flush] 対象: {len(files)} 件 / dry_run={dry_run}")
    print(f"{'=' * 50}")

    from money_agent.agents import distributor

    state = _load_state()
    today = datetime.date.today().isoformat()
    flushed = 0

    for filepath in files:
        try:
            article = json.loads(filepath.read_text(encoding="utf-8"))
        except Exception as e:
            msg = f"読み込み失敗: {filepath.name} — {e}"
            print(f"[Flush] {msg}")
            flush_result["errors"].append({"file": filepath.name, "error": msg})
            continue

        keyword = article.get("keyword", filepath.stem)
        title = article.get("title", "タイトルなし")
        pending_since = article.get("pending_since", "")[:10]

        print(f"\n  [{flushed + 1}] {keyword}")
        print(f"       タイトル : {title[:50]}")
        print(f"       保存日   : {pending_since}")

        if dry_run:
            print(f"       → dry-run: スキップ")
            flush_result["skipped"].append({"keyword": keyword, "title": title, "pending_since": pending_since})
            continue

        # 配信実行
        dist_result: dict = {}
        try:
            dist_result = distributor.run(article, dry_run=False)
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            print(f"  [Flush] Distributor エラー: {msg}")
            flush_result["errors"].append({"keyword": keyword, "title": title, "error": msg})
            dist_result = {k: False for k in _PLATFORM_LABELS}

        # 成功・失敗プラットフォームの仕分け（urls/errors は別キーとして除外）
        platform_keys = [k for k in _PLATFORM_LABELS if k in dist_result]
        success_count = sum(bool(dist_result.get(k)) for k in platform_keys)
        print(f"  [Flush] 配信結果: {success_count}/{len(platform_keys)} プラットフォーム")

        ok_platforms = [_PLATFORM_LABELS[k] for k in platform_keys if dist_result.get(k)]
        ng_platforms = [_PLATFORM_LABELS[k] for k in platform_keys if not dist_result.get(k)]

        # URL を取り出す（hatena / note / bluesky）
        urls: dict = dist_result.get("urls", {})
        platform_errors: dict = dist_result.get("errors", {})

        # エラー1行サマリー（失敗プラットフォームのみ）
        error_lines = []
        for pk in platform_keys:
            if not dist_result.get(pk) and pk in platform_errors:
                label = _PLATFORM_LABELS.get(pk, pk)
                error_lines.append(f"{label}: {platform_errors[pk]}")

        flush_result["flushed"].append({
            "keyword":       keyword,
            "title":         title,
            "pending_since": pending_since,
            "ok_platforms":  ok_platforms,
            "ng_platforms":  ng_platforms,
            "success_count": success_count,
            "urls":          {
                "hatena":  urls.get("hatena", ""),
                "note":    urls.get("note", ""),
                "bluesky": urls.get("bluesky", ""),
            },
            "platform_errors": error_lines,
        })

        # posted/ に移動
        dest = _move_to_posted(filepath)
        print(f"  [Flush] 移動: pending/{filepath.name} → posted/{dest.name}")

        # state 更新
        state["total_articles"] = state.get("total_articles", 0) + 1
        state["today_articles"] = state.get("today_articles", 0) + 1
        log_entry = {
            "date": today,
            "keyword": keyword,
            "results": results,
            "flushed_at": datetime.datetime.now().isoformat(),
            "source": "flush_pending",
        }
        state.setdefault("daily_log", []).append(log_entry)
        # daily_log は直近 60 件まで保持
        state["daily_log"] = state["daily_log"][-60:]

        flushed += 1

    print(f"\n[Flush] 完了: {flushed} 件投稿")
    if not dry_run and flushed > 0:
        _save_state(state)

    # GitHub Actions 用に結果ファイルを書き出す
    FLUSH_RESULT_FILE.write_text(
        json.dumps(flush_result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[Flush] 結果ファイル書き出し: {FLUSH_RESULT_FILE}")

    print(f"{'=' * 50}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="pending/の下書き記事をフラッシュ投稿")
    parser.add_argument("--count", type=int, default=MAX_FLUSH, help=f"最大投稿件数（デフォルト: {MAX_FLUSH}）")
    parser.add_argument("--dry-run", action="store_true", help="投稿せず確認のみ")
    args = parser.parse_args()

    flush(count=args.count, dry_run=args.dry_run)
