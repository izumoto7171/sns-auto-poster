"""
月10万円SEO記事生成エンジン
- 2000〜4000文字のSEO最適化記事
- アフィリエイトリンクを自然に挿入
- はてなブログ / note 両対応のHTML/Markdown
"""

import os
import sys
import random
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from money_agent.keywords_db import get_affiliates_for_category, KEYWORD_CATEGORIES

# ============================================================
# SEO記事テンプレート（カテゴリ × スタイル別）
# ============================================================

ARTICLE_TEMPLATES = {

    "ai_tools": [
        {
            "title_format": "【{year}年最新】{keyword}完全ガイド｜初心者でも5分でわかる使い方",
            "structure": ["hook", "what_is", "merit", "how_to", "tips", "affiliate_cta", "summary"],
            "tone": "教育的・分かりやすい",
            "target": "AI初心者・副業検討層"
        },
        {
            "title_format": "{keyword}を試してみた正直レビュー【無料プランで実際に使った結果】",
            "structure": ["hook", "review_intro", "pros_cons", "use_cases", "affiliate_cta", "summary"],
            "tone": "体験談・正直レビュー",
            "target": "比較検討層"
        }
    ],

    "side_hustle": [
        {
            "title_format": "【{year}年版】{keyword}で月3万円稼ぐまでの全手順",
            "structure": ["hook", "reality_check", "step_by_step", "tools", "affiliate_cta", "faq", "summary"],
            "tone": "実践的・ステップ形式",
            "target": "副業初心者"
        },
        {
            "title_format": "{keyword}｜在宅で稼ぐ方法を現役副業ワーカーが解説",
            "structure": ["hook", "author_intro", "methods", "tools", "affiliate_cta", "caution", "summary"],
            "tone": "経験談ベース",
            "target": "会社員・主婦・学生"
        }
    ],

    "investment_savings": [
        {
            "title_format": "【初心者向け】{keyword}徹底比較｜{year}年おすすめランキング",
            "structure": ["hook", "comparison_table", "detail_review", "how_to_start", "affiliate_cta", "caution", "summary"],
            "tone": "比較・ランキング形式",
            "target": "投資初心者・比較検討層"
        }
    ],

    "productivity": [
        {
            "title_format": "{keyword}を使って仕事効率を2倍にした方法【具体的な手順あり】",
            "structure": ["hook", "problem", "solution", "how_to", "tools", "affiliate_cta", "summary"],
            "tone": "問題解決型",
            "target": "ビジネスパーソン"
        }
    ]
}

# ============================================================
# セクション別コンテンツ生成（テンプレート）
# ============================================================

def generate_section(section: str, keyword: str, category: str, affiliates: list) -> str:
    """各セクションのコンテンツを生成"""

    year = datetime.now().year

    sections = {
        "hook": f"""## 「{keyword}って本当に使えるの？」

そんな疑問を持つ方に向けて、この記事では**{keyword}について基礎から実践まで**徹底解説します。

実際に試してみた経験をもとに、初心者がつまずくポイントも含めて分かりやすくお伝えします。

---
""",
        "what_is": f"""## {keyword}とは？【基礎知識】

まず{keyword}の基本を理解しましょう。

**{keyword}の主な特徴:**
- 誰でも無料・低コストで始められる
- スマホ・PCどちらでも使える
- 専門知識がなくてもOK
- 即日から使い始められる

特に**初心者でも扱いやすい**点が最大の魅力です。

---
""",
        "merit": f"""## {keyword}を使うメリット・デメリット

### ✅ メリット

**1. 時間の節約**
従来の方法と比較すると、作業時間を大幅に短縮できます。

**2. コストパフォーマンスが高い**
無料プランでも十分な機能が使えるため、始めるハードルが低いです。

**3. 品質の向上**
AIの支援により、初心者でも高品質なアウトプットが可能になります。

### ❌ デメリット

**1. 学習コストがかかる**
最初は使い方を覚える必要があります（とはいえ数時間程度）。

**2. 完璧ではない**
AIの出力は必ずチェックが必要です。

---
""",
        "how_to": f"""## {keyword}の使い方【ステップ別解説】

### STEP1：アカウント登録

まずは公式サイトにアクセスして無料アカウントを作成します。

メールアドレスがあれば**3分以内**に登録完了。

### STEP2：基本設定

登録後、プロフィールと基本設定を行います。

日本語対応しているので迷うことはありません。

### STEP3：実際に使ってみる

最初は**小さなタスクから試す**のがおすすめです。

```
💡 コツ：完璧を求めず、まず動かしてみることが大切
```

### STEP4：応用・カスタマイズ

基本操作に慣れたら、自分のニーズに合わせてカスタマイズしていきましょう。

---
""",
        "tips": f"""## {keyword}をさらに活用する5つのコツ

**コツ1：毎日少しずつ使う**
週1回まとめて使うより、毎日5分使う方が習熟が早いです。

**コツ2：テンプレートを活用する**
よく使うプロンプトや操作はテンプレートとして保存しておきましょう。

**コツ3：コミュニティに参加する**
使い方の質問や最新情報の共有ができるコミュニティに入ると上達が早まります。

**コツ4：他のツールと組み合わせる**
複数のツールを組み合わせることで、より高い効果が得られます。

**コツ5：定期的に新機能をチェックする**
AIツールは急速に進化しています。定期的にアップデート情報を確認しましょう。

---
""",
        "step_by_step": f"""## {keyword}で稼ぐ具体的な手順

### 第1週：準備・学習（0円〜）

1. 必要なツール・サービスに無料登録
2. 基本的な使い方を習得（YouTube・公式チュートリアル活用）
3. 小さな仕事を1〜2件受注してみる

### 第2〜3週：実践・改善（副収入が発生し始める）

1. 受注した仕事を完了・フィードバックをもらう
2. プロフィールを充実させてリピーターを獲得
3. 単価アップの交渉を開始

### 第4週〜：スケールアップ

1. 得意な分野に特化して専門性を高める
2. 複数のプラットフォームで展開
3. 外注・自動化を取り入れてさらに効率化

```
📊 実際の収益例：
1ヶ月目：5,000〜20,000円
3ヶ月目：30,000〜80,000円
6ヶ月目：100,000円以上も可能
```

---
""",
        "review_intro": f"""## 実際に{keyword}を使ってみた

私が{keyword}を始めたのは{year-1}年のこと。

最初は半信半疑でしたが、試してみたら**想像以上に使いやすく**驚きました。

この記事では、実際の使用感を正直にお伝えします。

---
""",
        "pros_cons": f"""## {keyword} 実際に使ってわかったメリット・デメリット

### 良かった点（星4.5/5）

**✅ 操作が直感的で分かりやすい**
マニュアルを読まなくても使い始められるほど直感的なUIでした。

**✅ 出力品質が高い**
特に日本語対応の精度が良く、実用的なアウトプットが得られました。

**✅ 無料プランが充実**
有料プランにしなくてもある程度の機能が使えます。

### 気になった点

**⚠️ 無料プランには制限あり**
本格的に使う場合は有料プランが必要になることも。

**⚠️ 最初の学習コスト**
使いこなすまでに少し時間がかかります（1〜2週間程度）。

---
""",
        "comparison_table": f"""## {keyword} 比較一覧表【{year}年最新版】

| サービス名 | 特徴 | 手数料 | 初心者向け |
|-----------|------|--------|-----------|
| ① Aサービス | 使いやすさNo.1 | 無料〜 | ◎ |
| ② Bサービス | 機能が豊富 | 無料〜 | ○ |
| ③ Cサービス | 実績が豊富 | 無料〜 | ○ |

**総合おすすめ：Aサービス**

初心者には①が最もおすすめです。理由は以下の通り：
- 登録が簡単（5分以内）
- サポートが充実
- 無料で始められる

---
""",
        "tools": f"""## {keyword}に役立つおすすめツール

### 無料ツール

**1. Google検索・Bard**
基本的な調査・下調べに活用できます。完全無料。

**2. Canva（無料版）**
SNS用の画像作成に便利。テンプレートが豊富で初心者でも使いやすい。

**3. Notion（無料版）**
タスク管理・ノート整理に最適。チームでの共有も可能。

### 有料ツール（月1,000〜3,000円）

副業が軌道に乗ってきたら、以下のツールへの投資を検討してみてください：

- ChatGPT Plus（月20ドル）：作業効率が大幅に向上
- Canva Pro（月1,500円）：プロ品質のデザインが作れる

---
""",
        "affiliate_cta": _build_affiliate_cta(affiliates, keyword),
        "faq": f"""## よくある質問（FAQ）

**Q: 初期費用はかかりますか？**
A: 基本的に無料で始められます。必要に応じて有料プランにアップグレードしてください。

**Q: スマホだけでもできますか？**
A: はい、スマホのみでも十分対応可能です。

**Q: どのくらいで収益が出始めますか？**
A: 個人差はありますが、多くの方が1〜3ヶ月で最初の収益を得ています。

**Q: 副業として確定申告は必要ですか？**
A: 年間20万円以上の副収入がある場合は確定申告が必要です。

---
""",
        "caution": f"""## 注意点・リスクについて

{keyword}に取り組む際の注意点をお伝えします。

**❗ 詐欺・悪徳業者に注意**
「簡単に月100万円」などの誇大広告には要注意。信頼できるサービスを選びましょう。

**❗ 税金・確定申告を忘れずに**
副収入が増えたら税務処理も適切に行いましょう。

**❗ 継続が重要**
すぐに結果が出ない場合もあります。焦らず継続することが大切です。

---
""",
        "summary": f"""## まとめ

{keyword}は、正しい方法で取り組めば誰でも始められる分野です。

この記事のポイントを振り返ると：

1. **基本を理解する**：まず仕組みを把握してから始める
2. **小さく始める**：最初から大きく投資しない
3. **継続する**：結果が出るまで3ヶ月は続ける
4. **ツールを活用する**：効率化ツールを積極的に使う

今日から一歩踏み出してみてください。

最後まで読んでいただきありがとうございました！
"""
    }

    return sections.get(section, "")


def _build_affiliate_cta(affiliates: list, keyword: str) -> str:
    """アフィリエイトCTAセクションを生成"""
    if not affiliates:
        return ""

    content = "## この記事で紹介したおすすめサービス\n\n"

    for af in affiliates[:3]:  # 最大3件
        content += f"""### 🔗 {af['name']}

**{af['description']}**

手数料・報酬：{af['commission']}

> [{af['cta']}]({af['url']})

---
"""
    return content


def generate_seo_article(keyword: str, category: str) -> dict:
    """SEO最適化記事を生成"""

    year = datetime.now().year
    affiliates = get_affiliates_for_category(category)

    # テンプレート選択
    templates = ARTICLE_TEMPLATES.get(category, ARTICLE_TEMPLATES["ai_tools"])
    template = random.choice(templates)

    # タイトル生成
    title = template["title_format"].format(keyword=keyword, year=year)

    # 記事構造に従ってコンテンツ生成
    body_parts = []

    # 導入文
    body_parts.append(f"""この記事では**{keyword}**について、初心者でも実践できるよう基礎から応用まで解説します。

実際に試してみた経験をもとに、失敗しないためのポイントも含めてお伝えします。

""")

    # 目次
    body_parts.append("## 目次\n")
    for i, section in enumerate(template["structure"], 1):
        section_titles = {
            "hook": f"{keyword}とは",
            "what_is": "基本知識",
            "merit": "メリット・デメリット",
            "how_to": "具体的な使い方・手順",
            "tips": "活用のコツ5選",
            "step_by_step": "稼ぐための具体的な手順",
            "review_intro": "実際に使ってみた",
            "pros_cons": "使ってわかったこと",
            "comparison_table": "比較一覧",
            "tools": "おすすめツール",
            "affiliate_cta": "おすすめサービス",
            "faq": "よくある質問",
            "caution": "注意点",
            "summary": "まとめ",
            "author_intro": "この記事の筆者について",
            "methods": "具体的な方法",
            "use_cases": "活用事例",
            "problem": "よくある悩み",
            "solution": "解決策",
            "detail_review": "詳細レビュー",
            "how_to_start": "始め方",
            "reality_check": "現実的な話",
        }
        title_text = section_titles.get(section, section)
        body_parts.append(f"{i}. {title_text}\n")

    body_parts.append("\n---\n\n")

    # 各セクションのコンテンツ
    for section in template["structure"]:
        content = generate_section(section, keyword, category, affiliates)
        body_parts.append(content)

    body = "".join(body_parts)

    # メタ情報
    return {
        "title": title,
        "body": body,
        "keyword": keyword,
        "category": category,
        "char_count": len(body),
        "affiliate_count": len(affiliates),
        "template": template["tone"],
        "target": template["target"],
        "generated_at": datetime.now().isoformat()
    }


if __name__ == "__main__":
    # テスト生成
    article = generate_seo_article("AI副業 始め方 初心者", "side_hustle")
    print(f"タイトル: {article['title']}")
    print(f"文字数: {article['char_count']}")
    print(f"アフィリエイト数: {article['affiliate_count']}")
    print(f"\n本文（最初の500文字）:\n{article['body'][:500]}")
