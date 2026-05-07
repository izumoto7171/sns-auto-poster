"""
batch_processor.py — Geminiクォータ節約のためのバッチ生成プロセッサ

pending_tasks テーブルから案件を取り出し、優先度に応じて Gemini / テンプレートで
投稿文を生成し content_cache に保存する。x_poster は content_cache を読むだけ。

【設計方針（429対策）】
  - 1回の実行: 最大 MAX_BATCHES 回のバッチループ
  - 各バッチ: BATCH_SIZE_PER_CALL 件を Gemini に1コールでまとめて生成
  - バッチ間: BATCH_SLEEP_SEC 秒待機（RPM制限回避）
  - priority >= PRIORITY_THRESHOLD → Gemini生成
  - priority <  PRIORITY_THRESHOLD → テンプレートのみ（Gemini不使用）

使い方:
  python3 batch_processor.py               # デフォルト: post_type=x
  python3 batch_processor.py --dry-run     # Gemini不使用でキュー件数だけ確認
  python3 batch_processor.py --post-type x # 投稿タイプ指定
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).parent
sys.path.insert(0, str(_ROOT))

from db_client import db

# ── 定数 ──────────────────────────────────────────────────────
BATCH_SIZE_PER_CALL = 10   # 1回のGeminiコールで処理する件数上限（API呼び出し回数を半減）
MAX_BATCHES         = 4    # 1回の実行で最大バッチ数（4×10=40件/実行）
BATCH_SLEEP_SEC     = 20   # バッチ間スリープ秒数（RPM制限回避）
PRIORITY_THRESHOLD  = 5    # これ以上はGemini生成、未満はテンプレート
MIN_TEXT_LEN        = 50   # 生成テキストの最小文字数
MAX_TEXT_LEN        = 200  # X投稿の最大文字数（ハッシュタグ除く）
GEMINI_MODEL        = "gemini-2.0-flash-lite"  # X投稿用（軽量・高速）
CACHE_TTL_DAYS      = 3    # content_cache の有効期間

# ── A8用5スタイル定義（batch_processor 側でも保持）────────────
_A8_STYLES_BRIEF = """
スタイル選択肢（A8案件のみ適用。最も効果的なものを1つ選ぶ）:
1. 共感・悩み解決型: 悩みに寄り添い「わかる…」から商品へ
2. 体験レビュー型: 「半信半疑→想像以上」から箇条書きで具体メリット
3. 比較・本音型: 他との違い、耐久性・使いやすさで説得
4. ストーリー・変化型: 失敗の過去→商品との出会い→変化のナラティブ
5. ティザー・ベネフィット型: 「知らないと損」など強い一言→詳細はリンク
"""

# ── バッチプロンプトテンプレート ──────────────────────────────
_SYSTEM_PROMPT_BASE = """あなたはSNSコピーライターです。
以下に最大10件の案件データを与えます。それぞれに最適なスタイルを1つ選び、X（Twitter）用の投稿文を生成してください。

【スタイル選択（各案件に最適なものを1つ）】
- 共感: 読者の悩みから始め「わかる…」から商品へ繋ぐ
- 体験: 「半信半疑→想像以上」から箇条書きで具体的メリット3点
- 比較: 他との違い・耐久性・使いやすさで説得（「結局〇〇に戻った」系）
- ストーリー: 失敗の過去→商品との出会い→変化のナラティブ
- ティザー: 「知らないと損」など強い一言から始め、詳細をリンクへ誘導

{a8_style_block}
【共通制約】
- 各投稿: 70〜110文字以内（ハッシュタグ・URL除く）
- 禁止ワード: 「ぜひ」「おすすめ」「チェック」「ご確認ください」「いかがでしたか」
- 独り言・本音の口コミに見える口調を徹底
- スマホで読みやすい改行・空白行を入れる
- URLとハッシュタグは含めない（別途追加する）
- 「リンクから」などのURL誘導フレーズも書かない

【出力形式】必ずJSON配列のみ（コードブロック・説明不要）:
[
  {{"index": 0, "text": "投稿文..."}},
  {{"index": 1, "text": "投稿文..."}},
  ...
]"""


def _build_batch_prompt(tasks: list) -> str:
    has_a8 = any(t.get("source") == "a8" for t in tasks)
    a8_block = _A8_STYLES_BRIEF if has_a8 else ""
    system = _SYSTEM_PROMPT_BASE.format(a8_style_block=a8_block)

    items = []
    for i, task in enumerate(tasks):
        data   = task.get("raw_data", {})
        source = task.get("source", "")
        prio   = task.get("priority", 0)

        if source == "amazon":
            name     = data.get("name", data.get("title", ""))
            price    = data.get("price", "")
            discount = data.get("discount_rate", "")
            desc     = str(data.get("description", ""))[:80]
            item_str = f"Amazon商品: {name} / 価格:{price} / 割引:{discount}% / {desc}"
        elif source == "a8":
            name     = data.get("name", "")
            reward   = data.get("reward_text", data.get("reward", ""))
            tags     = " ".join(data.get("hashtags", [])[:3])
            item_str = f"A8案件: {name} / 報酬:{reward} / ジャンル:{tags}"
        elif source == "rakuten":
            name     = data.get("name", data.get("itemName", ""))
            price    = data.get("price", data.get("itemPrice", ""))
            review   = data.get("reviewAverage", "")
            item_str = f"楽天商品: {name} / 価格:{price}円 / レビュー:{review}"
        else:
            item_str = f"商品: {json.dumps(data, ensure_ascii=False)[:120]}"

        items.append(f"[{i}] (priority={prio}) {item_str}")

    return system + "\n\n【商品リスト】\n" + "\n".join(items)


def _parse_batch_response(text: str, n: int) -> list[Optional[str]]:
    results: list[Optional[str]] = [None] * n

    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines   = cleaned.split("\n")
        cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            for item in data:
                idx = item.get("index")
                txt = item.get("text", "").strip()
                if isinstance(idx, int) and 0 <= idx < n and len(txt) >= MIN_TEXT_LEN:
                    results[idx] = txt[:MAX_TEXT_LEN]
    except json.JSONDecodeError as e:
        print(f"[BatchProcessor] JSONパース失敗: {e}")
        import re
        for m in re.finditer(r'"index"\s*:\s*(\d+).*?"text"\s*:\s*"([^"]+)"', text, re.DOTALL):
            idx = int(m.group(1))
            txt = m.group(2).strip()
            if 0 <= idx < n and len(txt) >= MIN_TEXT_LEN:
                results[idx] = txt[:MAX_TEXT_LEN]

    return results


def _call_gemini_batch(prompt: str) -> Optional[str]:
    try:
        from money_agent.gemini_client import generate
        return generate(prompt, model=GEMINI_MODEL, use_cache=False, temperature=0.75)
    except ImportError:
        pass
    try:
        import google.generativeai as genai
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        model = genai.GenerativeModel(GEMINI_MODEL)
        resp  = model.generate_content(prompt)
        return resp.text
    except Exception as e:
        print(f"[BatchProcessor] Gemini呼び出し失敗: {e}")
        return None


# ── テンプレート生成（低優先度案件・Gemini不使用）────────────
def _generate_template_text(task: dict) -> str:
    data   = task.get("raw_data", {})
    source = task.get("source", "")

    if source == "a8":
        name   = data.get("name", "サービス")
        reward = data.get("reward_text", data.get("reward", "特典あり"))
        templates = [
            f"毎月の固定費、見直してみたら{name}が思いのほか使えた。\n{reward}もついてきて、登録して正解だった。",
            f"半信半疑で登録した{name}。\n手続きが簡単で{reward}の特典まであった。\nもっと早く知りたかった。",
            f"似たサービスも試したけど、結局{name}に落ち着いた。\n使い勝手と{reward}という条件が決め手。",
            f"副業を始めようと思っても何から手を付けるかわからなかった。\n{name}を知ってから少し動けるようになった。\n{reward}の条件も悪くない。",
            f"これ、知らないと損かもしれない。\n{name}、{reward}の特典がついてくる。",
        ]
        return random.choice(templates)

    if source == "amazon":
        name  = data.get("name", data.get("title", "商品"))
        price = data.get("price", "")
        price_str = f"（{price}円）" if price else ""
        templates = [
            f"最近買ってよかったもの。\n{name}{price_str}、普通に使えて満足してる。",
            f"{name}、コスパ良くて気に入ってる。\n一人暮らしに向いてると思う。",
            f"ずっと迷ってた{name}、買って正解だった。\n{price_str}この価格でこのクオリティは納得。",
        ]
        return random.choice(templates)

    if source == "rakuten":
        name  = data.get("name", data.get("itemName", "商品"))
        price = data.get("price", data.get("itemPrice", ""))
        price_str = f"（{price}円）" if price else ""
        templates = [
            f"楽天で買った{name}{price_str}、想像以上に良かった。",
            f"{name}、コスパ最強かもしれない。{price_str}この値段は正直驚いた。",
        ]
        return random.choice(templates)

    return f"最近気になってる商品。コスパ良さそうで試してみた。"


# ── メインバッチ処理ループ ─────────────────────────────────────
def run_batches(
    post_type: str = "x",
    dry_run: bool = False,
    source: Optional[str] = None,
) -> dict:
    """
    優先度ベースのバッチ処理ループ。

    - priority >= PRIORITY_THRESHOLD: Gemini生成（バッチ）
    - priority <  PRIORITY_THRESHOLD: テンプレート生成（即時）
    - MAX_BATCHES 回のループ、バッチ間は BATCH_SLEEP_SEC 秒待機

    Returns:
        {"queued", "processed", "cached", "failed", "skipped", "template_gen"}
    """
    total_queued  = db.count_pending_tasks(post_type=post_type)
    print(f"[BatchProcessor] pending: {total_queued}件 / 最大 {MAX_BATCHES}バッチ × {BATCH_SIZE_PER_CALL}件")

    if dry_run:
        print("[BatchProcessor] dry-run: Gemini呼び出しをスキップ")
        return {"queued": total_queued, "processed": 0, "cached": 0,
                "failed": 0, "skipped": 0, "template_gen": 0}

    if total_queued == 0:
        print("[BatchProcessor] キューが空。処理をスキップ")
        return {"queued": 0, "processed": 0, "cached": 0,
                "failed": 0, "skipped": 0, "template_gen": 0}

    total_processed  = 0
    total_cached     = 0
    total_failed     = 0
    total_skipped    = 0
    total_template   = 0

    for batch_num in range(MAX_BATCHES):
        tasks = db.pop_pending_batch(n=BATCH_SIZE_PER_CALL, post_type=post_type, source=source)
        if not tasks:
            print(f"[BatchProcessor] バッチ{batch_num+1}: キュー枯渇。終了")
            break

        print(f"\n[BatchProcessor] バッチ {batch_num+1}/{MAX_BATCHES} （{len(tasks)}件）")

        # キャッシュ済みをスキップ
        to_process: list = []
        for task in tasks:
            cached = db.get_content_cache(
                task["product_key"], post_type=post_type, max_age_days=CACHE_TTL_DAYS
            )
            if cached:
                db.mark_task_done(task["id"])
                total_skipped += 1
                print(f"  [skip] キャッシュ済み: {task['product_key'][:40]}")
            else:
                to_process.append(task)

        total_processed += len(tasks)

        if not to_process:
            continue

        # 優先度で分割
        high_prio = [t for t in to_process if (t.get("priority") or 0) >= PRIORITY_THRESHOLD]
        low_prio  = [t for t in to_process if (t.get("priority") or 0) <  PRIORITY_THRESHOLD]

        print(f"  高優先度（Gemini）: {len(high_prio)}件 / 低優先度（テンプレ）: {len(low_prio)}件")

        # ── 低優先度: テンプレートで即時生成・キャッシュ ──────
        for task in low_prio:
            text = _generate_template_text(task)
            db.set_content_cache(
                product_key    = task["product_key"],
                source         = task["source"],
                post_type      = post_type,
                generated_text = text,
                metadata       = {
                    "name":     task["raw_data"].get("name", task["raw_data"].get("itemName", "")),
                    "batch_run": datetime.now().isoformat(),
                    "method":   "template",
                    "priority": task.get("priority", 0),
                },
            )
            db.mark_task_done(task["id"])
            total_cached   += 1
            total_template += 1
            print(f"  [template] 保存: {task['product_key'][:40]} (priority={task.get('priority',0)})")

        # ── 高優先度: Gemini バッチ生成 ───────────────────────
        if high_prio:
            prompt      = _build_batch_prompt(high_prio)
            raw_response = _call_gemini_batch(prompt)

            if not raw_response:
                # バッチ全体失敗 → 全タスクをテンプレートで救済
                for task in high_prio:
                    fallback = _generate_template_text(task)
                    db.set_content_cache(
                        product_key    = task["product_key"],
                        source         = task["source"],
                        post_type      = post_type,
                        generated_text = fallback,
                        metadata       = {"method": "template_fallback_batch", "priority": task.get("priority", 0)},
                    )
                    db.mark_task_done(task["id"])
                    total_cached   += 1
                    total_template += 1
                    print(f"  [fallback] バッチ失敗→テンプレ保存: {task['product_key'][:40]}")
            else:
                texts = _parse_batch_response(raw_response, len(high_prio))
                for i, (task, text) in enumerate(zip(high_prio, texts)):
                    if text:
                        db.set_content_cache(
                            product_key    = task["product_key"],
                            source         = task["source"],
                            post_type      = post_type,
                            generated_text = text,
                            metadata       = {
                                "name":     task["raw_data"].get("name", task["raw_data"].get("itemName", "")),
                                "url":      task["raw_data"].get("url", task["raw_data"].get("affiliateUrl", "")),
                                "batch_run": datetime.now().isoformat(),
                                "method":   "gemini",
                                "priority": task.get("priority", 0),
                            },
                        )
                        db.mark_task_done(task["id"])
                        total_cached += 1
                        print(f"  [gemini] 保存: {task['product_key'][:40]} (priority={task.get('priority',0)})")
                    else:
                        # Gemini失敗 → テンプレートでフォールバック保存
                        fallback = _generate_template_text(task)
                        db.set_content_cache(
                            product_key    = task["product_key"],
                            source         = task["source"],
                            post_type      = post_type,
                            generated_text = fallback,
                            metadata       = {"method": "template_fallback", "priority": task.get("priority", 0)},
                        )
                        db.mark_task_done(task["id"])
                        total_cached   += 1
                        total_template += 1
                        print(f"  [fallback] テンプレ保存: {task['product_key'][:40]}")

        # バッチ間スリープ（最終バッチは不要）
        if batch_num < MAX_BATCHES - 1:
            remaining = db.count_pending_tasks(post_type=post_type)
            if remaining == 0:
                print("[BatchProcessor] キュー空。早期終了")
                break
            print(f"  → {BATCH_SLEEP_SEC}秒待機（RPM制限回避）... 残り: {remaining}件")
            time.sleep(BATCH_SLEEP_SEC)

    result = {
        "queued":       total_queued,
        "processed":    total_processed,
        "cached":       total_cached,
        "failed":       total_failed,
        "skipped":      total_skipped,
        "template_gen": total_template,
    }
    print(f"\n[BatchProcessor] 完了: {result}")
    return result


# ── 後方互換ラッパー ──────────────────────────────────────────
def run_batch(
    n: int = BATCH_SIZE_PER_CALL,
    post_type: str = "x",
    dry_run: bool = False,
    source: Optional[str] = None,
) -> dict:
    return run_batches(post_type=post_type, dry_run=dry_run, source=source)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Geminiバッチ生成プロセッサ（クォータ節約版）")
    parser.add_argument("--post-type", type=str, default="x",    help="投稿タイプ (デフォルト: x)")
    parser.add_argument("--source",    type=str, default=None,   help="ソース絞り込み: amazon|a8|rakuten")
    parser.add_argument("--dry-run",   action="store_true",      help="Gemini未使用のキュー確認のみ")
    args = parser.parse_args()

    run_batches(
        post_type = args.post_type,
        dry_run   = args.dry_run,
        source    = args.source,
    )
