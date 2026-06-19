"""
GitHub Actions 使用量監視スクリプト
月間使用量が上限に近づいたらsns-postの頻度を自動調整する。

実行:
  python3 scripts/actions_usage_monitor.py          # 使用量表示
  python3 scripts/actions_usage_monitor.py --auto   # 自動調整モード
"""
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
MONTHLY_FREE_LIMIT = 2000  # 無料枠（分）
WARNING_THRESHOLD = 0.75   # 75%で警告
DANGER_THRESHOLD = 0.90    # 90%で自動調整

REPO = "izumoto7171/sns-auto-poster"


def get_usage_minutes() -> dict:
    """GitHub APIから今月のActions使用量を取得"""
    try:
        result = subprocess.run(
            ["gh", "api", f"/repos/{REPO}/actions/cache/usage"],
            capture_output=True, text=True, timeout=30,
        )

        # billing APIはOrg向けなので、実行履歴から推定する
        result = subprocess.run(
            ["gh", "api", f"/repos/{REPO}/actions/runs",
             "--jq", '.workflow_runs[:100] | map(select(.created_at > "'
             + datetime.now().strftime("%Y-%m") + '")) | length'],
            capture_output=True, text=True, timeout=30,
        )

        # 直近の実行から使用量を推定
        runs_result = subprocess.run(
            ["gh", "api", f"/repos/{REPO}/actions/runs",
             "--paginate", "--jq",
             '.workflow_runs[] | select(.created_at > "' + datetime.now().strftime("%Y-%m") + '") '
             '| {name: .name, status: .status, conclusion: .conclusion, '
             'created: .created_at, updated: .updated_at}'],
            capture_output=True, text=True, timeout=60,
        )

        runs = []
        for line in runs_result.stdout.strip().split('\n'):
            if line.strip():
                try:
                    runs.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

        # ワークフロー別実行回数
        workflow_counts = {}
        for run in runs:
            name = run.get("name", "unknown")
            workflow_counts[name] = workflow_counts.get(name, 0) + 1

        # 推定使用量（ワークフロー別平均実行時間）
        avg_minutes = {
            "SNS Auto Post": 25,
            "Lifestyle Hack Auto Poster": 8,
            "Analytics & Click Update": 10,
            "Money Agent (アフィリエイト記事生成)": 35,
            "A8新着案件パイプライン": 20,
            "週次アフィリエイト案件リサーチ": 10,
        }

        total_estimated = 0
        breakdown = {}
        for name, count in workflow_counts.items():
            avg = avg_minutes.get(name, 15)
            minutes = count * avg
            breakdown[name] = {"runs": count, "avg_min": avg, "total_min": minutes}
            total_estimated += minutes

        return {
            "total_runs": len(runs),
            "estimated_minutes": total_estimated,
            "breakdown": breakdown,
            "month": datetime.now().strftime("%Y-%m"),
        }

    except Exception as e:
        print(f"使用量取得エラー: {e}")
        return {"total_runs": 0, "estimated_minutes": 0, "breakdown": {}, "month": ""}


def print_report(usage: dict):
    """使用量レポート表示"""
    total = usage["estimated_minutes"]
    pct = total / MONTHLY_FREE_LIMIT * 100

    print(f"\n{'='*50}")
    print(f"GitHub Actions 使用量レポート ({usage['month']})")
    print(f"{'='*50}")
    print(f"推定使用量: {total:,}分 / {MONTHLY_FREE_LIMIT:,}分 ({pct:.1f}%)")
    print(f"実行回数:   {usage['total_runs']}回")

    if usage["breakdown"]:
        print(f"\nワークフロー別:")
        for name, data in sorted(usage["breakdown"].items(), key=lambda x: -x[1]["total_min"]):
            print(f"  {name}: {data['runs']}回 x ~{data['avg_min']}分 = {data['total_min']}分")

    if pct >= DANGER_THRESHOLD * 100:
        print(f"\n[DANGER] 月間上限の{DANGER_THRESHOLD*100:.0f}%超過。自動調整が必要。")
    elif pct >= WARNING_THRESHOLD * 100:
        print(f"\n[WARNING] 月間上限の{WARNING_THRESHOLD*100:.0f}%に到達。")
    else:
        print(f"\n[OK] 使用量は問題なし。")


def estimate_remaining_days(usage: dict) -> int:
    """今月の残り日数で使える1日あたりの分数を計算"""
    now = datetime.now()
    import calendar
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    days_remaining = days_in_month - now.day
    if days_remaining <= 0:
        return 0
    remaining_minutes = MONTHLY_FREE_LIMIT - usage["estimated_minutes"]
    return max(0, int(remaining_minutes / days_remaining))


def suggest_adjustments(usage: dict) -> list:
    """使用量に応じた調整案を返す"""
    suggestions = []
    total = usage["estimated_minutes"]
    pct = total / MONTHLY_FREE_LIMIT

    if pct < WARNING_THRESHOLD:
        return suggestions

    # SNS Auto Postが最大の消費者なので、まずここを調整
    sns_data = usage["breakdown"].get("SNS Auto Post", {})
    if sns_data.get("runs", 0) > 60:  # 月60回以上 = 2回/日以上
        suggestions.append({
            "action": "sns-post頻度を4回→2回/日に削減",
            "savings": sns_data["total_min"] // 2,
            "priority": "high",
        })

    lifehack_data = usage["breakdown"].get("Lifestyle Hack Auto Poster", {})
    if lifehack_data.get("runs", 0) > 0:
        suggestions.append({
            "action": "lifehack-posterを1回/日に削減（現在2回）",
            "savings": lifehack_data["total_min"] // 2,
            "priority": "medium",
        })

    return suggestions


def main():
    auto_mode = "--auto" in sys.argv

    usage = get_usage_minutes()
    print_report(usage)

    daily_budget = estimate_remaining_days(usage)
    print(f"\n残り日数あたりの予算: {daily_budget}分/日")

    suggestions = suggest_adjustments(usage)
    if suggestions:
        print(f"\n調整案:")
        for s in suggestions:
            print(f"  [{s['priority']}] {s['action']} (節約: ~{s['savings']}分)")

    if auto_mode and suggestions:
        print("\n[auto] 自動調整は未実装（ワークフローの動的変更はGitHub APIでは不可）")
        print("  → 手動でcron式を変更するか、このスクリプトの結果を参考にしてください")


if __name__ == "__main__":
    main()
