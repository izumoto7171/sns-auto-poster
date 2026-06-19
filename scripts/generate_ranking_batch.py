"""
ランキング記事 一括生成スクリプト
全6ジャンルのランキング記事を順番に生成・はてなブログに投稿する。

実行:
  python3 scripts/generate_ranking_batch.py           # 全ジャンル生成
  python3 scripts/generate_ranking_batch.py dry-run   # 生成のみ（投稿なし）
  python3 scripts/generate_ranking_batch.py status     # 生成済み確認
"""
import sys
import os
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

GENRES = ["programming", "fx", "credit_card", "eikaiwa", "vod", "denryoku"]


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"

    if mode == "status":
        os.system(f"python3 {ROOT / 'money_agent' / 'ranking_article_generator.py'} status")
        return

    dry_run = mode == "dry-run"
    generated = 0
    failed = 0

    for genre in GENRES:
        print(f"\n{'='*60}")
        print(f"ジャンル: {genre}")
        print(f"{'='*60}")

        args = [genre]
        if dry_run:
            args.append("dry-run")

        cmd = f"python3 {ROOT / 'money_agent' / 'ranking_article_generator.py'} {' '.join(args)}"
        exit_code = os.system(cmd)

        if exit_code == 0:
            generated += 1
            print(f"[OK] {genre} 生成完了")
        else:
            failed += 1
            print(f"[NG] {genre} 生成失敗（exit={exit_code}）")

        # Gemini APIレートリミット対策
        if genre != GENRES[-1]:
            print("30秒待機（API制限対策）...")
            time.sleep(30)

    print(f"\n{'='*60}")
    print(f"結果: 成功={generated} 失敗={failed} / 全{len(GENRES)}ジャンル")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
