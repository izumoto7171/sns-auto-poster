"""
A8.net 成果レポート自動集計

【機能】
1. Gmail IMAP でA8.netからの成果確認メールを取得・解析
2. 案件別・月別の収益をJSONに集計
3. CSVエクスポート（スプレッドシート向け）
4. コンソールにダッシュボード表示

【A8.netの成果メール形式】
 件名: "【A8.net】成果確認のお知らせ" または "A8.net 成果レポート"
 内容: プログラム名・成果件数・報酬額が記載

【実行方法】
  python3 money_agent/a8_report_collector.py collect   # メール収集・集計
  python3 money_agent/a8_report_collector.py dashboard # 集計済みデータを表示
  python3 money_agent/a8_report_collector.py csv       # CSVエクスポート
"""

import os
import sys
import json
import imaplib
import email
import re
import csv
from datetime import datetime
from pathlib import Path
from email.header import decode_header

# .env読み込み
def load_env():
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

load_env()

# ============================================================
# 定数
# ============================================================
REPORT_FILE = Path(__file__).parent / "data" / "a8_report.json"
SEEN_MAIL_FILE = Path(__file__).parent / "data" / "seen_a8_mails.json"

# Gmail IMAP設定（Google Workspaceまたはアプリパスワード必須）
IMAP_HOST = os.environ.get("IMAP_HOST", "imap.gmail.com")
IMAP_PORT = int(os.environ.get("IMAP_PORT", "993"))
IMAP_USER = os.environ.get("IMAP_USER", os.environ.get("X_EMAIL", ""))
IMAP_PASSWORD = os.environ.get("IMAP_PASSWORD", "")  # Gmailアプリパスワード

# A8.netからのメール送信元
A8_SENDERS = [
    "a8-info@a8.net",
    "mail@a8.net",
    "noreply@a8.net",
    "report@a8.net",
]


# ============================================================
# データ管理
# ============================================================
def load_report() -> dict:
    if REPORT_FILE.exists():
        return json.loads(REPORT_FILE.read_text(encoding="utf-8"))
    return {
        "_updated": "",
        "_total_revenue": 0,
        "_total_conversions": 0,
        "monthly": {},   # {"2026-03": {"total": 5000, "programs": [...]}}
        "programs": {},  # {"プログラム名": {"total_revenue": 0, "conversions": 0}}
    }

def save_report(data: dict):
    data["_updated"] = datetime.now().isoformat()
    REPORT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def load_seen_mails() -> set:
    if SEEN_MAIL_FILE.exists():
        return set(json.loads(SEEN_MAIL_FILE.read_text(encoding="utf-8")))
    return set()

def save_seen_mails(seen: set):
    SEEN_MAIL_FILE.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=2), encoding="utf-8")


# ============================================================
# メール解析
# ============================================================
def decode_mime_header(header: str) -> str:
    """MIMEエンコードされたメールヘッダをデコード"""
    parts = decode_header(header)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(str(part))
    return "".join(decoded)


def parse_a8_mail(body: str, subject: str):
    """
    A8.netの成果確認メールを解析して成果データを返す。
    メール形式が変わる場合はこの関数を更新する。
    """
    results = []

    # パターン1: 「プログラム名：〇〇 / 成果：N件 / 報酬：¥X,XXX」形式
    pattern1 = re.findall(
        r"プログラム[名]?[：:]\s*(.+?)\s*[/／\n].*?成果[数件]?[：:]\s*(\d+)\s*件.*?報酬[額]?[：:]\s*[¥￥]?([\d,]+)",
        body,
        re.DOTALL,
    )
    for match in pattern1:
        results.append({
            "program": match[0].strip()[:50],
            "conversions": int(match[1]),
            "revenue": int(match[2].replace(",", "")),
        })

    # パターン2: テーブル形式「プログラム名\t件数\t報酬」
    pattern2 = re.findall(
        r"([^\t\n]{3,30})\t(\d+)\t[¥￥]?([\d,]+)",
        body,
    )
    for match in pattern2:
        name = match[0].strip()
        if len(name) >= 3:
            results.append({
                "program": name[:50],
                "conversions": int(match[1]),
                "revenue": int(match[2].replace(",", "")),
            })

    # パターン3: 「今月の成果合計: ¥X,XXX」形式（合計のみ）
    if not results:
        total_match = re.search(r"合計[報酬]?[：:]\s*[¥￥]?([\d,]+)", body)
        if total_match:
            results.append({
                "program": "合計（内訳不明）",
                "conversions": 0,
                "revenue": int(total_match.group(1).replace(",", "")),
            })

    # 月を件名・本文から推定
    month_match = re.search(r"(\d{4})[年/\-](\d{1,2})[月/]", subject + body)
    month = f"{month_match.group(1)}-{int(month_match.group(2)):02d}" if month_match else datetime.now().strftime("%Y-%m")

    for r in results:
        r["month"] = month

    return results


def collect_from_imap():
    """Gmail IMAP でA8.net成果メールを収集"""
    if not IMAP_PASSWORD:
        print("[IMAP] IMAP_PASSWORD未設定。Gmailアプリパスワードが必要です。")
        print("  設定方法: Googleアカウント → セキュリティ → アプリパスワード")
        print("  取得したパスワードを .env の IMAP_PASSWORD= に設定してください")
        return []

    seen = load_seen_mails()
    all_results = []

    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(IMAP_USER, IMAP_PASSWORD)
        mail.select("INBOX")
        print(f"[IMAP] {IMAP_USER} にログイン成功")

        # A8.netからのメールを検索
        for sender in A8_SENDERS:
            _, msg_ids = mail.search(None, f'FROM "{sender}"')
            if not msg_ids[0]:
                continue

            for msg_id in msg_ids[0].split():
                msg_key = msg_id.decode()
                if msg_key in seen:
                    continue

                _, msg_data = mail.fetch(msg_id, "(RFC822)")
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)

                subject = decode_mime_header(msg.get("Subject", ""))

                # 件名フィルタ（成果関連のみ）
                if not any(kw in subject for kw in ["成果", "レポート", "報酬", "report"]):
                    seen.add(msg_key)
                    continue

                # 本文取得
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        ct = part.get_content_type()
                        if ct in ("text/plain", "text/html"):
                            payload = part.get_payload(decode=True)
                            charset = part.get_content_charset() or "utf-8"
                            body += payload.decode(charset, errors="replace")
                else:
                    payload = msg.get_payload(decode=True)
                    charset = msg.get_content_charset() or "utf-8"
                    body = payload.decode(charset, errors="replace")

                # HTMLタグ除去
                body = re.sub(r"<[^>]+>", "", body)

                results = parse_a8_mail(body, subject)
                if results:
                    print(f"  [IMAP] 成果メール解析: {subject[:50]} → {len(results)}件")
                    all_results.extend(results)

                seen.add(msg_key)

        mail.logout()
        save_seen_mails(seen)

    except imaplib.IMAP4.error as e:
        print(f"[IMAP] 接続エラー: {e}")
    except Exception as e:
        print(f"[IMAP] 予期せぬエラー: {e}")

    return all_results


# ============================================================
# 集計
# ============================================================
def aggregate_results(results: list[dict], report: dict) -> dict:
    """成果データをレポートに集計"""
    for r in results:
        month = r.get("month", datetime.now().strftime("%Y-%m"))
        program = r.get("program", "不明")
        revenue = r.get("revenue", 0)
        conversions = r.get("conversions", 0)

        # 月別集計
        if month not in report["monthly"]:
            report["monthly"][month] = {"total_revenue": 0, "total_conversions": 0, "programs": []}
        report["monthly"][month]["total_revenue"] += revenue
        report["monthly"][month]["total_conversions"] += conversions
        report["monthly"][month]["programs"].append({
            "program": program,
            "revenue": revenue,
            "conversions": conversions,
        })

        # プログラム別集計
        if program not in report["programs"]:
            report["programs"][program] = {"total_revenue": 0, "total_conversions": 0, "months": {}}
        report["programs"][program]["total_revenue"] += revenue
        report["programs"][program]["total_conversions"] += conversions
        report["programs"][program]["months"][month] = revenue

    # トータル更新
    report["_total_revenue"] = sum(v["total_revenue"] for v in report["monthly"].values())
    report["_total_conversions"] = sum(v["total_conversions"] for v in report["monthly"].values())
    return report


# ============================================================
# ダッシュボード表示
# ============================================================
def print_dashboard():
    report = load_report()

    print("\n" + "=" * 50)
    print("A8.net 収益ダッシュボード")
    print("=" * 50)
    print(f"最終更新: {report.get('_updated', '未収集')}")
    print(f"累計収益: ¥{report['_total_revenue']:,}")
    print(f"累計成果: {report['_total_conversions']}件")

    print("\n--- 月別収益 ---")
    for month in sorted(report["monthly"].keys(), reverse=True)[:6]:
        m = report["monthly"][month]
        bar = "█" * min(int(m["total_revenue"] / 1000), 30)
        print(f"  {month}: ¥{m['total_revenue']:,} ({m['total_conversions']}件) {bar}")

    print("\n--- プログラム別収益（上位10件） ---")
    sorted_programs = sorted(
        report["programs"].items(),
        key=lambda x: x[1]["total_revenue"],
        reverse=True,
    )[:10]
    for name, data in sorted_programs:
        print(f"  {name[:30]:30s} ¥{data['total_revenue']:,} ({data['total_conversions']}件)")

    # 月10万円進捗
    current_month = datetime.now().strftime("%Y-%m")
    current_revenue = report["monthly"].get(current_month, {}).get("total_revenue", 0)
    target = 100000
    progress = current_revenue / target * 100
    bar_len = int(progress / 5)
    print(f"\n--- 今月({current_month})の進捗 ---")
    print(f"  ¥{current_revenue:,} / ¥{target:,} ({progress:.1f}%)")
    print(f"  [{'█' * bar_len}{'░' * (20 - bar_len)}]")

    print("=" * 50)


def export_csv():
    """レポートをCSV出力"""
    report = load_report()
    csv_path = Path(__file__).parent / "a8_report.csv"

    rows = []
    for month, m_data in sorted(report["monthly"].items()):
        for prog in m_data.get("programs", []):
            rows.append({
                "月": month,
                "プログラム": prog["program"],
                "成果件数": prog["conversions"],
                "報酬額": prog["revenue"],
            })

    if not rows:
        print("集計データがありません。先に collect を実行してください。")
        return

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["月", "プログラム", "成果件数", "報酬額"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"CSVエクスポート完了: {csv_path}")


# ============================================================
# メイン
# ============================================================
def collect():
    print(f"\n=== A8レポート収集開始 {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")
    results = collect_from_imap()

    if results:
        report = load_report()
        report = aggregate_results(results, report)
        save_report(report)
        print(f"集計完了: {len(results)}件の成果データを保存")
    else:
        print("新しい成果データなし")

    print_dashboard()


if __name__ == "__main__":
    args = sys.argv[1:]
    if "dashboard" in args:
        print_dashboard()
    elif "csv" in args:
        export_csv()
    else:
        collect()
