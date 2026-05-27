"""
テンプレート自動改善オプティマイザー

analyzer.py でスキップ率が高いテンプレートを特定し、
Gemini API で新しいバリエーションを生成して content_pool.json を更新する。

使い方:
  python3 optimizer.py --report-only          # 分析のみ（変更なし）
  python3 optimizer.py --apply-fix            # ワースト5件を自動改善
  python3 optimizer.py --apply-fix --top 3    # ワースト3件を改善
  python3 optimizer.py --apply-fix --dry-run  # 生成内容を確認（pool 更新なし）
"""
import json
import os
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional

BASE_DIR  = Path(__file__).parent
POOL_FILE = BASE_DIR / "content_pool.json"

sys.path.insert(0, str(BASE_DIR))
from analyzer import analyze, print_report, DEFAULT_TOP_N

VARIATIONS_PER_TEMPLATE = 5
MIN_SKIP_RATE_THRESHOLD  = 0.3   # この値以上のスキップ率を持つテンプレートを改善対象にする


# ─────────────────────────────────────────
# プール操作
# ─────────────────────────────────────────

def load_pool() -> dict:
    try:
        with POOL_FILE.open(encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[ERROR] content_pool.json の読み込みに失敗: {e}")
        sys.exit(1)


def save_pool(pool: dict):
    pool["updated_at"] = datetime.now().strftime("%Y-%m-%d")
    pool["total"]      = len([i for i in pool["items"] if not i.get("deprecated")])
    try:
        with POOL_FILE.open("w", encoding="utf-8") as f:
            json.dump(pool, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[ERROR] content_pool.json の保存に失敗: {e}")
        sys.exit(1)


# ─────────────────────────────────────────
# 成功事例の取得
# ─────────────────────────────────────────

def load_success_examples(n: int = 5) -> list[str]:
    """post_log.json から成功した投稿テキストを返す（直近n件）"""
    log_file = BASE_DIR / "post_log.json"
    if not log_file.exists():
        return []
    try:
        with log_file.open(encoding="utf-8") as f:
            log = json.load(f)
    except Exception:
        return []
    return [
        e.get("text", "")
        for e in log
        if e.get("success") and e.get("text")
    ][-n:]


# ─────────────────────────────────────────
# Gemini によるバリエーション生成
# ─────────────────────────────────────────

def _build_rewrite_prompt(
    original_text: str,
    post_type: str,
    diagnosis: str,
    success_examples: list[str],
    n: int,
) -> str:
    success_block = ""
    if success_examples:
        joined = "\n---\n".join(success_examples[:3])
        success_block = f"""
【参考：過去の成功投稿例（トーン・構造を参考にする）】
{joined}
"""

    type_direction = {
        "useful":   "AI副業・時短・節約・生産性向上に関する役立つ情報",
        "empathy":  "副業や生活改善での失敗談・体験談・共感を呼ぶ内容",
        "trivia":   "AI・テクノロジー・お金に関する意外な雑学・ネタ",
        "product":  "AIツールや副業サービスを体験談として自然に紹介する内容",
        "progress": "AI副業の現在進行形の検証ログ・正直な途中経過",
    }.get(post_type, "副業・AI関連の有益な情報")

    return f"""あなたはX（Twitter）副業コンテンツのコピーライターです。

以下の投稿は重複スキップが多く、リライトが必要です。
診断: {diagnosis}

【改善対象の投稿（タイプ: {post_type} / {type_direction}）】
---
{original_text}
---
{success_block}
【依頼】
・トピックとジャンル（{post_type}）は維持する
・フック（1行目）と全体の切り口を完全に変えた投稿を{n}つ生成する
・各バリエーションのフックは互いに重複しないこと

【絶対ルール】
1. 100〜140文字以内（ハッシュタグ除く）
2. AIっぽい表現禁止（「〜しましょう」「〜が重要です」「〜といえます」等）
3. 完璧な情報より、生々しい体験談・失敗談・気づきを優先する
4. 改行で縦読みしやすくする
5. ハッシュタグは出力しない
6. 各フックは「{original_text.split(chr(10))[0][:20]}」と被らない新しい切り口にする

出力形式（JSONのみ・説明文不要）:
{{
  "variations": [
    "バリエーション1の全文",
    "バリエーション2の全文"
  ]
}}"""


def generate_variations(
    original_text: str,
    post_type: str,
    diagnosis: str,
    success_examples: list[str],
    api_key: str,
    n: int = VARIATIONS_PER_TEMPLATE,
) -> list[str]:
    """Gemini でリライトバリエーションを生成する"""
    try:
        from google import genai
    except ImportError:
        print("[ERROR] google-genai が未インストール: pip install google-genai")
        return []

    prompt = _build_rewrite_prompt(original_text, post_type, diagnosis, success_examples, n)

    try:
        client = genai.Client(api_key=api_key)
        resp   = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt,
        )
        raw = resp.text.strip()
    except Exception as e:
        print(f"  [ERROR] Gemini 呼び出し失敗: {e}")
        return []

    # ```json ... ``` ブロックを除去
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) >= 2 else raw
        if raw.startswith("json"):
            raw = raw[4:]

    try:
        data = json.loads(raw.strip())
        return [v.strip() for v in data.get("variations", []) if v.strip()]
    except json.JSONDecodeError as e:
        print(f"  [ERROR] Gemini レスポンスのパース失敗: {e}")
        print(f"  レスポンス先頭: {raw[:200]}")
        return []


# ─────────────────────────────────────────
# プール更新
# ─────────────────────────────────────────

def apply_optimizations(
    worst_templates: list[dict],
    api_key: str,
    top_n: int,
    dry_run: bool = False,
) -> dict:
    """
    ワーストテンプレートに対しバリエーションを生成し、
    content_pool.json を更新する。

    Returns:
        {"added": int, "deprecated": int, "skipped": int}
    """
    pool          = load_pool()
    items         = pool["items"]
    existing_ids  = {item["id"] for item in items}
    existing_hooks = {item.get("hook", "") for item in items if not item.get("deprecated")}
    success_examples = load_success_examples()

    # プール未登録（Gemini生成パターン）はスキップ、登録済みのみ対象
    targets = [
        t for t in worst_templates
        if t.get("pool_item_text") and t.get("skip_rate", 0) >= MIN_SKIP_RATE_THRESHOLD
    ][:top_n]

    if not targets:
        print(
            f"\n改善対象のテンプレートが見つかりません。"
            f"（スキップ率 {MIN_SKIP_RATE_THRESHOLD:.0%} 未満 or pool未登録）"
        )
        return {"added": 0, "deprecated": 0, "skipped": len(worst_templates)}

    added_total = deprecated_total = skipped_total = 0

    for t in targets:
        pool_id    = t["pool_item_id"]
        orig_text  = t["pool_item_text"]
        post_type  = t["pool_item_type"]
        label      = t.get("pool_item_label") or post_type
        diagnosis  = t["diagnosis"]

        print(f"\n改善中: {pool_id}  スキップ率: {t['skip_rate']:.0%}")
        print(f"  フック : {t['hook']}")
        print(f"  診断   : {diagnosis}")

        variations = generate_variations(
            orig_text, post_type, diagnosis, success_examples, api_key
        )

        if not variations:
            skipped_total += 1
            continue

        if dry_run:
            print(f"  [DRY RUN] {len(variations)}件のバリエーションを生成しました（pool更新なし）:")
            for i, v in enumerate(variations, 1):
                print(f"    [{i}] {v[:70]}...")
            continue

        # 既存アイテムを deprecated にマーク
        for item in items:
            if item["id"] == pool_id:
                item["deprecated"]    = True
                item["deprecated_at"] = datetime.now().strftime("%Y-%m-%d")
                deprecated_total += 1
                break

        # 新バリエーションを追加
        added = 0
        for var_idx, var_text in enumerate(variations):
            new_id   = f"{pool_id}_opt{var_idx:02d}"
            new_hook = var_text.split("\n")[0].strip()

            # 重複IDまたはフック重複はスキップ
            if new_id in existing_ids or new_hook in existing_hooks:
                continue

            new_item = {
                "id":         new_id,
                "type":       post_type,
                "label":      label,
                "text":       var_text,
                "hook":       new_hook,
                "source":     "optimized",
                "parent_id":  pool_id,
                "created_at": datetime.now().strftime("%Y-%m-%d"),
                "deprecated": False,
            }
            items.append(new_item)
            existing_ids.add(new_id)
            existing_hooks.add(new_hook)
            added += 1
            added_total += 1

        print(f"  {added}件のバリエーションを追加しました")

    if not dry_run:
        # deprecated を末尾に移動
        pool["items"] = (
            [i for i in items if not i.get("deprecated")]
            + [i for i in items if i.get("deprecated")]
        )
        save_pool(pool)
        print(f"\n完了: {added_total}件追加 / {deprecated_total}件をdeprecated化 / {skipped_total}件スキップ")
        print(f"更新済み: {POOL_FILE}")
    else:
        print(f"\n[DRY RUN完了] 実際のファイル変更はなし。--apply-fix で実行してください。")

    return {"added": added_total, "deprecated": deprecated_total, "skipped": skipped_total}


# ─────────────────────────────────────────
# .env 読み込みユーティリティ
# ─────────────────────────────────────────

def _load_env():
    env_path = BASE_DIR / ".." / ".env"
    if env_path.exists():
        with env_path.open() as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


# ─────────────────────────────────────────
# CLI
# ─────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="テンプレート自動改善オプティマイザー")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--report-only", action="store_true", help="分析レポートのみ出力（変更なし）")
    mode.add_argument("--apply-fix",   action="store_true", help="分析に基づきテンプレートを自動改善")

    parser.add_argument("--top",     type=int,            default=DEFAULT_TOP_N, help=f"改善対象件数（デフォルト: {DEFAULT_TOP_N}）")
    parser.add_argument("--dry-run", action="store_true", help="生成内容を確認するが pool は更新しない")
    args = parser.parse_args()

    # 分析
    report = analyze(top_n=args.top)
    worst  = print_report(report, top_n=args.top)

    if report["total_skips"] == 0:
        print("post_skip.log が空です。先に human_post_generator.py を実行してください。")
        return

    if args.report_only:
        return

    # API キー確認
    _load_env()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("\n[ERROR] GEMINI_API_KEY が未設定です（.env に GEMINI_API_KEY=xxx を追加してください）")
        sys.exit(1)

    mode_label = "[DRY RUN]" if args.dry_run else "[LIVE]"
    print(f"\n{mode_label} ワースト{args.top}件のテンプレートを改善します...")
    apply_optimizations(worst, api_key, top_n=args.top, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
