"""
月10万円SEO記事生成エンジン v2
- Gemini全文生成による高品質記事（テンプレート穴埋め廃止）
- アフィリエイトリンクを文脈内に自然統合（CTAセクション廃止）
- GEO最適化（JSON-LD、結論ファースト）維持
- quality_mode=False で旧テンプレートモードにロールバック可能
"""

import os
import sys
import random
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from money_agent.keywords_db import get_affiliates_for_category, KEYWORD_CATEGORIES
from money_agent.geo_enhancer import (
    build_conclusion_first,
    build_data_comparison_table,
    build_concern_section,
    render_jsonld_block,
    build_article_jsonld,
    build_faq_jsonld,
)

# ============================================================
# 読者ペルソナ定義（カテゴリ別）
# ============================================================

READER_PERSONAS = {
    "ai_tools": {
        "who": "AIに興味はあるが使いこなせていない会社員（30〜40代）",
        "pain": "ChatGPTを触ったことはあるが、仕事に活かせていない。周りが使い始めて焦っている",
        "goal": "AIツールで作業時間を半減し、副業にも活かしたい",
        "concern": "月額費用の元が取れるか、セキュリティは大丈夫か",
    },
    "ai_saas": {
        "who": "DXを推進したい中小企業の経営者・管理職（40〜50代）",
        "pain": "社員のIT リテラシーが低く、ツール導入に踏み切れない",
        "goal": "AIツールで業務効率化し、人件費を抑えたい",
        "concern": "導入コスト、社員が使いこなせるか、既存システムとの連携",
    },
    "side_hustle": {
        "who": "副収入が欲しい会社員（25〜40代）。手取り25万で将来が不安",
        "pain": "副業に興味はあるが、何から始めればいいかわからない。詐欺も怖い",
        "goal": "リスクなく月3〜5万円の副収入を得る",
        "concern": "本当に稼げるのか、会社にバレないか、時間が取れるか",
    },
    "investment_savings": {
        "who": "投資初心者の会社員（25〜35代）。貯金はあるが運用していない",
        "pain": "新NISAが話題だが、証券口座選びで迷っている。損するのが怖い",
        "goal": "つみたてNISAで月3万から安全に資産形成",
        "concern": "元本割れリスク、手数料の違い、どの銘柄を選ぶか",
    },
    "productivity": {
        "who": "業務効率化に関心のあるビジネスパーソン（30〜40代）",
        "pain": "残業が多く、もっと効率よく仕事をしたい",
        "goal": "ツールを活用して1日2時間の時短を実現",
        "concern": "ツールが多すぎてどれを選べばいいかわからない",
    },
    "dx_tools": {
        "who": "ITに苦手意識のある中小企業の経営者（45〜60代）",
        "pain": "紙・Excel・手作業が多く、月末処理に3日かかる。インボイス対応も不安",
        "goal": "バックオフィスを自動化して本業に集中したい",
        "concern": "設定が難しそう、社員が拒否反応、コストが心配",
    },
    "savings_lifestyle": {
        "who": "固定費を見直したい一人暮らし・若年ファミリー（25〜35代）",
        "pain": "毎月の支出が多いが、何を削ればいいかわからない",
        "goal": "年間5〜10万円の固定費削減",
        "concern": "乗り換えの手間、サービス品質が落ちないか",
    },
    "high_value": {
        "who": "キャリアアップを目指す20〜30代社会人",
        "pain": "現職の年収に不満。スキルアップして転職or副業で収入を上げたい",
        "goal": "プログラミング習得 or 転職で年収100万アップ",
        "concern": "スクールの費用対効果、挫折しないか、未経験で本当に転職できるか",
    },
}


# ============================================================
# Gemini全文生成（v2コア）
# ============================================================

def _build_gemini_article_prompt(
    keyword: str,
    category: str,
    affiliates: list,
    persona: dict,
    latest_ai_info: dict = None,
    related_articles: list = None,
) -> str:
    """記事全文を生成するGeminiプロンプトを構築"""

    year = datetime.now().year

    # アフィリエイト情報を整形
    affiliate_info = ""
    if affiliates:
        af_lines = []
        for af in affiliates[:4]:
            af_lines.append(
                f"  - {af['name']}: {af['description']} / {af['commission']} / URL: {af['url']}"
            )
        affiliate_info = "\n".join(af_lines)

    # 関連記事情報
    related_info = ""
    if related_articles:
        related_info = "\n".join(
            f"  - [{a['title']}]({a['url']})" for a in related_articles[:5]
        )

    # 最新情報（あれば）
    fresh_info = ""
    if latest_ai_info:
        fresh_info = f"""
【最新情報（Geminiで事前取得済み）】
- 最新機能: {latest_ai_info.get('latest_feature', '不明')}
- アップデート: {latest_ai_info.get('update_highlight', '不明')}
- ビジネス活用例: {latest_ai_info.get('business_use_case', '不明')}
- 無料vs有料: {latest_ai_info.get('free_vs_paid', '不明')}
- 注意点: {latest_ai_info.get('caution', '不明')}

この情報を記事に自然に織り込んでください。
"""

    prompt = f"""あなたはSEOアフィリエイト記事のプロライターです。
以下の条件で、検索上位を狙える高品質な記事を1本生成してください。

【キーワード】{keyword}
【カテゴリ】{category}
【年】{year}年

【ターゲット読者】
- 誰: {persona.get('who', '')}
- 悩み: {persona.get('pain', '')}
- ゴール: {persona.get('goal', '')}
- 最後の懸念: {persona.get('concern', '')}
{fresh_info}
【記事の絶対ルール】
1. 3000〜5000文字（Markdown形式）
2. 冒頭に「結論ファースト」のまとめブロック（3行以内）を入れる
3. 見出し(##)は5〜8個。読者の悩みに沿った論理的な流れにする
4. 具体的な数字・データ・比較表を最低3箇所に入れる（「〜できます」だけの抽象的な表現はNG）
5. 1人の読者が「この記事だけで行動できる」レベルの具体性
6. 「**Q:** ... **A:** ...」形式のFAQを最低3つ含める
7. 記事末尾に「まとめ」セクション

【アフィリエイトリンクのルール（最重要）】
以下のサービスを記事内で紹介してください。ただし:
- 「おすすめサービス」のような独立CTAセクションは絶対に作らない
- 記事の流れの中で、読者が「ここで知りたい」と思うタイミングで自然に言及する
- リンクテキストは「公式サイトを見る →」「無料で試してみる →」など行動を促す形にする
- 1つのサービスにつき記事内で1〜2回まで（しつこくしない）
- Markdownリンク形式で: [リンクテキスト](URL)

【紹介するサービス】
{affiliate_info if affiliate_info else '（該当なし — アフィリエイトリンクなしで記事を書いてください）'}

【内部リンク（あれば記事内の適切な箇所で言及）】
{related_info if related_info else '（関連記事なし）'}

【差別化ポイント（他のAI量産記事と違いを出す）】
- 読者ペルソナの「最後の懸念」に正面から答えるセクションを必ず入れる
- 「〜がおすすめです」で終わらず、「なぜおすすめか」をデータで示す
- 失敗パターン・注意点を正直に書く（信頼性向上）
- 体験談調のリアルな表現を使う（「実際に試してみると...」「正直に言うと...」）

【禁止事項】
- 「〜しましょう」の連発
- 「おすすめポイント」の箇条書きだけの浅いセクション
- 「## この記事で紹介したおすすめサービス」のようなCTAセクション
- 明らかにAIが書いたとわかる定型表現（「さまざまな」「非常に」の多用）

【出力形式】
Markdown形式の記事本文のみを出力してください。
タイトル（# 見出し1）は含めないでください（別途生成します）。
コードブロックで囲まないでください。"""

    return prompt


def _generate_title_with_gemini(keyword: str, category: str, persona: dict) -> str:
    """Geminiで検索クリック率の高いタイトルを生成"""
    year = datetime.now().year

    prompt = f"""以下の条件でSEO記事のタイトルを1つだけ生成してください。

【キーワード】{keyword}
【読者】{persona.get('who', '')}（悩み: {persona.get('pain', '')}）
【年】{year}年

【タイトルのルール】
- 28〜40文字（全角換算）
- キーワードを自然に含める
- 数字または具体的なベネフィットを入れる
- 「【】」「｜」を効果的に使う
- 読者が「自分のことだ」と感じるフック

タイトルだけを1行で出力してください。説明や選択肢は不要です。"""

    try:
        from money_agent.gemini_client import generate
        result = generate(prompt, use_cache=False)
        if result:
            title = result.strip().strip('"').strip("'").strip("#").strip()
            if 10 < len(title) < 80:
                return title
    except Exception as e:
        print(f"  [SEO] タイトル生成エラー: {e}")

    # フォールバック
    return f"【{year}年最新】{keyword}｜初心者向け完全ガイド"


def generate_article_with_gemini(
    keyword: str,
    category: str,
    affiliates: list,
    feedback_insights: dict = None,
    related_articles: list = None,
) -> dict:
    """Geminiで高品質SEO記事を生成（v2メイン関数）"""

    feedback_insights = feedback_insights or {}
    latest_ai_info = feedback_insights.get("latest_ai_info", {})
    reader_concerns = feedback_insights.get("reader_concerns", [])

    persona = READER_PERSONAS.get(category, READER_PERSONAS.get("ai_tools", {}))

    # Geminiプロンプト構築
    prompt = _build_gemini_article_prompt(
        keyword=keyword,
        category=category,
        affiliates=affiliates,
        persona=persona,
        latest_ai_info=latest_ai_info,
        related_articles=related_articles,
    )

    # Gemini API呼び出し
    try:
        from money_agent.gemini_client import generate
        body = generate(prompt, use_cache=False, temperature=0.8)
    except Exception as e:
        print(f"  [SEO] Gemini記事生成エラー: {e}")
        body = None

    if not body or len(body) < 500:
        print("  [SEO] Gemini生成失敗 → テンプレートフォールバック")
        return _generate_template_article(keyword, category, affiliates, feedback_insights)

    # タイトル生成
    title = _generate_title_with_gemini(keyword, category, persona)

    # GEO: 結論ファースト（記事冒頭に追加）
    conclusion_block = build_conclusion_first(keyword, category, affiliates or [])

    # GEO: 数値データ比較テーブル
    comparison_table = build_data_comparison_table(keyword, category, affiliates or [])

    # 本文を組み立て
    parts = []
    parts.append(conclusion_block)
    if comparison_table:
        parts.append(comparison_table)
    parts.append(body)

    # GEO: 懸念点払拭セクション
    if reader_concerns:
        parts.append(build_concern_section(reader_concerns, keyword, affiliates or []))

    full_body = "\n\n".join(parts)

    # JSON-LD Schema.org
    faq_items = _extract_faq_from_body(full_body)
    schema_objects = [build_article_jsonld(title, keyword)]
    if faq_items:
        schema_objects.append(build_faq_jsonld(faq_items))
    full_body += "\n\n" + render_jsonld_block(schema_objects) + "\n"

    # 免責事項
    year = datetime.now().year
    month = datetime.now().month
    if category in {"investment_savings", "high_value"}:
        disclaimer = f"\n\n---\n\n> **【免責事項】** 本記事の情報は{year}年{month}月時点のものです。投資は自己責任でお願いします。制度・金利・手数料は変更される場合があります。最終的な投資判断はご自身でご確認ください。\n"
    else:
        disclaimer = f"\n\n---\n\n> **【免責事項】** 本記事の情報は{year}年{month}月時点のものです。サービス内容・料金は変更される場合があります。最新情報は各公式サイトでご確認ください。\n"
    full_body += disclaimer

    return {
        "title": title,
        "body": full_body,
        "keyword": keyword,
        "category": category,
        "char_count": len(full_body),
        "affiliate_count": len(affiliates),
        "template": "gemini_v2",
        "target": persona.get("who", ""),
        "has_fresh_info": bool(latest_ai_info),
        "generated_at": datetime.now().isoformat(),
    }


# ============================================================
# 旧テンプレートモード（フォールバック / quality_mode=False 用）
# ============================================================

def _generate_template_article(keyword, category, affiliates, feedback_insights=None):
    """旧テンプレートベース記事生成（ロールバック用）"""
    year = datetime.now().year
    feedback_insights = feedback_insights or {}

    body_parts = []
    body_parts.append(build_conclusion_first(keyword, category, affiliates or []))

    comparison_table = build_data_comparison_table(keyword, category, affiliates or [])
    if comparison_table:
        body_parts.append(comparison_table)

    body_parts.append(f"""この記事では**{keyword}**について、初心者でも実践できるよう基礎から応用まで解説します。

""")

    # 基本セクション
    body_parts.append(f"""## {keyword}とは？

{keyword}の基本を理解しましょう。

**主な特徴:**
- 誰でも無料・低コストで始められる
- スマホ・PCどちらでも使える
- 専門知識がなくてもOK

---

## メリット・デメリット

### メリット
1. **時間の節約** — 従来の方法と比較すると作業時間を大幅に短縮
2. **コスパが高い** — 無料プランでも十分な機能
3. **品質向上** — AI支援で初心者でも高品質なアウトプット

### デメリット
1. 学習コストがかかる（数時間程度）
2. 完璧ではない（チェックが必要）

---

## 具体的な使い方

### STEP1：アカウント登録（3分）
公式サイトで無料アカウントを作成。

### STEP2：基本設定
日本語対応しているので迷いません。

### STEP3：実際に使ってみる
小さなタスクから試すのがおすすめ。

---
""")

    # アフィリエイト（旧方式）
    if affiliates:
        body_parts.append("## おすすめサービス\n\n")
        for af in affiliates[:4]:
            body_parts.append(f"### {af['name']}\n\n**{af['description']}**\n\n> [{af['cta']}]({af['url']})\n\n---\n")

    body_parts.append(f"""## よくある質問

**Q: 初期費用はかかりますか？**
A: 基本的に無料で始められます。

**Q: スマホだけでもできますか？**
A: はい、スマホのみでも対応可能です。

**Q: どのくらいで収益が出始めますか？**
A: 個人差はありますが、1〜3ヶ月で最初の収益を得ている方が多いです。

---

## まとめ

{keyword}は正しい方法で取り組めば誰でも始められます。今日から一歩踏み出してみてください。
""")

    body = "".join(body_parts)

    # JSON-LD
    title = f"【{year}年最新】{keyword}｜初心者向け完全ガイド"
    faq_items = _extract_faq_from_body(body)
    schema_objects = [build_article_jsonld(title, keyword)]
    if faq_items:
        schema_objects.append(build_faq_jsonld(faq_items))
    body += "\n\n" + render_jsonld_block(schema_objects) + "\n"

    month = datetime.now().month
    body += f"\n\n---\n\n> **【免責事項】** 本記事の情報は{year}年{month}月時点のものです。最新情報は各公式サイトでご確認ください。\n"

    return {
        "title": title,
        "body": body,
        "keyword": keyword,
        "category": category,
        "char_count": len(body),
        "affiliate_count": len(affiliates) if affiliates else 0,
        "template": "template_fallback",
        "target": "",
        "has_fresh_info": False,
        "generated_at": datetime.now().isoformat(),
    }


# ============================================================
# FAQ抽出（JSON-LD用）
# ============================================================

def _extract_faq_from_body(body: str) -> list[dict]:
    """記事本文から Q/A ペアを抽出して FAQPage JSON-LD 用データを生成"""
    import re
    faq_items = []
    pattern = re.compile(r'\*\*Q[:：]\s*(.+?)\*\*\s*\nA[:：]\s*(.+?)(?=\n\n|\Z)', re.DOTALL)
    for m in pattern.finditer(body):
        question = m.group(1).strip()
        answer = m.group(2).strip()[:200]
        faq_items.append({"question": question, "answer": answer})
    return faq_items[:5]


# ============================================================
# メインエントリーポイント（既存インターフェース維持）
# ============================================================

# quality_mode環境変数で制御（デフォルト: True = Gemini全文生成）
QUALITY_MODE = os.environ.get("QUALITY_MODE", "true").lower() in ("true", "1", "yes")


def generate_seo_article(keyword: str, category: str,
                         affiliates: list = None,
                         feedback_insights: dict = None,
                         related_articles: list = None) -> dict:
    """GEO最適化SEO記事を生成（v2: Gemini全文生成 / v1: テンプレートフォールバック）"""

    if affiliates is None:
        affiliates = get_affiliates_for_category(category)

    if QUALITY_MODE:
        return generate_article_with_gemini(
            keyword=keyword,
            category=category,
            affiliates=affiliates,
            feedback_insights=feedback_insights,
            related_articles=related_articles,
        )
    else:
        return _generate_template_article(keyword, category, affiliates, feedback_insights)


if __name__ == "__main__":
    article = generate_seo_article("AI副業 始め方 初心者", "side_hustle")
    print(f"タイトル: {article['title']}")
    print(f"文字数: {article['char_count']}")
    print(f"テンプレート: {article['template']}")
    print(f"アフィリエイト数: {article['affiliate_count']}")
    print(f"\n本文（最初の500文字）:\n{article['body'][:500]}")
