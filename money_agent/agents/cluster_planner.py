"""
クラスタープランナー
成功した「縦（個別）＋横（比較）」パターンを次のジャンルに横展開する

【クラスター戦略】
 第1陣（DXツール）: freee / マネーフォワード / Chatwork ← 完成
 第2陣（AIツール）: ChatGPT / Notion AI / Canva     ← 次
 第3陣（人事・労務）: freee人事 / マネフォ勤怠 / 給与奉行 ← 将来

「経営者の悩みが連鎖する順」= 会計→コミュニケーション→給与→勤怠→採用
この順にクラスターを作ると、サイト全体が「中小企業DX専門メディア」になる。
"""
import json
import os
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent.parent

# ── クラスター定義 ────────────────────────────────────────────
CLUSTER_ROADMAP = [
    {
        "cluster_id": 1,
        "theme": "バックオフィス効率化（DXツール）",
        "status": "完成",
        "target": "中小企業経営者",
        "tools": ["freee会計", "マネーフォワード クラウド", "Chatwork"],
        "hub_article": "バックオフィスを最短で効率化するならどれ？",
        "keywords": [
            "freee 中小企業 クラウド会計",
            "マネーフォワード クラウド 中小企業",
            "Chatwork 社内チャット 中小企業",
            "バックオフィス 効率化 ツール 比較 中小企業",
        ],
        "affiliate": "freee/マネーフォワード/Chatwork（A8.net・提携申請中）",
    },
    {
        "cluster_id": 2,
        "theme": "AIツール・業務自動化（SaaS）",
        "status": "次の仕込み対象",
        "target": "中小企業経営者・ビジネスパーソン",
        "tools": ["ChatGPT（OpenAI）", "Notion AI", "Canva Pro"],
        "hub_article": "中小企業のAI活用、何から始める？ChatGPT・Notion・Canvaを比較",
        "keywords": [
            "ChatGPT 中小企業 活用 事例",
            "Notion AI 使い方 業務効率化",
            "Canva Pro 中小企業 デザイン",
            "AIツール 中小企業 比較 おすすめ",
        ],
        "affiliate": "Canva Pro（アフィリエイト対応）/ Notion Plus",
        "why": (
            "DXクラスターで「業務効率化」に関心を持った読者の次の悩みが"
            "『具体的にAIをどう使うか』。自然な導線になる。"
        ),
        "commission_est": "Canva Pro: 36%継続報酬 / Notion: 50%×3ヶ月",
    },
    {
        "cluster_id": 3,
        "theme": "給与・勤怠・人事管理",
        "status": "第3陣（将来）",
        "target": "従業員10名以上の中小企業",
        "tools": ["freee人事労務", "マネーフォワード クラウド勤怠", "KING OF TIME"],
        "hub_article": "中小企業の給与計算・勤怠管理、どのソフトが最適？3サービス比較",
        "keywords": [
            "勤怠管理 クラウド 中小企業 比較",
            "freee 人事労務 使い方",
            "マネーフォワード 勤怠 中小企業",
            "給与計算 ソフト おすすめ 中小企業",
        ],
        "affiliate": "freee人事労務/マネーフォワード（A8.net）",
        "why": (
            "DXクラスター・AIクラスターで経理が解決した経営者の次の課題が"
            "『給与計算・勤怠の自動化』。第1陣のfreeeを導入した読者への自然なアップセル。"
        ),
        "commission_est": "freee人事労務: 2,000〜3,000円/登録",
    },
    {
        "cluster_id": 4,
        "theme": "ネットショップ・EC開業",
        "status": "第4陣（将来）",
        "target": "実店舗オーナー・副業検討者",
        "tools": ["BASE", "Shopify", "カラーミーショップ"],
        "hub_article": "ネットショップを開くならどれ？BASE・Shopify・カラーミーを徹底比較",
        "keywords": [
            "BASE 使い方 開設",
            "Shopify 日本語 使い方",
            "ネットショップ 比較 2026",
            "EC 開業 費用 比較",
        ],
        "affiliate": "各社（A8.net / バリューコマース）",
        "why": "DXで業務効率化した経営者の次の一手が『売上を増やす』EC展開。",
        "commission_est": "BASE: 1,000〜2,000円/登録 / Shopify: 月額の200%",
    },
]

# ── 第2陣 keywords_db 追加用データ ──────────────────────────
CLUSTER2_KEYWORDS = {
    "ai_saas": {
        "label": "AIツール・SaaS（中小企業向け）",
        "commission_range": "1,500〜10,000円/件",
        "keywords": [
            {"kw": "ChatGPT 中小企業 活用 事例", "intent": "informational", "volume": "high"},
            {"kw": "ChatGPT Plus 仕事 効率化 具体例", "intent": "how-to", "volume": "high"},
            {"kw": "Notion AI 使い方 業務効率化", "intent": "how-to", "volume": "mid"},
            {"kw": "Notion テンプレート 中小企業 無料", "intent": "commercial", "volume": "mid"},
            {"kw": "Canva Pro 中小企業 デザイン 費用対効果", "intent": "commercial", "volume": "mid"},
            {"kw": "AIツール 中小企業 比較 おすすめ 2026", "intent": "commercial", "volume": "high"},
            {"kw": "AI 議事録 自動化 ツール", "intent": "commercial", "volume": "mid"},
            {"kw": "AI 文章作成 ビジネス 活用", "intent": "how-to", "volume": "high"},
        ],
    }
}

# ── 第2陣 article テンプレート ───────────────────────────────
CLUSTER2_ARTICLE_STYLE = {
    "persona": "AI活用コンサルタント（中小企業に実践的なAI導入を支援している専門家）",
    "hook_pattern": "「AIって難しそう」という方へ。実際の中小企業での使い方を解説します。",
    "worries": [
        "どのAIツールから始めればいいかわからない",
        "社員がAIを使いこなせるか不安",
        "AIが出した内容の正確性が心配",
    ],
    "faq_fixed": [
        "ChatGPTの内容は社外秘情報として扱っていいですか？（セキュリティ）",
        "AIが生成したコンテンツは著作権上問題ありませんか？",
        "無料プランと有料プラン（Plus）の実際の違いは？",
    ],
    "title_patterns": {
        "ChatGPT 中小企業 活用 事例": [
            "ChatGPTで仕事が変わった中小企業の実例【導入して3ヶ月でわかったこと】",
            "社長がChatGPTを使い始めたら、会社の何が変わったか？",
        ],
        "Notion AI 使い方 業務効率化": [
            "Notion AIで議事録・報告書を自動化した話【月20時間の削減実例】",
            "Notion AIって実際どう使う？中小企業での活用法を具体的に解説",
        ],
        "Canva Pro 中小企業 デザイン 費用対効果": [
            "デザイナーなしでプロ品質の資料を作る方法【Canva Proを中小企業が使った結果】",
            "Canva Proは月1,500円の価値があるか？中小企業目線で正直に評価する",
        ],
        "AIツール 中小企業 比較 おすすめ 2026": [
            "中小企業のAI活用、何から始める？ChatGPT・Notion・Canvaを経営者目線で比較",
            "2026年版：中小企業が最初に導入すべきAIツール3選と選び方",
        ],
    },
}


def generate_cluster_plan() -> dict:
    """第2陣クラスター実行計画を生成"""
    next_cluster = CLUSTER_ROADMAP[1]  # 第2陣（インデックス1）

    plan = {
        "generated_at": datetime.now().isoformat(),
        "current_cluster": CLUSTER_ROADMAP[0]["theme"],
        "next_cluster": {
            **next_cluster,
            "action_plan": [
                {
                    "step": 1,
                    "action": "Canva ProのアフィリエイトをAFFILIATE_PROGRAMSに追加（既存）",
                    "status": "完了済み（canva_pro, notion がkeywords_db.pyに存在）",
                },
                {
                    "step": 2,
                    "action": "ai_saasカテゴリをkeywords_db.pyに追加",
                    "keywords": CLUSTER2_KEYWORDS["ai_saas"]["keywords"],
                },
                {
                    "step": 3,
                    "action": "seo_article_generator.pyにai_saasテンプレートを追加",
                    "persona": CLUSTER2_ARTICLE_STYLE["persona"],
                    "faq_fixed": CLUSTER2_ARTICLE_STYLE["faq_fixed"],
                    "title_patterns": CLUSTER2_ARTICLE_STYLE["title_patterns"],
                },
                {
                    "step": 4,
                    "action": "Writer を4本走らせて記事生成（個別3本＋比較1本）",
                    "articles": [
                        "ChatGPTで仕事が変わった中小企業の実例",
                        "Notion AIで業務効率化した話",
                        "Canva Pro 費用対効果レビュー",
                        "中小企業のAI活用、何から始める？3ツール比較（hub）",
                    ],
                },
            ],
        },
        "full_roadmap": CLUSTER_ROADMAP,
        "seo_strategy": {
            "pillar_page": "中小企業のDX・AI活用 完全ガイド（将来的な総まとめ記事）",
            "cluster_link_strategy": (
                "各クラスターのhub記事が相互リンクする構造。"
                "DXクラスターhub → AIクラスターhub → 勤怠クラスターhub と内部リンクで連鎖させる。"
                "Googleはこの構造を『専門性の高いサイト』と判断しやすい。"
            ),
            "expected_effect": (
                "クラスター2が揃うと『中小企業 DX』『中小企業 AI活用』で"
                "検索上位を狙える専門性が生まれる。"
                "3クラスター完成時点でサイト評価が大幅に向上する見込み。"
            ),
        },
    }
    return plan


def run(state: dict = None) -> dict:
    """CEOエージェントから呼び出されるエントリポイント"""
    print("  🗺️ [ClusterPlanner] 第2陣クラスター計画を生成中...")
    plan = generate_cluster_plan()

    # 保存
    output_file = BASE_DIR / "data" / "cluster_plan.json"
    output_file.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    next_c = plan["next_cluster"]
    print(f"  ✅ [ClusterPlanner] 次のジャンル: 「{next_c['theme']}」")
    print(f"     ツール: {next_c['tools']}")
    print(f"     hub記事: {next_c['hub_article']}")
    return plan


if __name__ == "__main__":
    plan = run()
    print("\n" + "=" * 60)
    print("  クラスターロードマップ")
    print("=" * 60)
    for c in plan["full_roadmap"]:
        mark = "✅" if c["status"] == "完成" else ("→" if "次" in c["status"] else "  ")
        print(f"  {mark} 第{c['cluster_id']}陣: {c['theme']} [{c['status']}]")
    print()
    print("次のアクション:")
    for step in plan["next_cluster"]["action_plan"]:
        print(f"  STEP{step['step']}: {step['action']}")
