"""
note記事 自動生成
戦略：AIツール / 副業の始め方 / 初心者向け稼ぎ方 / 体験談 / 失敗談
構成：タイトル → 導入 → 背景 → 解決方法 → 具体例 → まとめ
文字数：1500〜3000文字
"""
import os
import random
from datetime import datetime

# ─────────────────────────────────────────
# 記事テーマ（カテゴリ×トピック）
# ─────────────────────────────────────────
ARTICLE_THEMES = {
    "ai_tools": {
        "label": "AIツールの使い方",
        "topics": [
            "Gemini APIを無料で使ってコンテンツを自動生成する方法",
            "ChatGPTとGeminiの違い、初心者はどちらを選ぶべきか",
            "AI画像生成ツールの使い方と副業への活用法",
            "Canva AIで誰でもプロ並みのデザインが作れる理由",
            "無料AIツール5選：今すぐ副業に使えるものだけ厳選",
        ],
    },
    "side_hustle": {
        "label": "副業の始め方",
        "topics": [
            "会社員が副業を始める前に知っておくべき3つのこと",
            "スマホだけで始められる副業5選【初心者向け】",
            "副業で月3万円稼ぐまでにやったこと全部話す",
            "在宅副業の選び方：失敗しない3つの基準",
            "副業初心者がやりがちな3つの失敗と回避方法",
        ],
    },
    "beginners_income": {
        "label": "初心者向けの稼ぎ方",
        "topics": [
            "スキルなしでも稼げる？ポイ活で月1万円の現実",
            "アフィリエイト初心者が最初の1円を稼ぐまでの道のり",
            "ランサーズ・クラウドワークスで最初の案件を取る方法",
            "AI記事作成で稼ぐ方法：実際の単価と作業量を公開",
            "note有料記事を売るための3つのコツ",
        ],
    },
    "recommended": {
        "label": "実際に使ってよかったサービス",
        "topics": [
            "Gemini無料プランで副業が変わった話【実体験】",
            "使って1ヶ月でわかったAIライティングツールの本音",
            "副業で実際に稼いだ方法とツールを全部公開する",
            "初心者でも使えた自動化ツール3選【コスパ最高】",
        ],
    },
    "experience": {
        "label": "失敗談・体験談",
        "topics": [
            "副業で3ヶ月間全く稼げなかった理由と転機",
            "AIに頼りすぎて失敗した話：自動化の落とし穴",
            "月収0円から1万円になるまでにやったこと・やめたこと",
            "副業詐欺に騙されかけた話：見分け方を教えます",
        ],
    },
}

# ─────────────────────────────────────────
# テンプレート記事（APIなしでも動く）
# ─────────────────────────────────────────
TEMPLATE_ARTICLES = [
    {
        "theme": "ai_tools",
        "title": "Gemini APIを無料で使ってコンテンツを自動生成する方法",
        "body": """## こんな悩みはありませんか？

「副業でコンテンツを作りたいけど、毎回一から文章を書くのが大変…」

「AIを使えば楽になるって聞いたけど、APIとか難しそうで手が出せない」

この記事では、Googleが提供するGemini APIを**完全無料**で使って、コンテンツ制作を自動化する方法をわかりやすく解説します。

---

## なぜ多くの人がAI活用に失敗するのか

AIツールを副業に使いたくても、こんな壁にぶつかる人が多いです。

- 「ChatGPT Plusは月20ドルかかる」
- 「APIって何？プログラミングの知識が必要？」
- 「使い方がわからないまま時間だけが過ぎる」

実は、**GeminiのAPIは1日1,500回まで完全無料**で使えます。
しかもセットアップはたった10分で完了します。

---

## Gemini APIを無料で使う3ステップ

### ステップ1：APIキーを取得する

1. Google AI Studio（https://aistudio.google.com）にアクセス
2. Googleアカウントでログイン
3. 「Get API Key」をクリック
4. キーが表示されたらコピーして保存

### ステップ2：Pythonに設定する

```python
pip install google-genai
```

環境変数に設定するだけです。

```
GEMINI_API_KEY=あなたのAPIキー
```

### ステップ3：記事の文章を自動生成する

以下のコードで、トピックを指定するだけで記事が自動生成されます。

```python
from google import genai
client = genai.Client(api_key="your_key")
response = client.models.generate_content(
    model="gemini-2.0-flash-lite",
    contents="副業初心者向けにAIツールの活用法を800字で書いて"
)
print(response.text)
```

---

## 実際にやってみた結果

この方法を使って、1日10記事分のネタ出しと下書きを**30分以内**に終わらせています。

以前は1記事に2〜3時間かかっていたので、作業時間が**約80%削減**されました。

ポイントは「完璧な文章をAIに求めない」こと。
AIに下書きを作らせて、自分で少し手直しするのが一番効率的です。

---

## まとめ：今日から始められます

- Gemini APIは**無料**で使える
- セットアップは**10分**で完了
- 1日1,500回まで使い放題

まずは無料でAPIキーを取得して、小さく試してみてください。
AIを味方にすれば、副業のコンテンツ制作が格段に楽になります。

使ってよかったツールや詳しい活用法は、プロフィールのリンクにまとめています。ぜひ参考にしてみてください。""",
    },
    {
        "theme": "side_hustle",
        "title": "副業で月3万円稼ぐまでにやったこと全部話す",
        "body": """## 「副業で稼ぐ」は本当に難しいのか

「副業を始めたけど全然稼げない」
「何をやればいいかわからない」

そんな声をよく聞きます。

実は私も最初の2ヶ月間、ほぼ収益ゼロでした。
でも3ヶ月目から少しずつ形になり始め、今では月3万円以上を安定して稼げています。

この記事では**実際にやったこと・失敗したこと**を包み隠さず話します。

---

## 最初に失敗した理由

正直に言うと、最初は「簡単に稼げる」という甘い考えで始めました。

- ブログを作ったけど3記事で挫折
- アフィリエイトに申し込んだけど何を紹介すればいいかわからない
- 動画編集を試みたけどソフトが難しすぎてやめた

失敗の原因は一つです。**「何でもやろうとしすぎた」**こと。

---

## 転機になった3つの気づき

### 気づき1：得意なことに絞る

私の場合、文章を書くのは苦じゃなかった。
だからライティング系に絞って集中しました。

### 気づき2：単価より「量をこなせるか」を重視

最初は単価1円でも、100記事書けば1万円。
クオリティより量を優先して、まずスピードを上げました。

### 気づき3：AIを使って作業時間を半分にした

Geminiを使い始めてから、1記事の作成時間が**2時間→40分**になりました。
これが一番の転機でした。

---

## 実際の月収推移

| 月 | 作業時間 | 収益 |
|---|---|---|
| 1ヶ月目 | 20時間 | 800円 |
| 2ヶ月目 | 25時間 | 3,200円 |
| 3ヶ月目 | 30時間 | 12,000円 |
| 4ヶ月目 | 25時間 | 31,500円 |

作業時間が増えたのに収益が大きく伸びたのは、**AIを使い始めたタイミング**と完全に一致しています。

---

## まとめ：月3万円は「特別なスキル」は不要

- 最初は1つのジャンルに絞る
- 量をこなしてスピードを上げる
- AIを積極的に活用する

この3つだけで、私は月3万円を達成できました。

もし今「全然稼げない」と感じているなら、まず**AIツールの活用**から始めてみてください。
使っているツールの詳細はプロフィールにまとめています。""",
    },
    {
        "theme": "beginners_income",
        "title": "ランサーズ・クラウドワークスで最初の案件を取る方法",
        "body": """## 「登録したけど仕事が取れない」は当たり前

クラウドソーシングに登録したのに、
全然案件が取れない…という経験はありませんか？

実はこれ、初心者の**90%が通る壁**です。

この記事では、実際に最初の案件を取るために私がやった方法を具体的に紹介します。

---

## なぜ初心者は案件が取れないのか

理由はシンプルです。

**実績がないから信頼されない。**
でも、実績を作るには案件を取る必要がある。
この矛盾が初心者を苦しめます。

でも、ちゃんと抜け道があります。

---

## 最初の案件を取る3つの方法

### 方法1：単価を下げてでも実績を作る

最初の3件は「実績作り」と割り切って、相場より安い金額で提案します。

- 相場3,000円の案件 → 1,500円で提案
- 「実績を作るために全力で取り組みます」と一言添える

これだけで採用率が大幅に上がります。

### 方法2：提案文に「具体性」を入れる

多くの人がやりがちな失敗が、テンプレートそのままの提案文。

クライアントは毎日何十件もの提案を見ています。
目を引くには**「この仕事、ちゃんと理解してます」**が伝わる具体性が必要。

例：
> 「御社のSNS投稿を拝見しました。特に〇〇の投稿のような、日常に溶け込む自然な表現が得意です」

### 方法3：プロフィールを「ポートフォリオ」にする

実績がなくても、自分で作ったサンプルを載せればOK。

- ブログ記事のサンプル（自分で書いたもの）
- デザインのサンプル（架空でもOK）
- 「こんな仕事ができます」を具体的に示す

---

## 最初の案件を取った後が大事

1件取れたら、**必ず高評価をもらう**ことに全集中してください。

評価が1件あるだけで、次の案件の採用率が3倍以上になります。

---

## まとめ

1. 最初は単価より実績優先
2. 提案文に具体性を入れる
3. プロフィールにサンプルを載せる

クラウドソーシングで稼ぐコツや、実際に使った便利なツールはプロフィールのリンクにまとめています。ぜひ参考にしてください。""",
    },
]


def pick_theme() -> dict:
    """ランダムにテーマを選択"""
    theme_key = random.choice(list(ARTICLE_THEMES.keys()))
    return {
        "key": theme_key,
        **ARTICLE_THEMES[theme_key],
    }


def generate_with_template() -> dict:
    """テンプレートから記事を生成"""
    article = random.choice(TEMPLATE_ARTICLES)
    theme = ARTICLE_THEMES[article["theme"]]
    return {
        "theme":    article["theme"],
        "label":    theme["label"],
        "title":    article["title"],
        "body":     article["body"],
        "chars":    len(article["body"]),
        "source":   "template",
    }


def generate_with_gemini(theme: dict, api_key: str) -> dict:
    """Gemini APIで記事を生成"""
    try:
        from google import genai
        import json, re

        topic = random.choice(theme["topics"])
        client = genai.Client(api_key=api_key)

        prompt = f"""
あなたはnoteで副業・AI・ライフハック情報を発信するブロガーです。

【テーマ】{theme['label']}
【トピック】{topic}

【記事の構成（必須）】
# タイトル（30文字以内・読者の悩みや数字を入れる）

## 導入（読者の悩みや疑問を提示・200文字程度）

## 背景・理由（問題の背景を説明・300文字程度）

## 解決方法（具体的な手順・ステップ形式・600文字程度）

## 具体例（実体験・数字・比較を交えて・400文字程度）

## まとめ（要点3つ＋プロフィールリンクへの誘導・200文字程度）

【ルール】
- 全体1500〜2500文字
- 初心者が読んでもわかる言葉を使う
- 具体的な数字・事例を必ず入れる
- 広告・宣伝っぽい表現は使わない
- まとめの最後は「詳しくはプロフィールリンクにまとめています」で締める
- Markdown形式で出力（見出しは##を使用）

タイトル行（# で始まる1行目）から本文まで、記事本文のみ出力してください。
"""
        resp = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=prompt,
        )
        full_text = resp.text.strip()

        # タイトルと本文を分離
        lines = full_text.split("\n")
        title = lines[0].lstrip("# ").strip() if lines else topic
        body  = "\n".join(lines[1:]).strip() if len(lines) > 1 else full_text

        return {
            "theme":  theme["key"],
            "label":  theme["label"],
            "title":  title,
            "body":   body,
            "chars":  len(full_text),
            "source": "gemini",
        }

    except Exception as e:
        print(f"⚠️ Gemini失敗、テンプレート使用: {e}")
        return generate_with_template()


def generate_article(force_theme: str = None) -> dict:
    """記事を生成（APIキーがあればGemini、なければテンプレート）"""
    if force_theme:
        theme = {"key": force_theme, **ARTICLE_THEMES.get(force_theme, list(ARTICLE_THEMES.values())[0])}
    else:
        theme = pick_theme()

    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        print(f"✨ Gemini APIで記事生成中: [{theme['label']}]")
        return generate_with_gemini(theme, api_key)
    else:
        print(f"📝 テンプレートで記事生成: [{theme['label']}]")
        return generate_with_template()


def preview_article(article: dict):
    """記事プレビュー表示"""
    print("\n" + "=" * 60)
    print(f"📄 [{article['label']}] ({article['chars']}文字) [{article['source']}]")
    print("=" * 60)
    print(f"タイトル：{article['title']}")
    print("─" * 60)
    # 本文は最初の500文字だけ表示
    preview = article["body"][:500]
    print(preview)
    if len(article["body"]) > 500:
        print(f"\n... （残り {article['chars'] - 500}文字）")
    print("=" * 60)


if __name__ == "__main__":
    import sys

    # .env読み込み
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

    theme_arg = sys.argv[1] if len(sys.argv) > 1 else None
    article = generate_article(force_theme=theme_arg)
    preview_article(article)

    # Markdownファイルとして保存
    out_dir = os.path.join(os.path.dirname(__file__), "drafts")
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(out_dir, f"article_{ts}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# {article['title']}\n\n{article['body']}")
    print(f"\n💾 下書き保存: {out_path}")
