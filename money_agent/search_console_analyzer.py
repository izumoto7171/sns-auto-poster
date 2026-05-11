"""
Google Search Console / Analytics データ分析
CSVをアップロードするだけで、キーワード・流入・離脱ポイントを自動分析する

【使い方】
1. Google Search Console → パフォーマンス → エクスポート → CSV ダウンロード
2. このスクリプトと同じフォルダの search_console/ に配置
3. python3 money_agent/search_console_analyzer.py

【自動分析サイクル】
Analyst エージェントが毎回実行時に search_console_analysis.json を参照し
キーワード戦略に反映する。
"""
import csv
import json
import os
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent
SC_DIR = BASE_DIR / "search_console"
ANALYSIS_FILE = BASE_DIR / "data" / "search_console_analysis.json"

SC_DIR.mkdir(exist_ok=True)

# Search Console CSVのカラム名（日本語/英語どちらにも対応）
COLUMN_ALIASES = {
    "query":       ["クエリ", "Query", "query", "検索クエリ"],
    "clicks":      ["クリック数", "Clicks", "clicks"],
    "impressions": ["表示回数", "Impressions", "impressions"],
    "ctr":         ["CTR", "ctr", "クリック率"],
    "position":    ["掲載順位", "Position", "position", "平均掲載順位"],
}


def _detect_column(header: list, field: str) -> int:
    """ヘッダーからカラムのインデックスを返す（-1 = 見つからない）"""
    aliases = COLUMN_ALIASES.get(field, [])
    for alias in aliases:
        if alias in header:
            return header.index(alias)
    return -1


def _parse_ctr(value: str) -> float:
    """CTRの文字列を float に変換（例: "4.17%" → 0.0417）"""
    value = value.strip().replace("%", "")
    try:
        f = float(value)
        return f / 100 if f > 1 else f  # % 表記か小数か自動判定
    except ValueError:
        return 0.0


def analyze_csv(csv_path) -> dict:
    """
    Search Console CSVを解析してインサイトを返す

    Returns:
        {
          "total_queries": int,
          "total_clicks": int,
          "total_impressions": int,
          "avg_ctr": float,
          "avg_position": float,
          "top_queries": [...],         # クリック数上位10
          "low_position_queries": [...], # 掲載順位11〜20位（改善余地あり）
          "high_impression_low_ctr": [...], # 表示多いがCTR低い（タイトル改善候補）
          "recommendations": [...],
          "analyzed_at": str,
        }
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSVファイルが見つかりません: {csv_path}")

    rows = []
    with open(csv_path, encoding="utf-8-sig") as f:  # BOM付きUTF-8対応
        reader = csv.reader(f)
        header = next(reader)
        header = [h.strip() for h in header]

        idx = {field: _detect_column(header, field) for field in COLUMN_ALIASES}

        for row in reader:
            if not row:
                continue
            try:
                entry = {
                    "query":       row[idx["query"]]       if idx["query"] >= 0       else "",
                    "clicks":      int(row[idx["clicks"]])        if idx["clicks"] >= 0      else 0,
                    "impressions": int(row[idx["impressions"]])    if idx["impressions"] >= 0 else 0,
                    "ctr":         _parse_ctr(row[idx["ctr"]])     if idx["ctr"] >= 0         else 0.0,
                    "position":    float(row[idx["position"]].replace(",", ".")) if idx["position"] >= 0 else 99.0,
                }
                if entry["query"]:
                    rows.append(entry)
            except (ValueError, IndexError):
                continue

    if not rows:
        return {"error": "データが空です", "analyzed_at": datetime.now().isoformat()}

    total_clicks = sum(r["clicks"] for r in rows)
    total_impressions = sum(r["impressions"] for r in rows)
    avg_ctr = (total_clicks / total_impressions) if total_impressions > 0 else 0.0
    avg_position = sum(r["position"] for r in rows) / len(rows)

    # クリック数上位10
    top_queries = sorted(rows, key=lambda r: r["clicks"], reverse=True)[:10]

    # 掲載順位11〜20（SEO改善余地あり = 2ページ目）
    low_position = [r for r in rows if 11 <= r["position"] <= 20]
    low_position_sorted = sorted(low_position, key=lambda r: r["impressions"], reverse=True)[:10]

    # 表示回数が多いのにCTRが低い（タイトル・メタ改善候補）
    median_ctr = sorted(r["ctr"] for r in rows)[len(rows) // 2] if rows else 0
    hi_imp_lo_ctr = [
        r for r in rows
        if r["impressions"] >= 50 and r["ctr"] < median_ctr * 0.7
    ]
    hi_imp_lo_ctr_sorted = sorted(hi_imp_lo_ctr, key=lambda r: r["impressions"], reverse=True)[:10]

    # 改善提案
    recommendations = []
    if low_position_sorted:
        recs = [r["query"] for r in low_position_sorted[:3]]
        recommendations.append(
            f"2ページ目（11〜20位）にいるキーワードを強化してください: {recs}"
        )
    if hi_imp_lo_ctr_sorted:
        recs = [r["query"] for r in hi_imp_lo_ctr_sorted[:3]]
        recommendations.append(
            f"表示されているのにクリックされないキーワードはタイトルを改善してください: {recs}"
        )
    if avg_position > 15:
        recommendations.append(
            "全体的に掲載順位が低いです。内部リンク強化・記事のリライトを検討してください。"
        )
    if avg_ctr < 0.02:
        recommendations.append(
            "CTRが低いです。タイトルに数字・【】・疑問形を追加してクリック率を改善しましょう。"
        )

    result = {
        "source_file": csv_path.name,
        "total_queries": len(rows),
        "total_clicks": total_clicks,
        "total_impressions": total_impressions,
        "avg_ctr": round(avg_ctr, 4),
        "avg_position": round(avg_position, 2),
        "top_queries": [
            {"query": r["query"], "clicks": r["clicks"], "impressions": r["impressions"],
             "ctr": round(r["ctr"], 4), "position": round(r["position"], 1)}
            for r in top_queries
        ],
        "low_position_queries": [
            {"query": r["query"], "impressions": r["impressions"], "position": round(r["position"], 1)}
            for r in low_position_sorted
        ],
        "high_impression_low_ctr": [
            {"query": r["query"], "impressions": r["impressions"], "ctr": round(r["ctr"], 4)}
            for r in hi_imp_lo_ctr_sorted
        ],
        "recommendations": recommendations,
        "analyzed_at": datetime.now().isoformat(),
    }

    return result


def load_latest_csv():
    """search_console/ 内の最新CSVを返す"""
    csvs = sorted(SC_DIR.glob("*.csv"), key=lambda f: f.stat().st_mtime, reverse=True)
    return csvs[0] if csvs else None


def run(state: dict = None) -> dict:
    """
    Analyst エージェントから呼び出されるエントリポイント
    最新CSVを自動検出して分析し、search_console_analysis.json に保存
    """
    print("  🔍 [SearchConsole] CSVデータ分析中...")

    csv_path = load_latest_csv()
    if not csv_path:
        print(f"  ⚠️ [SearchConsole] {SC_DIR} にCSVがありません。")
        print(f"     → Search Console → パフォーマンス → エクスポート → CSVを {SC_DIR}/ に配置してください。")
        # 既存の分析結果があればそれを返す
        if ANALYSIS_FILE.exists():
            try:
                return json.loads(ANALYSIS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"status": "no_data", "message": "CSVファイルが見つかりません"}

    try:
        result = analyze_csv(csv_path)
        ANALYSIS_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"  ✅ [SearchConsole] 分析完了: {result['total_queries']}クエリ / "
              f"クリック合計: {result['total_clicks']} / 平均順位: {result['avg_position']}")
        if result.get("recommendations"):
            for rec in result["recommendations"]:
                print(f"     💡 {rec[:80]}")

        return result
    except Exception as e:
        print(f"  ❌ [SearchConsole] 分析失敗: {e}")
        return {"status": "error", "error": str(e)}


def generate_sample_csv():
    """
    動作確認用のサンプルCSVを生成
    実際のSearch ConsoleデータはGSCからエクスポートしてください
    """
    sample_path = SC_DIR / "sample_search_console.csv"
    sample_data = [
        ["クエリ", "クリック数", "表示回数", "CTR", "掲載順位"],
        ["freee 中小企業 使い方", "45", "1200", "3.75%", "6.2"],
        ["マネーフォワード クラウド 比較", "23", "890", "2.58%", "8.5"],
        ["Chatwork 導入 メリット", "18", "650", "2.77%", "9.1"],
        ["バックオフィス 効率化 ツール", "12", "2100", "0.57%", "14.3"],
        ["クラウド会計 中小企業", "8", "1500", "0.53%", "16.8"],
        ["DX ツール おすすめ 2026", "6", "980", "0.61%", "18.2"],
        ["freee マネーフォワード どっち", "31", "420", "7.38%", "4.1"],
        ["中小企業 DX 始め方", "3", "750", "0.40%", "22.5"],
        ["業務効率化 無料 ツール", "2", "580", "0.34%", "25.1"],
        ["freee 使い方 初心者", "19", "340", "5.59%", "5.3"],
    ]
    with open(sample_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(sample_data)
    print(f"サンプルCSV生成: {sample_path}")
    return sample_path


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "sample":
        # サンプルCSVを生成して分析
        path = generate_sample_csv()
        result = analyze_csv(path)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        result = run()
        print(json.dumps(result, ensure_ascii=False, indent=2))
