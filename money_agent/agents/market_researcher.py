"""
市場調査エージェント
「今、どのジャンルの報酬単価が高く、競合が少ないか」を分析する
"""
import os
import json
from pathlib import Path
from google import genai

BASE_DIR = Path(__file__).parent.parent

# ── 既知のアフィリエイト報酬データ（A8.net / 各ASP）──────────────────
AFFILIATE_MARKET_DATA = {
    "証券口座": {
        "unit_price": 25000,   # 円/件（SBI証券, DMM証券等）
        "competition": 8,      # 競合度 1-10（高いほど激戦）
        "cvr_est": 0.3,        # 推定CVR %
        "trend": "stable",
    },
    "FX口座": {
        "unit_price": 20000,
        "competition": 9,
        "cvr_est": 0.2,
        "trend": "declining",
    },
    "クレジットカード": {
        "unit_price": 8000,
        "competition": 9,
        "cvr_est": 0.5,
        "trend": "stable",
    },
    "AIツール・SaaS": {
        "unit_price": 5000,
        "competition": 3,      # 2026年時点でまだ競合少ない
        "cvr_est": 1.2,
        "trend": "growing",
    },
    "副業・在宅ワーク": {
        "unit_price": 3000,
        "competition": 7,
        "cvr_est": 0.8,
        "trend": "stable",
    },
    "格安SIM": {
        "unit_price": 8000,
        "competition": 8,
        "cvr_est": 0.4,
        "trend": "stable",
    },
    "ウォーターサーバー": {
        "unit_price": 7000,
        "competition": 6,
        "cvr_est": 0.6,
        "trend": "stable",
    },
    "転職エージェント": {
        "unit_price": 30000,
        "competition": 9,
        "cvr_est": 0.15,
        "trend": "stable",
    },
    "DX・業務効率化ツール": {
        "unit_price": 8000,
        "competition": 3,      # 中小企業向けニッチ
        "cvr_est": 0.8,
        "trend": "growing",
    },
    "米国株・ETF投資": {
        "unit_price": 15000,
        "competition": 4,      # 証券より競合少
        "cvr_est": 0.5,
        "trend": "growing",
    },
    "プログラミングスクール": {
        "unit_price": 50000,
        "competition": 8,
        "cvr_est": 0.05,
        "trend": "stable",
    },
    "脱毛・美容": {
        "unit_price": 5000,
        "competition": 8,
        "cvr_est": 0.4,
        "trend": "stable",
    },
    "電力会社乗り換え": {
        "unit_price": 5000,
        "competition": 5,
        "cvr_est": 0.6,
        "trend": "growing",
    },
}


def _score_niche(data: dict) -> float:
    """
    ニッチスコア = 報酬単価 × CVR推定 / 競合度
    高いほど「稼ぎやすい」
    """
    revenue_potential = data["unit_price"] * data["cvr_est"] / 100
    competition_penalty = data["competition"] ** 1.5
    trend_bonus = {"growing": 1.3, "stable": 1.0, "declining": 0.7}[data["trend"]]
    return (revenue_potential / competition_penalty) * trend_bonus * 1000


def run(state: dict) -> dict:
    """
    市場調査エージェント実行
    Returns: 推奨ジャンルと理由
    """
    print("  🔬 [MarketResearcher] 市場調査中...")

    # スコアリング
    scored = []
    for genre, data in AFFILIATE_MARKET_DATA.items():
        score = _score_niche(data)
        scored.append({
            "genre": genre,
            "score": round(score, 2),
            "unit_price": data["unit_price"],
            "competition": data["competition"],
            "cvr_est": data["cvr_est"],
            "trend": data["trend"],
            "monthly_potential": int(data["unit_price"] * data["cvr_est"] / 100 * 1000),  # 月1000PV想定
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    top5 = scored[:5]

    # Gemini で深堀り分析
    api_key = os.environ.get("GEMINI_API_KEY", "")
    gemini_analysis = {}
    if api_key:
        try:
            client = genai.Client(api_key=api_key)
            prompt = f"""あなたはアフィリエイトマーケティングの市場調査専門家です。
2026年現在の日本のアフィリエイト市場を分析してください。

スコアリング結果（上位5ジャンル）:
{json.dumps(top5, ensure_ascii=False, indent=2)}

以下をJSONのみで返してください（コードブロック不要）:
{{
  "best_genre": "最もおすすめのジャンル名",
  "reason": "選んだ理由（2-3文）",
  "target_keywords": ["具体的なキーワード例1", "キーワード例2", "キーワード例3", "キーワード例4", "キーワード例5"],
  "monthly_10man_strategy": "月10万円達成のための具体的な戦略（3-4文）",
  "quick_wins": ["今週すぐできること1", "今週すぐできること2", "今週すぐできること3"],
  "risk": "このジャンルの主なリスク（1文）"
}}"""

            resp = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
            )
            text = resp.text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            gemini_analysis = json.loads(text)
        except Exception as e:
            print(f"  ⚠️ [MarketResearcher] Gemini分析スキップ: {e}")

    result = {
        "top5_genres": top5,
        "recommended_genre": gemini_analysis.get("best_genre", top5[0]["genre"]),
        "reason": gemini_analysis.get("reason", "スコアが最も高いジャンル"),
        "target_keywords": gemini_analysis.get("target_keywords", []),
        "monthly_10man_strategy": gemini_analysis.get("monthly_10man_strategy", ""),
        "quick_wins": gemini_analysis.get("quick_wins", []),
        "risk": gemini_analysis.get("risk", ""),
        "scored_all": scored,
    }

    # 結果保存
    output_file = BASE_DIR / "market_research.json"
    output_file.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"  ✅ [MarketResearcher] 推奨ジャンル: 「{result['recommended_genre']}」")
    print(f"     理由: {result['reason'][:60]}...")
    return result
