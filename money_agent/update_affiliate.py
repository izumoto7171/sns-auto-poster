"""
アフィリエイトURL一括更新スクリプト
A8.net等で提携承認されたら、このスクリプトでURLを更新するだけで
全記事生成に自動反映される

【使い方】
  # URLを更新
  python3 money_agent/config/update_affiliate.py freee_accounting "https://px.a8.net/..."

  # ステータスを確認
  python3 money_agent/config/update_affiliate.py --status

  # 全pendingを一覧表示
  python3 money_agent/config/update_affiliate.py --pending
"""
import json
import sys
from pathlib import Path

CONFIG_FILE = Path(__file__).parent / "data" / "affiliate_links.json"


def load() -> dict:
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))


def save(data: dict):
    CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def update_url(program_id: str, new_url: str):
    """URLを更新してstatusをactiveに変更"""
    data = load()
    if program_id not in data:
        print(f"エラー: '{program_id}' が見つかりません")
        print(f"有効なID: {[k for k in data if not k.startswith('_')]}")
        return False

    old_url = data[program_id].get("url", "")
    data[program_id]["url"] = new_url
    data[program_id]["status"] = "active"
    data[program_id]["note"] = "提携承認済み・URL更新済み"
    save(data)

    print(f"更新完了: {program_id}")
    print(f"  旧: {old_url[:60]}")
    print(f"  新: {new_url[:60]}")
    print(f"  → 次回記事生成から自動的に新URLが使われます")
    return True


def show_status():
    """全プログラムのステータスを表示"""
    data = load()
    active = [(k, v) for k, v in data.items() if not k.startswith("_") and v.get("status") == "active"]
    pending = [(k, v) for k, v in data.items() if not k.startswith("_") and v.get("status") == "pending"]

    print(f"\n=== アフィリエイトプログラム状況 ===")
    print(f"\n承認済み ({len(active)}件):")
    for k, v in active:
        print(f"  ✅ {k}: {v.get('note', '')}")

    print(f"\n提携申請中 ({len(pending)}件):")
    for k, v in pending:
        print(f"  ⏳ {k}: {v.get('note', '')}")
        print(f"     現在のURL: {v.get('url', '')[:60]}")


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args or args[0] == "--status":
        show_status()
    elif args[0] == "--pending":
        data = load()
        pending = [(k, v) for k, v in data.items() if not k.startswith("_") and v.get("status") == "pending"]
        print(f"提携申請中: {len(pending)}件")
        for k, v in pending:
            print(f"  {k}")
    elif len(args) == 2:
        update_url(args[0], args[1])
    else:
        print(__doc__)
