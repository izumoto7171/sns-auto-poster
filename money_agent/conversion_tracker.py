"""
成約追跡 — A8成約データと記事の紐付け

【機能】
1. A8のa8sid → 記事URLの逆引きマッピング構築
2. a8_report_collector.py の成約データを記事単位でSupabaseに記録
3. カテゴリ別の実績CVRを算出 → data/actual_cvr.json に出力
4. data_analyst.py が実績CVRを動的に読み込んで使用

【実行】
  python3 money_agent/conversion_tracker.py update    # 成約データ紐付け更新
  python3 money_agent/conversion_tracker.py cvr       # 実績CVR算出・出力
  python3 money_agent/conversion_tracker.py report    # 記事別成約レポート
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path(__file__).parent
ROOT_DIR = BASE_DIR.parent
sys.path.insert(0, str(ROOT_DIR))

REPORT_FILE = BASE_DIR / "data" / "a8_report.json"
CVR_FILE = BASE_DIR / "data" / "actual_cvr.json"
ARTICLE_MAP_FILE = BASE_DIR / "data" / "article_sid_map.json"


# ============================================================
# a8sid → 記事のマッピング管理
# ============================================================

def load_sid_map() -> dict:
    """a8sid → 記事情報のマッピングを読み込み"""
    if ARTICLE_MAP_FILE.exists():
        return json.loads(ARTICLE_MAP_FILE.read_text(encoding="utf-8"))
    return {}


def save_sid_map(mapping: dict):
    ARTICLE_MAP_FILE.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def register_article(
    a8_sid: str,
    article_url: str,
    keyword: str,
    category: str,
    title: str = "",
):
    """記事投稿時にa8sid→記事の紐付けを登録"""
    mapping = load_sid_map()
    mapping[a8_sid] = {
        "article_url": article_url,
        "keyword": keyword,
        "category": category,
        "title": title,
        "registered_at": datetime.now().isoformat(),
    }
    save_sid_map(mapping)


def build_sid_from_keyword(keyword: str, platform: str = "htn") -> str:
    """キーワードからa8sidを生成（tracking.pyの逆引き用）"""
    import hashlib
    kw_hash = hashlib.md5(keyword.encode()).hexdigest()[:8]
    date = datetime.now().strftime("%Y%m%d")
    return f"{platform}_{date}_{kw_hash}"


# ============================================================
# 成約データの紐付け
# ============================================================

def update_conversions():
    """A8レポートの成約データを記事単位で紐付け"""
    if not REPORT_FILE.exists():
        print("[ConversionTracker] A8レポートなし。a8_report_collector.py collect を先に実行してください")
        return

    report = json.loads(REPORT_FILE.read_text(encoding="utf-8"))
    sid_map = load_sid_map()

    # Supabase に記録を試行
    try:
        from db_client import db
        has_db = True
    except Exception:
        has_db = False

    conversions_by_article = defaultdict(lambda: {"conversions": 0, "revenue": 0})

    for month, m_data in report.get("monthly", {}).items():
        for prog in m_data.get("programs", []):
            program_name = prog.get("program", "")
            revenue = prog.get("revenue", 0)
            conversions = prog.get("conversions", 0)

            # a8sidベースのマッチング
            matched_articles = []
            for sid, article_info in sid_map.items():
                # プログラム名とカテゴリで照合（a8sidの日付とmonthが一致するか）
                if month in sid:
                    matched_articles.append(article_info)

            # マッチしない場合はキーワードベースでfuzzyマッチ
            if not matched_articles:
                for sid, article_info in sid_map.items():
                    title = article_info.get("title", "").lower()
                    kw = article_info.get("keyword", "").lower()
                    prog_lower = program_name.lower()
                    if any(word in title or word in kw for word in prog_lower.split()[:2] if len(word) > 2):
                        matched_articles.append(article_info)

            # 成約を記事に配分
            if matched_articles:
                per_article_rev = revenue // len(matched_articles)
                per_article_conv = max(1, conversions // len(matched_articles))
                for article in matched_articles:
                    key = article.get("article_url", article.get("keyword", "unknown"))
                    conversions_by_article[key]["conversions"] += per_article_conv
                    conversions_by_article[key]["revenue"] += per_article_rev
                    conversions_by_article[key]["category"] = article.get("category", "")
                    conversions_by_article[key]["keyword"] = article.get("keyword", "")
                    conversions_by_article[key]["month"] = month

    # Supabaseに保存
    if has_db and conversions_by_article:
        for url, data in conversions_by_article.items():
            try:
                db._get_supabase().table("article_conversions").upsert({
                    "article_url": url,
                    "keyword": data.get("keyword", ""),
                    "category": data.get("category", ""),
                    "conversions": data["conversions"],
                    "revenue": data["revenue"],
                    "month": data.get("month", ""),
                }).execute()
            except Exception as e:
                print(f"  [ConversionTracker] DB保存エラー: {e}")

    print(f"[ConversionTracker] {len(conversions_by_article)}件の記事に成約データを紐付け")
    return dict(conversions_by_article)


# ============================================================
# 実績CVR算出
# ============================================================

def calculate_actual_cvr():
    """カテゴリ別の実績CVRを算出してJSON出力"""
    if not REPORT_FILE.exists():
        print("[ConversionTracker] A8レポートなし")
        return {}

    report = json.loads(REPORT_FILE.read_text(encoding="utf-8"))
    sid_map = load_sid_map()

    # カテゴリ別の成約数・記事数を集計
    category_conversions = defaultdict(int)
    category_revenue = defaultdict(int)
    category_articles = defaultdict(int)

    # sid_mapからカテゴリ別記事数をカウント
    for sid, info in sid_map.items():
        cat = info.get("category", "unknown")
        category_articles[cat] += 1

    # レポートから成約データを集計
    for month, m_data in report.get("monthly", {}).items():
        for prog in m_data.get("programs", []):
            # プログラムのカテゴリを推定（sid_mapからマッチ）
            program_name = prog.get("program", "")
            matched_cat = _infer_category_from_program(program_name, sid_map)
            category_conversions[matched_cat] += prog.get("conversions", 0)
            category_revenue[matched_cat] += prog.get("revenue", 0)

    # CVR算出（成約数 / 記事数）
    actual_cvr = {}
    for cat in set(list(category_conversions.keys()) + list(category_articles.keys())):
        articles = category_articles.get(cat, 1)
        conversions = category_conversions.get(cat, 0)
        revenue = category_revenue.get(cat, 0)
        cvr = conversions / max(articles, 1)
        actual_cvr[cat] = {
            "cvr": round(cvr, 4),
            "cvr_coefficient": round(max(cvr * 100, 0.5), 2),
            "total_conversions": conversions,
            "total_revenue": revenue,
            "total_articles": articles,
            "updated_at": datetime.now().isoformat(),
        }

    # data_analyst.pyが読み込む形式で保存
    cvr_output = {
        "_updated": datetime.now().isoformat(),
        "_source": "conversion_tracker",
        "categories": actual_cvr,
    }
    CVR_FILE.write_text(
        json.dumps(cvr_output, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"[ConversionTracker] 実績CVRを算出 → {CVR_FILE}")
    for cat, data in sorted(actual_cvr.items(), key=lambda x: x[1]["total_revenue"], reverse=True):
        print(f"  {cat:25s} CVR={data['cvr']:.4f} / 成約{data['total_conversions']}件 / 収益¥{data['total_revenue']:,}")

    return actual_cvr


def _infer_category_from_program(program_name: str, sid_map: dict) -> str:
    """プログラム名からカテゴリを推定"""
    prog_lower = program_name.lower()

    # キーワードベースの推定
    category_keywords = {
        "investment_savings": ["証券", "nisa", "ideco", "投資", "口座"],
        "dx_tools": ["freee", "マネーフォワード", "chatwork", "会計", "クラウド"],
        "ai_tools": ["chatgpt", "ai", "notion", "canva"],
        "ai_saas": ["chatgpt", "ai", "notion", "canva"],
        "side_hustle": ["副業", "クラウドワークス", "ランサーズ"],
        "savings_lifestyle": ["楽天", "カード", "格安sim", "電気"],
        "high_value": ["転職", "プログラミング", "スクール", "fx"],
    }

    for cat, keywords in category_keywords.items():
        if any(kw in prog_lower for kw in keywords):
            return cat

    # sid_mapからマッチするカテゴリを探す
    for sid, info in sid_map.items():
        title = info.get("title", "").lower()
        if any(word in title for word in prog_lower.split()[:2] if len(word) > 2):
            return info.get("category", "unknown")

    return "unknown"


# ============================================================
# レポート表示
# ============================================================

def print_article_report():
    """記事別の成約レポートを表示"""
    conversions = update_conversions()
    if not conversions:
        print("成約データなし")
        return

    print("\n" + "=" * 60)
    print("記事別 成約レポート")
    print("=" * 60)

    sorted_articles = sorted(
        conversions.items(),
        key=lambda x: x[1].get("revenue", 0),
        reverse=True,
    )

    for url, data in sorted_articles[:20]:
        print(f"  {url[:50]:50s}")
        print(f"    カテゴリ: {data.get('category', '?')} / 成約: {data.get('conversions', 0)}件 / 収益: ¥{data.get('revenue', 0):,}")

    print("=" * 60)


# ============================================================
# メイン
# ============================================================

if __name__ == "__main__":
    args = sys.argv[1:]
    if "cvr" in args:
        calculate_actual_cvr()
    elif "report" in args:
        print_article_report()
    else:
        update_conversions()
        calculate_actual_cvr()
