"""
note記事 自動生成
戦略：PASONA法則 × ブルーオーシャン × 意思決定支援
構成：Problem → Agitation（統計データ×危機感）→ Solution（AI×節約×投資の三位一体）→ Offer → Narrowing → Action
文字数：2000〜3500文字
"""
import os
import sys
import json
import random
from datetime import datetime
from pathlib import Path

# money_agent をインポートできるようにパスを追加
sys.path.insert(0, str(Path(__file__).parent.parent))

_INSIGHTS_FILE = Path(__file__).parent.parent / "money_agent" / "feedback_insights.json"


def _load_feedback_insights() -> dict:
    try:
        if _INSIGHTS_FILE.exists():
            return json.loads(_INSIGHTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _build_feedback_context(insights: dict) -> str:
    """note記事生成プロンプト用のフィードバックブロック"""
    lines = []
    # noteはプラットフォームキーがないのでx/blueskyの共通知見を使う
    for platform in ("x", "bluesky"):
        data = insights.get(platform, {})
        if data.get("winning_patterns"):
            lines.append(f"【SNS勝ちパターン（{platform}）→ 記事の切り口に活かす】")
            for p in data["winning_patterns"][:2]:
                lines.append(f"・{p}")
            break  # 1プラットフォームで十分

    if insights.get("keyword_strategy", {}).get("hot_topics"):
        lines.append("【直近のホットトピック（SNS分析）】")
        for t in insights["keyword_strategy"]["hot_topics"][:3]:
            lines.append(f"・{t}")

    if insights.get("exploration_mode"):
        lines.append("【探索モード: 今回は定番テーマを外し、全く新しい切り口で記事を構成すること】")

    return "\n".join(lines)

# ─────────────────────────────────────────
# 記事テーマ（カテゴリ×ブルーオーシャントピック）
# 競合が少ない × 読者ニーズが高い × 差別化できるニッチを選定
# ─────────────────────────────────────────
ARTICLE_THEMES = {
    "ai_blue_ocean": {
        "label": "AI×ブルーオーシャン副業",
        "topics": [
            "AI×音声配信で稼ぐ：スタンドFMでフォロワー0から月収を得た方法",
            "Gemini AIで「LINE副業」を自動化したら月2万円になった話",
            "AI×Kindle出版：1週間で電子書籍を出版して稼ぐ完全マニュアル",
            "AIで「ペット専門アフィリエイト」を始めたら競合がほぼいなかった件",
            "ChatGPT×Canvaで「シニア向けSNS運用代行」という無競争市場を発見",
            "AI翻訳×海外アフィリエイト：日本語話者だけが気づけない稼ぎ方",
        ],
    },
    "ai_tools": {
        "label": "AIツール×実践活用",
        "topics": [
            "Gemini APIを無料で使ってコンテンツを自動生成する方法",
            "NotebookLMで学習効率を10倍にした具体的な使い方",
            "AI音声生成ツールで「ながら聴きコンテンツ」を作る副業術",
            "Canva AI×noteで有料マガジンを作る全手順【月3万円達成】",
            "AIで「読書要約サービス」を副業化したらニーズが爆発した話",
        ],
    },
    "side_hustle": {
        "label": "競合ゼロの副業戦略",
        "topics": [
            "「好きなこと×AI」で無競争市場を作る3ステップ",
            "スマホ×AIだけで始めた副業が月1万円を超えた記録",
            "副業で稼げない人の共通点：競合が多い市場を選んでいる",
            "地方×AI副業：都市部の人が気づいていないローカルニッチ戦略",
            "主婦×AIライティング：育児の隙間時間に月2万円稼ぐ現実",
        ],
    },
    "beginners_income": {
        "label": "初心者×AI収益化",
        "topics": [
            "副業歴0日の会社員がAIで最初の1万円を稼ぐまでの全記録",
            "スキルなし×AIで始めたアフィリエイトが3ヶ月で黒字化した理由",
            "ランサーズでAIを使った提案をしたら採用率が3倍になった話",
            "note有料記事×AI：初投稿から売れた記事の構成を全公開",
            "副業初心者がAIを使って「やること」を絞った結果",
        ],
    },
    "experience": {
        "label": "リアル体験談×AI転換期",
        "topics": [
            "副業で3ヶ月ゼロ円だった私がAIで月1万円に転換した話",
            "AIに頼りすぎて失敗したこと・学んだこと・今やっていること",
            "月収0円から脱出できた理由：ブルーオーシャンを見つけた瞬間",
            "Gemini無料プランだけで副業を始めた1ヶ月間の正直な記録",
            "副業詐欺を避けて本当に稼げる方法にたどり着くまで",
        ],
    },
    "niche_content": {
        "label": "ニッチ×コンテンツ収益化",
        "topics": [
            "「40代の転職×AI」という誰も書いていないニッチで稼ぐ方法",
            "趣味のゲーム攻略×AIアフィリエイトで月5万円を狙う戦略",
            "AIで「地元グルメ情報」を発信したら地方で独占市場ができた",
            "「資格×AI解説」という競合がほぼいない収益化ニッチの作り方",
            "育児日記×AIアフィリエイト：ママブロガーが気づいていない収益化",
        ],
    },
    # ─── 新規追加：泥臭い現場×AI ───
    "muddy_niches": {
        "label": "泥臭い現場×AI革命",
        "topics": [
            "地方移住×AI副業：田舎暮らしで月5万円を稼ぐ完全ロードマップ",
            "介護職×AI：「時間がない・稼げない」を同時に解決した私の方法",
            "農家×AI：農業の知識をnoteで売ったら都市部の人に刺さりすぎた話",
            "工場勤務×AIライティング：夜勤明けの2時間で月2万円を作った記録",
            "地方の美容師×AI：指名ゼロだった私がSNS集客で予約を埋めた方法",
            "シングルマザー×AI副業：子供が寝た後の1時間で収入源を作った話",
            "50代の再雇用組×AI：デジタル苦手でも月1万円を稼げた理由",
        ],
    },
    # ─── 楽天アフィリエイト商品ランキング ───
    "rakuten_ranking": {
        "label": "楽天市場おすすめランキング",
        "category": "rakuten",
        "topics": [
            "楽天市場で本当に買ってよかったスキンケア商品ランキングTOP5【レビュー4点以上限定】",
            "一人暮らしに必要なキッチン用品を楽天で揃えた話【コスパ最強5選】",
            "楽天スーパーSALEで毎回買うリピート確定アイテム5選",
            "プレゼントに迷ったら楽天これ買っとけランキング【予算別】",
            "楽天ポイントで損しない買い方と実際に買ってよかった健康食品TOP5",
            "在宅ワーカーが楽天で揃えたデスク環境アイテムTOP5",
            "ペットを飼い始めて楽天で買って正解だったグッズランキング",
        ],
    },
    # ─── 新規追加：AI×節約×投資の三位一体 ───
    "trinity_lifestyle": {
        "label": "AI×節約×投資ライフスタイル",
        "topics": [
            "AIで月3万稼いで楽天ポイントで節約して新NISAに回す一気通貫の設計図",
            "「副業→節約→投資」の三位一体でFIREに近づく最短ルート",
            "楽天経済圏×AI副業：ポイント還元率を最大化しながら投資元本を作る方法",
            "SBI証券×新NISA×AI副業：月5万円の不労所得ルートを最速で作る手順",
            "AI副業で稼いだお金を「増やす仕組み」に変える3ステップ",
            "お金の三角形（稼ぐ×守る×増やす）をAIで全自動化した話",
            "副業収益を投資に回したら3年で資産が〇〇万円になった計算書",
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


def search_web(query: str, num_results: int = 6) -> str:
    """Web検索でトレンド情報を取得（DuckDuckGo → Google フォールバック）"""
    import re
    import html as html_module
    import urllib.parse

    try:
        import requests
    except ImportError:
        return ""

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    }

    def _strip_tags(text: str) -> str:
        return html_module.unescape(re.sub(r'<[^>]+>', '', text)).strip()

    # ── DuckDuckGo HTML（Botブロックなし）──
    try:
        encoded = urllib.parse.quote(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded}&kl=jp-jp"
        resp = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query, "kl": "jp-jp"},
            headers=headers,
            timeout=12,
        )
        body = resp.text

        results = []
        # タイトル: <a class="result__a">
        for m in re.findall(r'<a[^>]*class="result__a"[^>]*>(.*?)</a>', body, re.DOTALL)[:num_results]:
            text = _strip_tags(m)
            if text and len(text) > 4:
                results.append(f"・{text}")

        # スニペット: <a class="result__snippet">
        for m in re.findall(r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>', body, re.DOTALL)[:num_results]:
            text = _strip_tags(m)
            if text and len(text) > 20:
                results.append(f"  → {text[:200]}")

        if results:
            print(f"  DuckDuckGo検索取得: {len(results)}件")
            return "\n".join(results[:12])
        else:
            print("  DuckDuckGo: スニペット未取得、Googleを試みます")
    except Exception as e:
        print(f"  DuckDuckGo失敗: {e}")

    # ── Google フォールバック ──
    try:
        encoded = urllib.parse.quote(query)
        url = f"https://www.google.com/search?q={encoded}&num={num_results}&hl=ja&gl=jp"
        resp = requests.get(url, headers=headers, timeout=10)
        body = resp.text

        results = []
        for m in re.findall(r'<h3[^>]*>(.*?)</h3>', body, re.DOTALL)[:num_results]:
            text = _strip_tags(m)
            if text and len(text) > 5:
                results.append(f"・{text}")
        for m in re.findall(r'<div[^>]*class="[^"]*VwiC3b[^"]*"[^>]*>(.*?)</div>', body, re.DOTALL)[:num_results]:
            text = _strip_tags(m)
            if text and len(text) > 20:
                results.append(f"  → {text[:200]}")

        if results:
            print(f"  Google検索取得: {len(results)}件")
            return "\n".join(results[:12])
        else:
            print("  Google検索: スニペット未取得（スキップ）")
            return ""
    except Exception as e:
        print(f"  Google検索失敗（スキップ）: {e}")
        return ""


def generate_rakuten_article(theme: dict, api_key: str) -> dict:
    """楽天市場商品ランキング記事をnote向けに生成する"""
    try:
        import sys, os
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from money_agent.rakuten_product_article import fetch_rakuten_products, ARTICLE_CATEGORIES, inject_product_urls
        from money_agent.gemini_client import generate as gemini_generate
        import random as _random

        topic    = _random.choice(theme["topics"])
        category = _random.choice(ARTICLE_CATEGORIES)
        products = fetch_rakuten_products(category["genre_id"], hits=10)

        if len(products) < 3:
            return {}

        products_text = "\n".join(
            f"{i+1}. {p['name'][:50]} / {p['price']}円 / レビュー{p['review_count']}件({p['review_avg']}点)"
            for i, p in enumerate(products[:5])
        )

        year = datetime.now().year
        prompt = f"""noteで「{topic}」という記事を書いてください。

【楽天市場 人気商品リスト（{category['name']}）】
{products_text}

【ルール】
- 文字数: 1500〜2500字
- noteらしい一人称の体験談風（「〜してみた」「〜だった」）
- 商品リストを自然な形でランキング記事に組み込む
- 各商品に「[商品名を見る](PRODUCT_URL_PLACEHOLDER_0)」〜「(PRODUCT_URL_PLACEHOLDER_4)」形式でリンクを入れる
- 楽天ポイント・コスパ・使ってみた感想を盛り込む
- 最後に「楽天市場で探す」CTAを入れる
- Markdown形式、## ###を使う
- {year}年の情報として書く
- Markdownのみ出力（前置き不要）"""

        body = gemini_generate(prompt, temperature=0.75) or ""

        # Gemini失敗時はモック記事にフォールバック
        if not body.strip():
            year = datetime.now().year
            lines = [f"# {topic}\n"]
            lines.append(f"楽天市場で{category['name']}の人気商品を調べてみました。\n")
            for i, p in enumerate(products[:5], 1):
                lines.append(f"## {i}位: {p['name'][:40]}")
                lines.append(f"**価格**: {p['price']}円 / **レビュー**: {p['review_count']}件({p['review_avg']}点)\n")
                lines.append(f"[楽天市場で見る](PRODUCT_URL_PLACEHOLDER_{i-1})\n")
            lines.append("## まとめ\n楽天市場で高評価の商品をご紹介しました。ポイントも貯まるのでぜひチェックしてみてください。")
            body = "\n".join(lines)

        body = inject_product_urls(body, products)

        title = topic
        return {
            "title":   title,
            "body":    body,
            "label":   theme["label"],
            "chars":   len(body),
            "source":  "rakuten_api",
            "tags":    ["楽天市場", "おすすめ", category["name"], "アフィリエイト"],
        }
    except Exception as e:
        print(f"[note/rakuten] 生成エラー: {e}")
        return {}


def generate_with_gemini(theme: dict, api_key: str) -> dict:
    """Gemini APIで記事を生成（PASONA法則 × ブルーオーシャン × 魂の注入）
    情報収集フロー: Google検索（最新トレンド取得）→ Gemini Step1（市場分析）→ Gemini Step2（PASONA記事生成）
    """
    # 楽天ランキングテーマは専用関数で処理
    if theme.get("key") == "rakuten_ranking" or theme.get("category") == "rakuten":
        result = generate_rakuten_article(theme, api_key)
        if result:
            return result
        # 失敗時は通常フローにフォールバック

    try:
        from money_agent.gemini_client import generate as gemini_generate
        import re

        # フィードバックinsights読み込み
        insights         = _load_feedback_insights()
        feedback_context = _build_feedback_context(insights)
        temperature      = insights.get("last_temperature", 0.7)

        topic = random.choice(theme["topics"])

        # ─────────────────────────────────────────
        # STEP0: Web検索で最新トレンド情報を収集（DuckDuckGo → Google）
        # ─────────────────────────────────────────
        search_query = f"{topic} 副業 AI 2024 2025"
        print(f"  Web検索中: {search_query}")
        google_snippets = search_web(search_query)

        # ─────────────────────────────────────────
        # STEP1: ブルーオーシャン分析プロンプト（Google検索結果を注入）
        # コンセプト錬金術：ターゲット × 強み × パワーワード
        # ─────────────────────────────────────────
        google_context = ""
        if google_snippets:
            google_context = f"""
【Google検索で見つかった現在の競合記事・トレンド情報】
{google_snippets}
※上記は現在の競合記事の見出し・スニペット。これを参考にブルーオーシャン角度を見つけること。
"""

        research_prompt = f"""
副業・AI・ライフハック分野のnote記事を書く前に、ブルーオーシャン戦略で市場分析をしてください。

【テーマ】{theme['label']}
【トピック】{topic}
{google_context}
以下を出力してください：
1. 競合が多い「レッドオーシャン」キーワード（3つ）
2. 競合が少ない「ブルーオーシャン」角度（以下の視点で考えること）
   - 「地方×AI」「介護×AI」「農業×AI」「工場×AI」など泥臭い現場にAIを持ち込む切り口
   - 「副業→節約（楽天ポイント最適化）→投資（新NISA）」の三位一体ライフスタイル切り口
   - 上記どちらかに近い、まだ誰も書いていない切り口（2つ）
3. 読者のコメント欄によく出る「パワーワード」（感情を刺激する言葉・3つ）
4. このトピックを読む読者の「本当の悩み」（1文）
5. 読者が「このまま行動しないとどうなるか」を示す統計・数字（実在するデータや社会的事実・1〜2個）
   例：「AIに代替されるリスクが高い職種は全労働者の49%（McKinsey試算）」など

JSON形式のみ出力：
{{"red_ocean": [], "blue_ocean": [], "power_words": [], "real_pain": "", "danger_stats": []}}
"""
        research_text = gemini_generate(research_prompt, use_cache=True, temperature=0.5) or ""
        research_text = research_text.strip()

        # JSONパース試行（失敗してもデフォルト値で続行）
        research = {
            "red_ocean": [],
            "blue_ocean": [topic],
            "power_words": ["稼げない", "続かない", "難しい"],
            "real_pain": "何をやっても稼げない",
            "danger_stats": ["AIに代替されるリスクが高い職種は国内労働者の約49%（野村総研試算）"],
        }
        try:
            json_match = re.search(r'\{.*\}', research_text, re.DOTALL)
            if json_match:
                research = json.loads(json_match.group())
        except Exception:
            pass

        blue_angle   = research.get("blue_ocean", [topic])[0] if research.get("blue_ocean") else topic
        power_words  = "、".join(research.get("power_words", ["稼げない", "続かない"])[:3])
        real_pain    = research.get("real_pain", "何をやっても稼げない")
        danger_stats = "\n".join(f"・{s}" for s in research.get("danger_stats", [])[:2])

        # ─────────────────────────────────────────
        # ポートフォリオから案件を2件選択（1記事2案件で分散）
        # ─────────────────────────────────────────
        _note_theme = theme.get("category", "side_hustle")
        try:
            from money_agent.portfolio_selector import select_programs_for_theme, mark_program_used as _mark_used
            selected_programs = select_programs_for_theme(theme=_note_theme, count=2)
        except Exception:
            selected_programs = []
            _mark_used = None

        # 案件が取得できた場合、プロンプト用にフォーマット
        if len(selected_programs) >= 2:
            prog1, prog2 = selected_programs[0], selected_programs[1]
            prog1_name = prog1["name"]
            prog1_url  = prog1["affiliate_url"]
            prog1_desc = prog1.get("description", "")
            prog2_name = prog2["name"]
            prog2_url  = prog2["affiliate_url"]
            prog2_desc = prog2.get("description", "")
        elif len(selected_programs) == 1:
            prog1 = selected_programs[0]
            prog1_name, prog1_url, prog1_desc = prog1["name"], prog1["affiliate_url"], prog1.get("description", "")
            prog2_name, prog2_url, prog2_desc = "楽天カード", "https://card.rakuten.co.jp/", "ポイント還元率業界最高水準"
        else:
            # フォールバック: 固定案件
            prog1_name, prog1_url, prog1_desc = "楽天カード", "https://rpx.a8.net/svt/ejp?a8mat=4AZMKI+BFEJSI+2HOM+BW8O1&rakuten=y&a8ejpredirect=http%3A%2F%2Fhb.afl.rakuten.co.jp%2Fhgc%2F0ea62065.34400275.0ea62066.204f04c0%2Fa26032392970_4AZMKI_BFEJSI_2HOM_BW8O1%3Fpc%3Dhttps%253A%252F%252Fcard.rakuten.co.jp%252F%26m%3Dhttps%253A%252F%252Fcard.rakuten.co.jp%252F", "ポイント還元率業界最高水準"
            prog2_name, prog2_url, prog2_desc = "楽天証券", "https://www.rakuten-sec.co.jp/", "楽天ポイントで投資できる証券口座"
            _mark_used = None

        # ─────────────────────────────────────────
        # STEP2: PASONA構成 × 魂の注入プロンプト
        # ─────────────────────────────────────────
        pasona_prompt = f"""
あなたはnoteで副業・AI・お金の自由を発信しているクリエイターです。
{feedback_context}

「AI副業で月3万稼ぎ、浮いた時間で節約を最適化し、利益を新NISAに回す」という
一気通貫のライフスタイルを提案しながら、読者の人生の意思決定を支援してください。

【テーマ】{theme['label']}
【トピック（ブルーオーシャン角度）】{blue_angle}
【読者の本当の悩み】{real_pain}
【感情を動かすパワーワード】{power_words}
【行動しないと起きること（統計・数字）】
{danger_stats}
{google_context}

【PASONA構成で記事を書いてください】

# タイトル（30文字以内・「このままだと損する」感が出るタイトル）

## P：Problem（問題提起）
読者が今まさに感じている痛みを「あるある」な状況描写で突く。
「自分のことだ」と思わせる具体的な場面を描く。200文字程度。

## A：Agitation（危機感の具体化）
統計データや社会的事実を使って「このまま行動しないと取り返しがつかない」を伝える。
使うデータ：{danger_stats if danger_stats else "AIに代替されるリスクが高い職種は国内労働者の約49%（野村総研試算）"}
「5年後・10年後の自分」という時間軸で危機感を描く。感情ではなく数字で詰める。300文字程度。

## S：Solution（三位一体の解決策）
「AI副業（稼ぐ）→ 節約最適化（守る）→ 新NISA投資（増やす）」の一気通貫ライフスタイルを提案。
ブルーオーシャン角度（{blue_angle}）を起点に、以下の流れで解説する：
1. AIで月〇〇円の収益を作る具体的な手順（ステップ形式）
2. 浮いた時間・お金を楽天カードのポイント還元や固定費削減に回す方法
3. 残った利益をSBI証券の新NISAで複利運用する最初の一歩
各ステップは「今日からできる」行動レベルに落とす。700文字程度。

## O：Offer（人生の変化を数字で見せる）
この三位一体を1年続けると「何が・どう変わるか」をビフォーアフターで見せる。
例：「副業月2万 + 節約月1万 + 投資利回り〇% = 1年後に資産〇〇万円増」のような計算。
読者が「やらない理由がなくなる」状態にする。400文字程度。

## N：Narrowing（「あなた」への絞り込み）
「特にこういう状況の人にこそ今すぐやってほしい」という絞り込み。
「今やらないと5年後の自分が後悔する理由」を感情と数字で伝える。
「この記事を読んでいる今が一番若い」という緊迫感で締める。200文字程度。

## A：Action（最初の1歩）
「今日中にできる具体的な行動を1つだけ」提示する（ハードル最低限）。
楽天カード申込 or Geminiのアカウント作成 or SBI証券の口座開設 のどれか1つ。
「詳しい設定方法・アフィリエイトリンクはプロフィールのリンクにまとめています」で締める。150文字程度。

【自分事化ルール（必ず守ること）】
- 読者が「自分のことだ」と思う描写を各セクションに1箇所以上
- 「私も最初は〜でした」という等身大の体験談を1箇所
- 数字（月収・時間・日数・割合・資産額）を最低5箇所
- 「〜だと思います」より「〜です」と断言する
- AI生成っぽい無機質な文章NG。口語・感情・熱量を込める
- パワーワード（{power_words}）を自然に使う

【アフィリエイトブリッジルール（必ず守ること）】
楽天カードとSBI証券は「決済手段」「投資口座」として紹介しない。
「AI副業を加速させるためのプロツール」として再定義して差し込むこと。

■ 案件1「{prog1_name}」の再定義：
  {prog1_desc}
  読者の「副業を加速させるプロツール」として自然に差し込む。

■ 案件2「{prog2_name}」の再定義：
  {prog2_desc}
  読者の「お金を守る・増やす仕組み」として自然に差し込む。

■ 差し込みタイミング（以下の文脈の直後に1〜2文で差し込む）：
  【{prog1_name}を差し込む文脈】
  ・副業の経費管理・ツール代・コスト削減に触れた段落の直後
  ・「どのサービスを選べばお得か？」という読者の疑問が生まれる瞬間

  【{prog2_name}を差し込む文脈】
  ・収益シミュレーション・副業の出口戦略・お金の使い道に触れた段落の直後
  ・「稼ぐだけでは意味がない、増やす仕組みも必要」という文脈

■ CTAの書き方（リンク文言）：
  NG：「{prog1_name}の詳細を確認する」「{prog2_name}に申し込む」
  OK：ベネフィット主語の能動表現（例：「副業コストを{prog1_name}でゼロに近づける」）

■ アフィリエイトリンクの書き方：
  <a href="{prog1_url}" rel="nofollow">▶ {prog1_name}を使って副業コストを削減する</a>
  <a href="{prog2_url}" rel="nofollow">▶ {prog2_name}で副業収益を増やし続ける仕組みをつくる</a>

■ 配置・言及ルール：
  ・1記事につき各案件1回が上限（しつこくしない）
  ・体験談形式で：「実際に使ってから〇〇が変わった」
  ・締めは必ず「詳しい設定手順とリンクはプロフィールのリンクページにまとめています」

【技術ルール】
- 全体2000〜3500文字
- Markdown形式（見出しは##を使用）
- タイトル行（# から始まる）から本文まで、記事本文のみ出力

記事本文のみ出力してください。前置きや説明は不要です。
"""
        full_text = gemini_generate(
            pasona_prompt, use_cache=False, temperature=temperature
        ) or ""
        full_text = full_text.strip()

        # タイトルと本文を分離
        lines = full_text.split("\n")
        title = lines[0].lstrip("# ").strip() if lines else topic
        body  = "\n".join(lines[1:]).strip() if len(lines) > 1 else full_text

        print(f"  ブルーオーシャン角度: {blue_angle}")
        print(f"  パワーワード: {power_words}")
        print(f"  危機感データ: {danger_stats[:80]}...")

        # 使用した案件をポートフォリオのクールダウン開始
        if _mark_used and selected_programs:
            for sp in selected_programs:
                try:
                    _mark_used(sp["id"])
                except Exception:
                    pass

        return {
            "theme":     theme["key"],
            "label":     theme["label"],
            "title":     title,
            "body":      body,
            "chars":     len(full_text),
            "source":    "gemini_pasona",
            "programs":  [p["id"] for p in selected_programs],
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
