"""
Analyst — 投稿データを分析し、次のActionPlanを決定する意思決定エンジン

【出力: ActionPlan】
  {
    "primary_action": "write_new" | "rewrite_existing" | "change_genre" | "market_research" | "rest",
    "article_count": 3,
    "target_genre": "AIツール・SaaS",
    "target_keywords": ["キーワード1", "キーワード2"],
    "rewrite_targets": [...],      # DataAnalystから受け取ったリライト対象
    "skip_genres": [...],          # DataAnalystが避けるべきと判定したジャンル
    "reasoning": "判断の根拠（1〜2文）",
    "today_strategy": "今日の記事戦略（1文）",
    "title_tips": "タイトルのコツ（1文）",
    "cta_tips": "CTAのコツ（1文）"
  }

【自律判断ロジック】
  1. 今日の記事数がゼロ → write_new
  2. リライト候補が HIGH×3件以上 → rewrite_existing を優先
  3. 連続3回以上ゼロ収益 → change_genre
  4. 市場データが7日以上古い → market_research
  5. 上記いずれでもない → Gemini が状況を読んで決定
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR.parent))
from db_client import db

sys.path.insert(0, str(BASE_DIR))
from gemini_client import generate as gemini_generate, strip_code_block

# ── デフォルト ActionPlan ──────────────────────────────────────
_DEFAULT_PLAN: dict = {
    "primary_action": "write_new",
    "article_count": 3,
    "target_genre": "AIツール・SaaS",
    "target_keywords": [],
    "rewrite_targets": [],
    "skip_genres": [],
    "reasoning": "データなし → デフォルト戦略で記事生成",
    "today_strategy": "投稿数の少ないカテゴリを優先して記事を量産する",
    "title_tips": "数字・具体性・疑問形を組み合わせてクリック率を上げる",
    "cta_tips": "記事末尾に「今すぐ申し込む」ボタンを設置する",
}


# ── データ収集 ────────────────────────────────────────────────

def _load_post_logs() -> list[dict]:
    """全プラットフォームの投稿ログを DB から収集"""
    try:
        return db.get_posts(limit=300)
    except Exception as e:
        print(f"  [Analyst] 投稿ログDB読み込み失敗: {e}")
        return []


def _load_revenue_data() -> list[dict]:
    """収益・分析履歴を DB から読み込み"""
    try:
        return db.get_analytics_history(limit=100)
    except Exception as e:
        print(f"  [Analyst] 収益データDB読み込み失敗: {e}")
        return []


def _load_search_console_data() -> dict:
    """Search Console 分析結果を読み込む"""
    try:
        from money_agent.search_console_analyzer import run as sc_run
        return sc_run()
    except Exception:
        pass
    sc_file = BASE_DIR / "data" / "search_console_analysis.json"
    if sc_file.exists():
        try:
            return json.loads(sc_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


# ── ルールベース事前判定 ──────────────────────────────────────

def _rule_based_action(
    posts: list[dict],
    state: dict,
    data_analysis: dict,
) -> str | None:
    """
    明らかなケースをルールで判定し primary_action を返す。
    判断できない場合は None を返して Gemini に委任。
    """
    today = datetime.now().date()

    # 今日の記事数を確認
    today_articles = 0
    for p in posts:
        created = p.get("created_at", p.get("datetime", ""))
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00")).date()
            if dt == today:
                today_articles += 1
        except Exception:
            pass

    # 今日ゼロ → write_new 最優先
    if today_articles == 0 and state.get("today_articles", 0) == 0:
        return "write_new"

    # リライト候補が HIGH×3件以上 → rewrite を優先
    high_priority_rewrites = [
        r for r in data_analysis.get("rewrite_queue", [])
        if r.get("rewrite_priority") == "HIGH"
    ]
    if len(high_priority_rewrites) >= 3:
        return "rewrite_existing"

    # 連続ゼロ収益（daily_log の直近5件で分配件数 = 0）
    daily_log = state.get("daily_log", [])
    if len(daily_log) >= 5:
        recent_dist = [sum(e.get("dist_success", [0])) for e in daily_log[-5:]]
        if all(d == 0 for d in recent_dist):
            return "change_genre"

    # 市場データが7日以上古い → market_research
    last_market = state.get("market_research", {}).get("generated_at", "")
    if last_market:
        try:
            last_dt = datetime.fromisoformat(last_market)
            if (datetime.now() - last_dt).days >= 7:
                return "market_research"
        except Exception:
            pass
    elif not state.get("market_research"):
        return "market_research"

    return None  # Gemini に委任


# ── Gemini 分析 ───────────────────────────────────────────────

def _gemini_action_plan(
    posts: list[dict],
    revenue_data: list[dict],
    sc_data: dict,
    state: dict,
    data_analysis: dict,
) -> dict:
    """Gemini に状況を渡して ActionPlan を生成させる"""

    # カテゴリ別投稿数（直近100件）
    category_counts: dict[str, int] = {}
    for p in posts[-100:]:
        cat = p.get("post_type", p.get("label", "unknown"))
        category_counts[cat] = category_counts.get(cat, 0) + 1

    # 収益サマリー
    total_revenue = sum(r.get("estimated_revenue", 0) for r in revenue_data)
    recent_revenue = [
        {"label": r.get("label", ""), "revenue": r.get("estimated_revenue", 0)}
        for r in revenue_data[-10:]
    ]

    # DataAnalyst の結果から要約
    rewrite_count = len([
        r for r in data_analysis.get("rewrite_queue", [])
        if r.get("rewrite_priority") == "HIGH"
    ])
    best_genre = data_analysis.get("best_genre", "")
    skip_genres = data_analysis.get("skip_genres", [])

    sc_summary = {
        "avg_position": sc_data.get("avg_position"),
        "low_position_queries": [q.get("query") for q in sc_data.get("low_position_queries", [])[:5]],
        "high_imp_low_ctr": [q.get("query") for q in sc_data.get("high_impression_low_ctr", [])[:3]],
        "recommendations": sc_data.get("recommendations", [])[:3],
    }

    daily_log_summary = state.get("daily_log", [])[-5:]
    used_keywords = state.get("used_keywords", [])[-30:]

    prompt = f"""あなたはアフィリエイトブログの自律的な意思決定AIです。
以下のデータを分析し、**今すぐ取るべき最善のアクション**を決定してください。

【投稿カテゴリ分布（直近100件）】
{json.dumps(category_counts, ensure_ascii=False)}

【DataAnalyst の分析結果】
- リライト高優先記事数: {rewrite_count}件
- 最も伸ばすべきジャンル: {best_genre}
- 避けるべきジャンル: {skip_genres}
- リライトキュー: {json.dumps(data_analysis.get('rewrite_queue', [])[:3], ensure_ascii=False)}

【収益データ（直近10件）】
{json.dumps(recent_revenue, ensure_ascii=False)}
累計推定収益: {total_revenue}円

【Search Console】
{json.dumps(sc_summary, ensure_ascii=False)}

【直近5回の実行ログ】
{json.dumps(daily_log_summary, ensure_ascii=False)}

【使用済みキーワード（直近30件・重複避ける）】
{used_keywords}

【判断基準】
- write_new: 今日の記事数が目標未達、または新規ジャンルで攻めるべき
- rewrite_existing: HIGH優先リライト3件以上、またはSC で2ページ目記事多数
- change_genre: 連続してゼロ収益、または使用済みキーワードが枯渇
- market_research: 市場データが古い、またはジャンル変更後の再調査が必要

以下のJSON形式のみで返してください（コードブロック不要）:
{{
  "primary_action": "write_new" または "rewrite_existing" または "change_genre" または "market_research",
  "article_count": 3,
  "target_genre": "推奨ジャンル名",
  "target_keywords": ["キーワード1", "キーワード2", "キーワード3"],
  "skip_genres": ["避けるジャンル1"],
  "reasoning": "この判断を下した根拠（2〜3文）",
  "today_strategy": "今日の記事生成戦略（1文）",
  "title_tips": "クリック率を上げるタイトルのコツ（1文）",
  "cta_tips": "CV率を上げるCTAのコツ（1文）"
}}"""

    raw = gemini_generate(prompt, use_cache=False)
    if not raw:
        print("  [Analyst] Gemini応答なし → デフォルトプランを使用")
        return {}

    try:
        plan = json.loads(strip_code_block(raw))
        return plan
    except Exception as e:
        print(f"  [Analyst] JSONパース失敗: {e} → デフォルトプランを使用")
        return {}


# ── メイン ────────────────────────────────────────────────────

def run(state: dict, data_analysis: dict | None = None) -> dict:
    """
    Analyst 実行 → ActionPlan を返す

    Parameters
    ----------
    state         : CEO から渡された共有ステート
    data_analysis : DataAnalyst.run() の結果（先行実行済みであれば渡す）
    """
    print("  [Analyst] データ分析 → ActionPlan 生成中...")

    data_analysis = data_analysis or {}
    posts         = _load_post_logs()
    revenue_data  = _load_revenue_data()
    sc_data       = _load_search_console_data()

    # Search Console のリライト候補をログ出力
    sc_low = sc_data.get("low_position_queries", [])
    if sc_low:
        print(f"  [Analyst] GSC 2ページ目キーワード: {len(sc_low)}件（リライト候補）")

    # ── ルールベース事前判定 ──────────────────────────────────
    rule_action = _rule_based_action(posts, state, data_analysis)

    if rule_action:
        print(f"  [Analyst] ルール判定 → primary_action={rule_action}")
        plan = dict(_DEFAULT_PLAN)
        plan["primary_action"] = rule_action
        plan["rewrite_targets"] = data_analysis.get("rewrite_queue", [])
        plan["skip_genres"]     = data_analysis.get("skip_genres", [])
        plan["best_genre"]      = data_analysis.get("best_genre", "")
        plan["reasoning"]       = f"ルールベース判定: {rule_action}"
        # Gemini でタイトル/CTA ヒントだけ補完（軽量プロンプト）
        _enrich_hints(plan, sc_data)
        return plan

    # ── Gemini による総合判断 ─────────────────────────────────
    gemini_plan = _gemini_action_plan(posts, revenue_data, sc_data, state, data_analysis)

    if gemini_plan:
        # DataAnalyst の結果を上書きマージ
        gemini_plan.setdefault("rewrite_targets", data_analysis.get("rewrite_queue", []))
        if not gemini_plan.get("skip_genres"):
            gemini_plan["skip_genres"] = data_analysis.get("skip_genres", [])
        action = gemini_plan.get("primary_action", "write_new")
        genre  = gemini_plan.get("target_genre", "")
        print(f"  [Analyst] Gemini判断 → action={action} genre={genre}")
        print(f"  [Analyst] 根拠: {gemini_plan.get('reasoning', '')[:80]}")
        return gemini_plan

    # フォールバック
    fallback = dict(_DEFAULT_PLAN)
    fallback["rewrite_targets"] = data_analysis.get("rewrite_queue", [])
    fallback["skip_genres"]     = data_analysis.get("skip_genres", [])
    return fallback


def _enrich_hints(plan: dict, sc_data: dict) -> None:
    """
    ルールベース判定後に title_tips / cta_tips だけ Gemini で補完する（軽量）
    """
    sc_hi_ctr = [q.get("query", "") for q in sc_data.get("high_impression_low_ctr", [])[:3]]
    if not sc_hi_ctr:
        return

    prompt = f"""以下のキーワードは検索表示回数が多いのにクリック率が低いです。
キーワード: {sc_hi_ctr}
クリック率を上げるタイトルのコツを1文で返してください。コードブロック不要。"""

    result = gemini_generate(prompt, use_cache=True)
    if result:
        plan["title_tips"] = result.strip()
