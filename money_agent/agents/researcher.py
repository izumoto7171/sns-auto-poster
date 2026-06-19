"""
リサーチャーエージェント
CEOの戦略に基づき、今日狙うべきキーワードを選定する
"""
import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

# ── カテゴリ別ターゲット読者ペルソナ ──────────────────────────────
# ペルソナが具体的なほど懸念点抽出の精度が上がり、CVRが向上する
READER_PERSONAS = {
    "ai_saas": (
        "35〜50歳の中小企業経営者・管理職。ITは普通程度に使えるが最新AIツールには疎い。"
        "月額課金サービスへの慎重さがあり、社内展開のコスト・手間を心配している。"
        "「本当に自分の会社で使えるのか」「投資対効果が出るのか」を最も気にしている。"
    ),
    "dx_tools": (
        "30〜55歳の個人事業主または従業員5〜30名規模の中小企業経営者。"
        "今まで紙・Excel・メールで業務をこなしてきた。ITツールの移行コストや"
        "スタッフへの浸透を心配している。税理士・会計士との連携方法も不安要素。"
        "「うちの規模でコストに見合うのか」「解約できるのか」を強く気にしている。"
    ),
    "investment_savings": (
        "20〜40代の会社員または主婦。投資経験ゼロ〜1年程度。"
        "元本割れのリスクを最も怖れており、詐欺・悪質商品を見分けられるか不安。"
        "「難しそう」「お金が戻ってこなかったらどうしよう」という感情的ハードルが高い。"
        "制度の複雑さ（NISA・iDeCo・確定拠出）に混乱している。"
    ),
    "side_hustle": (
        "20〜40代の会社員・主婦・学生。副業初心者。月1〜5万円を目標にしている。"
        "「本当に稼げるのか」「詐欺じゃないか」「会社にバレないか」を最も気にしている。"
        "時間的余裕が少なく、スマホ中心で動くことを好む。最初の1件が取れるかどうかが壁。"
    ),
    "ai_tools": (
        "20〜45歳の学生・フリーランス・副業ワーカー。AIツールに興味はあるが"
        "英語UIや複雑な設定を敬遠する傾向がある。無料プランの制限に引っかかって"
        "有料移行を迷っている。「自分のスキルレベルで使いこなせるか」が最大の懸念。"
    ),
    "productivity": (
        "25〜45歳のビジネスパーソン。残業削減・効率化に意欲的だが、"
        "新ツール導入に上司・チームを説得するハードルを感じている。"
        "「既存ツールとの連携」「学習コスト」「チーム全員が使えるか」を心配している。"
    ),
}


def _load_used_keywords() -> list:
    f = BASE_DIR / "data" / "used_keywords.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def run(state: dict, slot: int = 0) -> dict:
    """
    リサーチャー実行
    slot: 0=メイン記事, 1=サブ記事A, 2=サブ記事B

    Returns: {"keyword": ..., "category": ..., "affiliates": [...], "reader_concerns": [...], "persona": ...}
    """
    print(f"  [Researcher-{slot}] キーワード選定中...")

    from money_agent.keywords_db import get_next_keyword, get_affiliates_for_category

    analyst_report = state.get("analyst_report", {})
    top_categories = analyst_report.get("top_categories", [])

    used_keywords = _load_used_keywords()

    # スロットごとに異なるカテゴリを優先
    preferred_category = None
    if top_categories:
        idx = slot % len(top_categories)
        preferred_category = top_categories[idx]

    # パイロットモード: state に pilot_mode=True が設定されている間は低競合KWを優先
    pilot_mode = state.get("pilot_mode", False)

    kw_data = get_next_keyword(
        used_keywords=used_keywords,
        preferred_category=preferred_category,
        pilot_mode=pilot_mode,
    )

    affiliates = get_affiliates_for_category(kw_data["category"])

    # ペルソナ取得（懸念点抽出の精度向上に使用）
    persona = READER_PERSONAS.get(kw_data["category"], "")

    # GEO: ペルソナを考慮した「最後の迷い（懸念点）」を抽出
    from money_agent.geo_enhancer import extract_reader_concerns
    reader_concerns = _extract_concerns_with_persona(
        kw_data["keyword"], kw_data["category"], persona
    )

    pilot_tag = " [PILOT]" if kw_data.get("is_pilot") else ""
    print(f"  [Researcher-{slot}]{pilot_tag} 「{kw_data['keyword']}」(カテゴリ: {kw_data['category']})")
    print(f"     懸念点: {reader_concerns[0][:40] if reader_concerns else 'なし'}...")

    return {
        "slot": slot,
        "keyword": kw_data["keyword"],
        "category": kw_data["category"],
        "intent": kw_data.get("intent", ""),
        "competition": kw_data.get("competition", "mid"),
        "is_pilot": kw_data.get("is_pilot", False),
        "affiliates": affiliates,
        "reader_concerns": reader_concerns,
        "persona": persona,
    }


def _extract_concerns_with_persona(keyword: str, category: str, persona: str) -> "list[str]":
    """
    ペルソナを system prompt に組み込んで懸念点を抽出する。
    汎用版の extract_reader_concerns より精度が高い。
    """
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key or not persona:
        from money_agent.geo_enhancer import extract_reader_concerns
        return extract_reader_concerns(keyword, category)

    try:
        from google import genai
        client = genai.Client(api_key=api_key)

        prompt = f"""あなたは以下のペルソナに完全になりきってください。

【ペルソナ】
{persona}

このペルソナが「{keyword}」を検索し、サービスへの登録・購入を検討している段階で感じる
「最後の迷い・懸念点」を3つ挙げてください。

条件:
- このペルソナの語彙・感情・生活状況に基づいた、リアルな本音であること
- 「本当に〜なのか」「〜したらどうなる」という疑問文の形で表現すること
- 抽象的な「コスパが心配」ではなく「月○円払い続けてXヶ月で元が取れるのか」のように具体的に
- JSONの配列のみ返すこと（コードブロック不要）

例（dx_toolsカテゴリの場合）:
["うちのスタッフはITが苦手なので、導入してもちゃんと使いこなせるか不安",
 "今の税理士とデータをどうやってやりとりすればいいのかわからない",
 "30日無料と言っても、解約の手続きが面倒くさいのでは"]"""

        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        text = resp.text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        concerns = json.loads(text)
        if isinstance(concerns, list) and concerns:
            return concerns[:3]
    except Exception as e:
        print(f"  [Researcher] ペルソナ懸念点取得失敗（フォールバック）: {e}")

    from money_agent.geo_enhancer import extract_reader_concerns
    return extract_reader_concerns(keyword, category)
