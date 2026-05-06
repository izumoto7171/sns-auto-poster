"""
batch_processor.py — Geminiクォータ節約のためのバッチ生成プロセッサ

pending_tasks テーブルから最大 BATCH_SIZE 件の案件を一括取得し、
Gemini に1回のAPIコールで全件のSNS投稿文を生成させる。
生成結果は content_cache テーブルに保存され、x_poster が再利用する。

【節約効果】
  現行: 1件/Geminiコール × システムプロンプト毎回 ≈ 800 token × N件
  改善後: 1コール で N件 → システムプロンプト消費は1回のみ
  理論削減率: 約 60〜70%（N=8の場合）

使い方:
  python3 batch_processor.py               # デフォルト: 8件・post_type=x
  python3 batch_processor.py --n 10        # 最大10件
  python3 batch_processor.py --dry-run     # Gemini不使用でキュー件数だけ確認
  python3 batch_processor.py --post-type x # 投稿タイプ指定
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# プロジェクトルートを sys.path に追加
_ROOT = Path(__file__).parent
sys.path.insert(0, str(_ROOT))

from db_client import db

# ── 定数 ──────────────────────────────────────────────────────
BATCH_SIZE         = 8    # 1回のGeminiコールで処理する最大件数
MIN_TEXT_LEN       = 60   # 生成テキストの最小文字数（これ未満は失敗とみなす）
MAX_TEXT_LEN       = 200  # X投稿の最大文字数（ハッシュタグ除く）
GEMINI_MODEL       = "gemini-2.0-flash-lite"
CACHE_TTL_DAYS     = 3    # content_cache の有効期間

# ── プロンプトテンプレート ──────────────────────────────────────

_BATCH_SYSTEM_PROMPT = """あなたはSNSマーケティングの専門家です。
以下の商品・サービスリストについて、X（Twitter）用の投稿文を一括生成してください。

【制約】
- 各投稿は100〜140文字以内（ハッシュタグ・URLを除く）
- 改行を活用して縦読みしやすくする
- 広告・宣伝っぽい表現は禁止（体験談・比較・情報提供の口調）
- 「いかがでしたか？」などの定型文は禁止
- 自然な話し言葉で書く（SNS口調）
- URLとハッシュタグは含めない（別途追加する）

【ターゲット】一人暮らし20代男性、節約・コスパ重視

【出力形式】必ずJSON配列で返すこと（コードブロックなし）:
[
  {"index": 0, "text": "投稿文..."},
  {"index": 1, "text": "投稿文..."},
  ...
]"""


def _build_batch_prompt(tasks: list) -> str:
    """タスクリストからバッチプロンプトを組み立てる。"""
    items = []
    for i, task in enumerate(tasks):
        data   = task.get("raw_data", {})
        source = task.get("source", "")

        if source == "amazon":
            name      = data.get("name", data.get("title", ""))
            price     = data.get("price", "")
            discount  = data.get("discount_rate", "")
            desc      = str(data.get("description", ""))[:100]
            item_str  = f"Amazon商品: {name} / 価格:{price} / 割引:{discount}% / {desc}"
        elif source == "a8":
            name      = data.get("name", "")
            hashtags  = " ".join(data.get("hashtags", [])[:3])
            reward    = data.get("reward_text", "")
            item_str  = f"A8案件: {name} / 報酬:{reward} / タグ:{hashtags}"
        elif source == "rakuten":
            name      = data.get("name", data.get("itemName", ""))
            price     = data.get("price", data.get("itemPrice", ""))
            review_av = data.get("reviewAverage", "")
            item_str  = f"楽天商品: {name} / 価格:{price}円 / レビュー:{review_av}"
        else:
            item_str = f"商品: {json.dumps(data, ensure_ascii=False)[:150]}"

        items.append(f"[{i}] {item_str}")

    return _BATCH_SYSTEM_PROMPT + "\n\n【商品リスト】\n" + "\n".join(items)


def _call_gemini_batch(prompt: str) -> Optional[str]:
    """Gemini API を呼び出してレスポンスを返す。"""
    try:
        from money_agent.gemini_client import generate
        return generate(prompt, use_cache=False, temperature=0.75)
    except ImportError:
        pass
    # gemini_client が使えない場合は直接呼ぶ（フォールバック）
    try:
        import google.generativeai as genai
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        model = genai.GenerativeModel(GEMINI_MODEL)
        resp  = model.generate_content(prompt)
        return resp.text
    except Exception as e:
        print(f"[BatchProcessor] Gemini呼び出し失敗: {e}")
        return None


def _parse_batch_response(text: str, n: int) -> list[Optional[str]]:
    """
    Geminiのレスポンス（JSON配列）をパースして投稿テキストのリストを返す。
    パース失敗した index は None にする。
    """
    results: list[Optional[str]] = [None] * n

    # コードブロックを除去
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines   = cleaned.split("\n")
        cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            for item in data:
                idx  = item.get("index")
                txt  = item.get("text", "").strip()
                if isinstance(idx, int) and 0 <= idx < n and len(txt) >= MIN_TEXT_LEN:
                    results[idx] = txt[:MAX_TEXT_LEN]
    except json.JSONDecodeError as e:
        print(f"[BatchProcessor] JSONパース失敗: {e}")
        # 部分的な救済: index:X パターンを探してテキストを抽出
        import re
        for m in re.finditer(r'"index"\s*:\s*(\d+).*?"text"\s*:\s*"([^"]+)"', text, re.DOTALL):
            idx = int(m.group(1))
            txt = m.group(2).strip()
            if 0 <= idx < n and len(txt) >= MIN_TEXT_LEN:
                results[idx] = txt[:MAX_TEXT_LEN]

    return results


def run_batch(
    n: int = BATCH_SIZE,
    post_type: str = "x",
    dry_run: bool = False,
    source: Optional[str] = None,
) -> dict:
    """
    バッチ処理のメイン関数。

    Returns:
        {
            "queued":    int,   # pending件数
            "processed": int,   # 今回処理した件数
            "cached":    int,   # content_cacheに保存した件数
            "failed":    int,   # 生成失敗件数
            "skipped":   int,   # キャッシュ済みスキップ件数
        }
    """
    queued = db.count_pending_tasks(post_type=post_type)
    print(f"[BatchProcessor] pending: {queued}件 / 今回処理上限: {n}件")

    if dry_run:
        print("[BatchProcessor] dry-run モード: Gemini呼び出しをスキップ")
        return {"queued": queued, "processed": 0, "cached": 0, "failed": 0, "skipped": 0}

    if queued == 0:
        print("[BatchProcessor] キューが空です。処理をスキップします")
        return {"queued": 0, "processed": 0, "cached": 0, "failed": 0, "skipped": 0}

    # キューから取り出す
    tasks = db.pop_pending_batch(n=n, post_type=post_type, source=source)
    if not tasks:
        return {"queued": queued, "processed": 0, "cached": 0, "failed": 0, "skipped": 0}

    # キャッシュ済みタスクをスキップ
    to_generate: list  = []
    skip_ids:    list  = []
    for task in tasks:
        cached = db.get_content_cache(
            task["product_key"], post_type=post_type, max_age_days=CACHE_TTL_DAYS
        )
        if cached:
            skip_ids.append(task["id"])
        else:
            to_generate.append(task)

    for tid in skip_ids:
        db.mark_task_done(tid)
    print(f"[BatchProcessor] キャッシュ済みスキップ: {len(skip_ids)}件 / 生成対象: {len(to_generate)}件")

    if not to_generate:
        return {
            "queued": queued, "processed": len(tasks),
            "cached": 0, "failed": 0, "skipped": len(skip_ids),
        }

    # Gemini に一括リクエスト（1回のAPIコール）
    prompt = _build_batch_prompt(to_generate)
    print(f"[BatchProcessor] Gemini呼び出し（{len(to_generate)}件分）...")
    raw_response = _call_gemini_batch(prompt)

    cached_count = 0
    failed_count = 0

    if not raw_response:
        # Gemini失敗 → 全タスクを failed に戻す
        for task in to_generate:
            db.mark_task_failed(task["id"], "Geminiレスポンスなし")
        failed_count = len(to_generate)
    else:
        texts = _parse_batch_response(raw_response, len(to_generate))

        for i, (task, text) in enumerate(zip(to_generate, texts)):
            if text:
                db.set_content_cache(
                    product_key    = task["product_key"],
                    source         = task["source"],
                    post_type      = post_type,
                    generated_text = text,
                    metadata       = {
                        "name":        task["raw_data"].get("name", task["raw_data"].get("itemName", "")),
                        "url":         task["raw_data"].get("url", task["raw_data"].get("affiliateUrl", "")),
                        "batch_run":   datetime.now().isoformat(),
                    },
                )
                db.mark_task_done(task["id"])
                cached_count += 1
                print(f"  [{i+1}/{len(to_generate)}] キャッシュ保存: {task['product_key'][:40]}")
            else:
                db.mark_task_failed(task["id"], f"パース失敗(index={i})")
                failed_count += 1
                print(f"  [{i+1}/{len(to_generate)}] 生成失敗: {task['product_key'][:40]}")

    return {
        "queued":    queued,
        "processed": len(tasks),
        "cached":    cached_count,
        "failed":    failed_count,
        "skipped":   len(skip_ids),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Geminiバッチ生成プロセッサ")
    parser.add_argument("--n",         type=int, default=BATCH_SIZE, help=f"最大処理件数 (デフォルト: {BATCH_SIZE})")
    parser.add_argument("--post-type", type=str, default="x",        help="投稿タイプ (デフォルト: x)")
    parser.add_argument("--source",    type=str, default=None,       help="ソース絞り込み: amazon|a8|rakuten")
    parser.add_argument("--dry-run",   action="store_true",          help="Gemini未使用のキュー確認のみ")
    args = parser.parse_args()

    result = run_batch(
        n         = args.n,
        post_type = args.post_type,
        dry_run   = args.dry_run,
        source    = args.source,
    )
    print(f"\n[BatchProcessor] 完了: {result}")
