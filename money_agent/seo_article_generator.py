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
    ],

    "ai_saas": [
        {
            "title_format": "【{year}年最新】{keyword}完全ガイド｜中小企業での実践的な使い方",
            "structure": ["hook", "latest_news", "merit", "how_to", "tips", "affiliate_cta", "summary"],
            "tone": "AI活用コンサルタント・最新情報重視",
            "target": "中小企業経営者・ビジネスパーソン"
        },
        {
            "title_format": "{keyword}｜実際に使ってわかった本音レビュー【{year}年版】",
            "structure": ["hook", "latest_news", "pros_cons", "how_to", "affiliate_cta", "summary"],
            "tone": "体験談・正直レビュー・最新情報あり",
            "target": "AI導入を検討している経営者・管理職"
        }
    ],

    "dx_tools": [
        {
            "title_format": "【中小企業向け】{keyword}の導入メリットを現場目線で解説｜{year}年版",
            "structure": ["dx_hook", "user_worries", "what_is", "merit", "how_to", "faq", "affiliate_cta", "summary"],
            "tone": "親切なDXアドバイザー・中小企業経営者に寄り添う",
            "target": "ITに疎い中小企業の経営者・管理職"
        },
        {
            "title_format": "{keyword}｜導入を迷っている経営者に伝えたいこと【ITが苦手でも大丈夫】",
            "structure": ["dx_hook", "user_worries", "merit", "how_to", "faq", "affiliate_cta", "summary"],
            "tone": "親切なDXアドバイザー・背中を押すスタイル",
            "target": "DX検討中の中小企業経営者"
        }
    ]
}

# ============================================================
# セクション別コンテンツ生成（テンプレート）
# ============================================================

def _extract_tool_name(keyword: str) -> str:
    """キーワードからツール名（製品名）を抽出する"""
    # 製品名として認識するマッピング（前方一致順）
    known_tools = [
        "マネーフォワード クラウド",
        "マネーフォワード",
        "freee",
        "Chatwork",
    ]
    kw_lower = keyword.lower()
    for tool in known_tools:
        if kw_lower.startswith(tool.lower()):
            return tool
    # 不明な場合は先頭の単語を返す
    return keyword.split()[0]


def _dx_merit_section(keyword: str, tool: str) -> str:
    return f"""## {tool}を導入するメリット・注意点

### ✅ 導入で変わること

**1. バックオフィス作業の時間が大幅に削減される**
手入力・転記・集計といった繰り返し作業を自動化できます。
「月次締めが3日かかっていたのが1日になった」という声は珍しくありません。

**2. ヒューマンエラーが激減する**
手書き・Excel管理では避けられない入力ミスや計算ミスを、システムが自動チェックします。
消費税の計算ミス・給与計算のズレは後から修正コストが大きくなるため、特に効果が高い部分です。

**3. 場所を選ばずリアルタイムで経営データを確認できる**
クラウドなので、事務所の外からでもスマホで帳簿・売上・経費を確認できます。
「社長が出張中でも月次の数字をすぐ確認できる」という使い方が典型的です。

### 導入前に知っておきたい注意点

**1. 初期設定に半日〜1日かかる**
会社情報・銀行口座・科目設定など、最初の環境構築に時間が必要です。
ただし、導入サポート（電話・チャット）を使えば一人でも進められます。
サポートを積極的に活用することをおすすめします。

**2. 税理士との連携方法を事前に確認する**
現在顧問税理士がいる場合、データの共有方法（会計データのエクスポート形式など）を
事前に税理士に確認しておくとスムーズです。
多くのクラウド会計ソフトは税理士向けの招待機能を持っています。

---
"""


def _dx_how_to_section(keyword: str, tool: str) -> str:
    return f"""## {tool}の始め方【4ステップ】

### STEP1：無料トライアルに申し込む（所要時間：5分）

公式サイトでメールアドレスを入力するだけで登録できます。
クレジットカードの登録は不要なサービスがほとんどです。

### STEP2：会社の基本情報を入力する（所要時間：15〜30分）

会社名・業種・従業員数・現在の経理方法などを入力します。
入力した情報をもとに、最適な設定を提案してくれます。

### STEP3：まず1つの業務だけ試してみる（最初の1週間）

最初から全機能を使おうとする必要はありません。
「請求書の発行だけ」「経費の記録だけ」など、**1つの業務に絞って**使い始めましょう。

```
ポイント：完璧を求めず、とにかく1件やってみることが大切
```

### STEP4：効果を確認してから本格導入を判断する

1週間〜1ヶ月使ってみて、時間短縮・ミス削減を数字で確認します。
「月に○時間削減できた」という実績が、社内への説得材料にもなります。

---
"""


def _dx_faq_section(keyword: str, tool: str) -> str:
    return f"""## よくある質問

**Q: インボイス制度（適格請求書）に対応していますか？**
A: はい、主要なクラウド会計・請求書ソフトはインボイス制度に対応しています。
適格請求書発行事業者の登録番号を設定すると、制度に準拠した請求書を自動で発行できます。
手書き・Excelで対応している場合は、早めにクラウド化することをおすすめします。

**Q: 電子帳簿保存法（電帳法）には対応していますか？**
A: 対応しています。2024年1月から義務化された電子取引データの保存要件（真実性・可視性の確保）を
クラウド上で自動的に満たす形で保存できます。
紙で保存していた領収書・請求書のスキャン保存（スキャナ保存）にも対応しているサービスが多いです。

**Q: 顧問税理士と一緒に使えますか？連携はどうすればいいですか？**
A: 税理士を「顧問税理士として招待」する機能があり、同じデータをリアルタイムで共有できます。
従来の「月末にデータをまとめて渡す」作業が不要になり、税理士の作業時間削減にもつながります。
導入前に税理士に相談し、使用しているソフトとの互換性を確認しておくとスムーズです。

---
"""


def generate_section(section: str, keyword: str, category: str, affiliates: list) -> str:
    """各セクションのコンテンツを生成"""

    year = datetime.now().year
    tool = _extract_tool_name(keyword) if category == "dx_tools" else keyword

    # DXツール専用オーバーライド
    if category == "dx_tools":
        if section == "merit":
            return _dx_merit_section(keyword, tool)
        if section == "how_to":
            return _dx_how_to_section(keyword, tool)
        if section == "faq":
            return _dx_faq_section(keyword, tool)

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
""",

        # ── DXアドバイザーペルソナ用セクション ──────────────────────

        "dx_hook": f"""## 「{tool}、うちみたいな会社でも使えるの？」

そう思っている経営者の方、安心してください。

私はこれまで多くの中小企業がDXに取り組む現場を見てきました。

「ITは苦手」「社員が使いこなせるか不安」「コストが心配」――そういった不安はよくわかります。

この記事では、**難しい専門用語は使わずに**{tool}のメリットと始め方を解説します。
一緒に、無理のない一歩を踏み出しましょう。

---
""",

        "user_worries": f"""## よくある悩みと、その解決策

### 悩み① 「設定が複雑そうで、自分たちだけでは無理では？」

**→ 大丈夫です。サポートが充実しています。**

最近のクラウドツールは、導入サポートが手厚く、電話・チャットで気軽に質問できます。
パソコンが苦手な方でも、**ステップガイドに沿って進めるだけ**でセットアップが完了します。

実際に「全員60代の会社でも3日で使えた」という声もあります。

---

### 悩み② 「月額費用がかかるのでは？今より余計なコストは増やしたくない」

**→ まず無料トライアルで試せます。効果を確認してから判断しましょう。**

多くのサービスは**30日間の無料トライアル**があります。
また、月数千円の費用でも、**紙・印刷・手作業の削減**でトータルコストが下がるケースがほとんどです。

「月5,000円のツールで、毎月20時間の残業が削減できた」という事例もあります。

---

### 悩み③ 「社員が拒否反応を示しそうで、社内の説得が大変そう」

**→ 小さな部署から始めて、成果を見せましょう。**

いきなり全社展開する必要はありません。
**1部署・1業務からスモールスタート**し、実際の効果を数字で示すと、社内の理解が得やすくなります。

「経理チームの1人に試してもらったら、月次締めが3日から1日に短縮され、他の部署も導入を希望してきた」という流れが典型です。

---
""",
    }

    return sections.get(section, "")


def _build_affiliate_cta(affiliates: list, keyword: str) -> str:
    """アフィリエイトCTAセクションを生成"""
    if not affiliates:
        return ""

    content = "## この記事で紹介したおすすめサービス\n\n"

    for af in affiliates[:4]:  # 最大4件
        content += f"""### 🔗 {af['name']}

**{af['description']}**

手数料・報酬：{af['commission']}

> [{af['cta']}]({af['url']})

---
"""
    return content


# AIツール・SaaS記事：キーワード → 自然言語タイトルのマッピング
AI_SAAS_NATURAL_TITLES = {
    "ChatGPT 中小企業 活用 事例": [
        "ChatGPTを中小企業で使いこなす方法【2026年最新・実例つき】",
        "社長がChatGPTを導入したら、会社の何が変わったか？実例で解説",
    ],
    "ChatGPT Plus 仕事 効率化 具体例": [
        "ChatGPT Plusは月額20ドルの価値があるか？仕事で使い倒した結果を報告",
        "ChatGPT Plusで仕事効率化【GPT-4oを使って実際に変わった5つのこと】",
    ],
    "Notion AI 使い方 業務効率化": [
        "Notion AIで議事録・報告書を自動生成した話【月20時間削減の実例】",
        "Notion AIって実際どう使う？中小企業での活用法を具体的に解説",
    ],
    "Notion テンプレート 中小企業 無料": [
        "中小企業がNotionを使い始めるなら、このテンプレートから始めよ",
        "Notionの無料テンプレート10選【中小企業の業務にそのまま使えるもの限定】",
    ],
    "Canva Pro 中小企業 デザイン 費用対効果": [
        "Canva Proは月1,500円の価値があるか？中小企業目線で正直に評価する",
        "デザイナーなしでプロ品質の資料を作る方法【Canva Proを使った結果】",
    ],
    "AIツール 中小企業 比較 おすすめ 2026": [
        "中小企業のAI活用、何から始める？ChatGPT・Notion・Canvaを経営者目線で比較",
        "2026年版：中小企業が最初に導入すべきAIツール3選と選び方",
    ],
}

# DXツール記事：キーワード → 自然言語タイトルのマッピング
DX_NATURAL_TITLES = {
    "freee 中小企業 クラウド会計": [
        "freeeで経理を自動化した中小企業の話【月次作業が3日→1日になった理由】",
        "freee会計は本当に使えるのか？ITが苦手な経営者が試してわかったこと",
    ],
    "マネーフォワード クラウド 中小企業": [
        "マネーフォワード クラウドで経理・給与・経費をまとめて自動化した話",
        "バックオフィスを1本化するなら？マネーフォワード クラウドを中小企業目線で解説",
    ],
    "Chatwork 社内チャット 中小企業": [
        "社内メールをやめてChatworkにしたら、残業が週5時間減った話",
        "Chatworkって本当に使いやすい？メール文化の中小企業が導入してみた結果",
    ],
    "バックオフィス 効率化 ツール 比較 中小企業": [
        "バックオフィスを最短で効率化するならどれ？freee・マネーフォワード・Chatworkを比較した",
        "中小企業のDXはどこから手をつける？3つのツールを経営者目線で徹底比較",
    ],
}


def _build_latest_news_section(keyword: str, latest_ai_info: dict) -> str:
    """ai_saas 用：Geminiから取得した最新情報セクションを生成"""
    if not latest_ai_info:
        return ""

    year = datetime.now().year
    lines = [f"## {year}年最新アップデート情報\n\n"]

    if latest_ai_info.get("update_highlight"):
        lines.append(f"**最近の主なアップデート:** {latest_ai_info['update_highlight']}\n\n")

    if latest_ai_info.get("latest_feature"):
        lines.append(f"**注目の新機能:** {latest_ai_info['latest_feature']}\n\n")

    if latest_ai_info.get("business_use_case"):
        lines.append(f"**中小企業での活用例:** {latest_ai_info['business_use_case']}\n\n")

    if latest_ai_info.get("free_vs_paid"):
        lines.append(f"**無料 vs 有料の違い:** {latest_ai_info['free_vs_paid']}\n\n")

    if latest_ai_info.get("caution"):
        lines.append(f"**注意点:** {latest_ai_info['caution']}\n\n")

    lines.append("---\n")
    return "".join(lines)


def generate_seo_article(keyword: str, category: str,
                         affiliates: list = None,
                         feedback_insights: dict = None) -> dict:
    """SEO最適化記事を生成"""

    year = datetime.now().year
    feedback_insights = feedback_insights or {}
    latest_ai_info = feedback_insights.get("latest_ai_info", {})

    # affiliates 引数が渡されなければカテゴリから取得
    if affiliates is None:
        affiliates = get_affiliates_for_category(category)

    # テンプレート選択
    templates = ARTICLE_TEMPLATES.get(category, ARTICLE_TEMPLATES["ai_tools"])
    template = random.choice(templates)

    # タイトル生成 — dx_tools / ai_saas はキャッチーな自然言語タイトルを優先
    if category == "dx_tools" and keyword in DX_NATURAL_TITLES:
        title = random.choice(DX_NATURAL_TITLES[keyword])
    elif category == "ai_saas" and keyword in AI_SAAS_NATURAL_TITLES:
        title = random.choice(AI_SAAS_NATURAL_TITLES[keyword])
    else:
        title = template["title_format"].format(keyword=keyword, year=year)

    # 記事構造に従ってコンテンツ生成
    body_parts = []

    # 導入文（ai_saasは鮮度をアピール）
    if category == "ai_saas" and latest_ai_info.get("update_highlight"):
        body_parts.append(f"""この記事では{year}年最新の**{keyword}**について、実際のビジネス活用を中心に解説します。

{latest_ai_info['update_highlight']}

競合記事との違いは「最新の実態」に基づいている点です。古い情報で判断して損をしないよう、ぜひ最後まで読んでください。

""")
    else:
        body_parts.append(f"""この記事では**{keyword}**について、初心者でも実践できるよう基礎から応用まで解説します。

実際に試してみた経験をもとに、失敗しないためのポイントも含めてお伝えします。

""")

    # 目次
    body_parts.append("## 目次\n")
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
        "dx_hook": "はじめに",
        "user_worries": "よくある悩みと解決策",
        "latest_news": f"{year}年最新アップデート情報",
    }
    for i, section in enumerate(template["structure"], 1):
        title_text = section_titles.get(section, section)
        body_parts.append(f"{i}. {title_text}\n")

    body_parts.append("\n---\n\n")

    # 各セクションのコンテンツ
    for section in template["structure"]:
        if section == "latest_news":
            content = _build_latest_news_section(keyword, latest_ai_info)
        else:
            content = generate_section(section, keyword, category, affiliates)
        body_parts.append(content)

    body = "".join(body_parts)

    # メタ情報
    has_fresh_info = bool(latest_ai_info)
    return {
        "title": title,
        "body": body,
        "keyword": keyword,
        "category": category,
        "char_count": len(body),
        "affiliate_count": len(affiliates),
        "template": template["tone"],
        "target": template["target"],
        "has_fresh_info": has_fresh_info,
        "generated_at": datetime.now().isoformat()
    }


if __name__ == "__main__":
    # テスト生成
    article = generate_seo_article("AI副業 始め方 初心者", "side_hustle")
    print(f"タイトル: {article['title']}")
    print(f"文字数: {article['char_count']}")
    print(f"アフィリエイト数: {article['affiliate_count']}")
    print(f"\n本文（最初の500文字）:\n{article['body'][:500]}")
