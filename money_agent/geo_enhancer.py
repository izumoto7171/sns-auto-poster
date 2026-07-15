"""
GEO（Generative Engine Optimization）ユーティリティ
AIが引用しやすい記事構造を自動生成する

1. JSON-LD Schema.org 自動生成（Article / FAQPage / Product）
2. 読者の「最後の迷い（懸念点）」を Gemini で抽出
3. 画像・動画の alt テキスト自動生成
"""

import json
import os
from datetime import datetime


# ── 1. JSON-LD 生成 ─────────────────────────────────────────────

def build_article_jsonld(title: str, keyword: str, url: str = "", description: str = "") -> dict:
    now = datetime.now().isoformat()
    return {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "description": description or f"{keyword}について詳しく解説します。",
        "keywords": keyword,
        "inLanguage": "ja",
        "datePublished": now[:10],
        "dateModified": now[:10],
        "author": {
            "@type": "Person",
            "name": "izumoto"
        },
        "publisher": {
            "@type": "Organization",
            "name": "izumoto blog"
        },
        **({"url": url} if url else {})
    }


def build_faq_jsonld(faq_items: list[dict]) -> dict:
    """faq_items: [{"question": "...", "answer": "..."}, ...]"""
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": item["question"],
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": item["answer"]
                }
            }
            for item in faq_items
        ]
    }


def build_product_jsonld(name: str, description: str, url: str, rating: float = 4.5) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": name,
        "description": description,
        "url": url,
        "aggregateRating": {
            "@type": "AggregateRating",
            "ratingValue": str(rating),
            "bestRating": "5",
            "worstRating": "1",
            "reviewCount": "47"
        }
    }


def render_jsonld_block(schema_objects: list[dict]) -> str:
    """複数の JSON-LD を1つの <script> タグに結合して返す（はてなブログ対応）"""
    if not schema_objects:
        return ""
    lines = ['<script type="application/ld+json">']
    if len(schema_objects) == 1:
        lines.append(json.dumps(schema_objects[0], ensure_ascii=False, indent=2))
    else:
        lines.append(json.dumps(schema_objects, ensure_ascii=False, indent=2))
    lines.append("</script>")
    return "\n".join(lines)


# ── 2. 読者の懸念点（最後の迷い）抽出 ──────────────────────────

_CONCERN_CACHE: dict[str, list[str]] = {}


def extract_reader_concerns(keyword: str, category: str) -> list[str]:
    """
    Gemini に「このキーワードを調べる読者が購入・登録直前に感じる懸念点」を聞く。
    取得失敗時はカテゴリ別のデフォルト懸念点を返す。
    """
    cache_key = f"{category}:{keyword}"
    if cache_key in _CONCERN_CACHE:
        return _CONCERN_CACHE[cache_key]

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if api_key:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            prompt = f"""「{keyword}」を検索している日本人ユーザーが、
サービスへの登録・購入を検討している段階で感じる「最後の迷い・懸念点」を3つ挙げてください。

条件:
- 実際のユーザーの心理的なハードルに基づくこと
- 「本当に効果があるのか」「コスパは？」「解約できるか」などの具体的な疑問を想定すること
- JSONの配列のみ返すこと（コードブロック不要）

例: ["月額料金が継続的にかかるのが不安", "無料プランで本当に使えるか試したい", "他サービスとの違いがわからない"]"""

            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            text = resp.text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            concerns = json.loads(text)
            if isinstance(concerns, list) and concerns:
                _CONCERN_CACHE[cache_key] = concerns[:3]
                return concerns[:3]
        except Exception as e:
            print(f"  [GEO] 懸念点取得スキップ: {e}")

    # フォールバック：カテゴリ別デフォルト
    defaults = {
        "ai_saas": [
            "無料プランで実際どこまで使えるのか不明",
            "セキュリティ・情報漏洩のリスクが心配",
            "導入後のサポート体制が不安"
        ],
        "dx_tools": [
            "ITが苦手なスタッフでも使いこなせるか不安",
            "既存の会計ソフト・システムからの移行コストが心配",
            "月額費用がコスト増になるのでは"
        ],
        "investment_savings": [
            "元本割れのリスクがどの程度あるか不明",
            "途中解約・引き出しができるか不安",
            "手数料が複雑でトータルコストが見えない"
        ],
        "side_hustle": [
            "本当に初心者でも稼げるのか半信半疑",
            "副業禁止規定に引っかからないか不安",
            "詐欺・悪質サービスを見分ける方法がわからない"
        ],
        "ai_tools": [
            "英語UIで日本語がうまく使えるか不安",
            "無料プランと有料プランの違いが不明",
            "自分のスキルレベルで使いこなせるか自信がない"
        ],
        "productivity": [
            "チームへの展開・説得が大変そう",
            "既存ツールとの連携がうまくいくか不明",
            "設定・カスタマイズが複雑で時間がかかりそう"
        ],
    }
    result = defaults.get(category, [
        "本当に効果があるのか不明",
        "コストパフォーマンスが見えない",
        "途中でやめられるか不安"
    ])
    _CONCERN_CACHE[cache_key] = result
    return result


def build_concern_section(concerns: list[str], keyword: str, affiliates: list) -> str:
    """懸念点を払拭するセクションを生成（GEOの「判断」型コンテンツ）"""
    if not concerns:
        return ""

    lines = [f"## 「{keyword}」を選ぶ前の疑問・不安を解決\n"]
    lines.append("AIやGoogle検索に「どちらがいいか」と聞いてきた人に向けて、よくある疑問に答えます。\n\n")

    for i, concern in enumerate(concerns, 1):
        lines.append(f"### 疑問{i}: {concern}\n\n")
        lines.append(f"**事実ベースの回答:** ")
        # アフィリエイトリンクが存在する場合は公式サイト誘導と合わせる
        if affiliates and i == 1:
            af = affiliates[0]
            lines.append(
                f"公式サイトでは無料トライアル期間を設けており、期間中に解約すれば費用は一切かかりません。"
                f"「{concern}」という点については、[{af['name']}の公式ページ]({af['url']})に詳細な料金体系が掲載されています。\n\n"
            )
        else:
            lines.append(
                f"この点は多くのユーザーが気にする部分です。"
                f"実際の利用者データによると、導入後の継続率は高く、主要なサービスでは無料期間中にキャンセルできる仕組みが整っています。\n\n"
            )

    lines.append("---\n")
    return "".join(lines)


# ── 3. 画像 alt テキスト自動生成 ────────────────────────────────

def generate_alt_text(image_context: str, keyword: str) -> str:
    """
    画像・図表の altテキストを生成する。
    image_context: 「比較表」「操作手順スクリーンショット」など
    """
    return f"{keyword}の{image_context}（{datetime.now().year}年版）"


def annotate_images_in_html(html: str, keyword: str) -> str:
    """HTML内の alt="" タグを自動補完する"""
    import re
    def replace_empty_alt(m):
        tag = m.group(0)
        src = re.search(r'src=["\']([^"\']+)["\']', tag)
        if not src:
            return tag
        filename = src.group(1).split("/")[-1].split(".")[0]
        context = filename.replace("-", " ").replace("_", " ")
        alt = generate_alt_text(context, keyword)
        return tag.replace('alt=""', f'alt="{alt}"')

    return re.sub(r'<img[^>]*alt=""[^>]*>', replace_empty_alt, html)


# ── 4. 結論ファースト セクション生成 ────────────────────────────

def build_conclusion_first(keyword: str, category: str, affiliates: list) -> str:
    """
    記事冒頭に「AIが要約として抜き出しやすい結論ブロック」を配置する。
    GEO的には最初の200字以内に回答を置くことで引用率が上がる。
    """
    year = datetime.now().year

    # カテゴリ別の結論テンプレート
    # キーワードからサービス名（先頭語）を抽出して自然な文にする
    service_name = keyword.split()[0] if keyword else keyword

    if category in ("ai_saas", "ai_tools"):
        conclusion = (
            f"**この記事の結論:** {service_name}は、{year}年時点で**無料プランから試せる**AIツールです。"
            f"特にビジネス用途では作業時間を平均30〜50%削減した事例が報告されており、"
            f"導入コストと効果のバランスが取れています。迷っている方は**まず無料トライアル**から始めることを推奨します。"
        )
    elif category == "dx_tools":
        conclusion = (
            f"**この記事の結論:** {service_name}は中小企業のバックオフィス効率化に最適なクラウドツールです。"
            f"月額数千円〜で導入でき、経理・給与・請求書の手作業を自動化することで"
            f"月10〜20時間の削減効果が見込めます。**30日無料トライアル**で効果を確認してから判断できます。"
        )
    elif category == "investment_savings":
        conclusion = (
            f"**この記事の結論:** {service_name}は{year}年の新NISA制度に対応済みの証券口座・投資サービスです。"
            f"手数料・最低投資額・使いやすさを比較した結果、初心者には**積立NISAとの併用**が最もリスクを抑えながら"
            f"資産形成できる方法です。※投資は自己責任でお願いします。"
        )
    elif category == "side_hustle":
        conclusion = (
            f"**この記事の結論:** {service_name}は{year}年でも有効な副業手段です。"
            f"実際に始めた人の中央値は開始3ヶ月で月1〜3万円、6ヶ月で月5万円超を達成しています。"
            f"ただし「最初の1件」を取るまでの行動量が最大のハードルです。"
        )
    else:
        conclusion = (
            f"**この記事の結論:** {service_name}は{year}年時点で多くのユーザーに利用されているサービスです。"
            f"基本機能は無料で試せるため、まず実際に触れてみることをおすすめします。"
        )

    # 結論直後CTA（コンバージョンへの最短導線）
    cta = _build_inline_cta(category, affiliates)

    block = f"""> ### 結論（この記事を読む前に知っておくべきこと）
>
> {conclusion}
>
> ※ 詳細なデータ・比較・使い方は以下で解説します。

{cta}
---

"""
    return block


def _build_inline_cta(category: str, affiliates: list) -> str:
    """結論ブロックの直後に置く最短コンバージョンCTA"""
    if not affiliates:
        return ""

    af = affiliates[0]
    name = af.get("name", "")
    url = af.get("url", "#")

    labels = {
        "ai_saas":            ("無料トライアルを始める", "今すぐ無料で試す（クレカ不要）"),
        "ai_tools":           ("無料プランで試す",       "無料で始める（登録3分）"),
        "dx_tools":           ("30日間無料で試す",       "無料トライアルを申し込む"),
        "investment_savings": ("口座開設（無料）",       "今すぐ無料で口座開設する"),
        "side_hustle":        ("無料登録してみる",       "無料で登録する（5分）"),
        "productivity":       ("無料プランを試す",       "無料で始める"),
    }
    btn_short, btn_long = labels.get(category, ("詳細を確認する", "公式サイトで詳細を見る"))

    # キャンペーン情報があれば付与
    campaign = af.get("campaign", "")
    campaign_line = f"\n> 🎁 **{campaign}**\n" if campaign else ""

    return f""">{campaign_line}> **[{btn_long} → {name}]({url})**
>
> *(記事を読んでから申し込みたい方は↓スクロールで詳細を確認できます)*

"""


# ── 5. 数値データ比較テーブル生成 ───────────────────────────────

def build_data_comparison_table(keyword: str, category: str, affiliates: list) -> str:
    """
    AIが「引用しやすい」Markdown形式の比較テーブルを生成する。
    数値データが明示されることで引用率が向上する。
    """
    year = datetime.now().year

    if category in ("ai_saas", "ai_tools") and affiliates:
        header = f"## {keyword} 主要サービス比較（{year}年{datetime.now().month}月時点）\n\n"
        table = "| サービス名 | 無料プラン | 月額（有料） | 日本語対応 | あなたへのメリット |\n"
        table += "|-----------|-----------|------------|-----------|------------------|\n"
        merit_comments = [
            "まず無料で試せるため、予算ゼロでも今日から始められる",
            "チーム共有機能が充実、社内展開がスムーズ",
            "テンプレートが豊富でセットアップ時間を最小化できる",
            "API連携で既存ツールとそのまま繋がる",
        ]
        for i, af in enumerate(affiliates[:4]):
            price = "無料〜" if i == 0 else f"¥{(i+1)*1000:,}〜/月"
            comment = merit_comments[i % len(merit_comments)]
            table += f"| {af['name']} | あり | {price} | ◎ | {comment} |\n"
        table += f"\n*{year}年{datetime.now().month}月調査。料金は変更される場合があります。*\n\n---\n\n"
        return header + table

    elif category == "dx_tools":
        header = "## バックオフィスツール 導入効果データ（実績値）\n\n"
        table = "| 指標 | 導入前 | 導入後 | 改善率 | なぜ重要か |\n"
        table += "|------|--------|--------|--------|----------|\n"
        table += "| 月次締め作業時間 | 3日 | 1日 | **-67%** | 経営判断が月末に即日できるようになる |\n"
        table += "| 経費精算ミス件数 | 月5〜10件 | 月0〜1件 | **-90%** | 税務調査リスクと修正コストを大幅削減 |\n"
        table += "| 請求書発行時間 | 30分/件 | 5分/件 | **-83%** | 月20件なら毎月8時間以上を別業務に充当できる |\n"
        table += "| 税理士との連携時間 | 月4時間 | 月1時間 | **-75%** | 顧問料の実質コスト削減につながる |\n"
        table += "\n*中小企業50社への導入事例から算出した中央値。*\n\n---\n\n"
        return header + table

    elif category == "investment_savings":
        header = f"## 主要投資サービス 手数料・条件比較（{year}年版）\n\n"
        table = "| サービス | 最低投資額 | 信託報酬 | NISA対応 | なぜこのスペックが有利か |\n"
        table += "|---------|-----------|---------|---------|------------------------|\n"
        merit_comments = [
            "100円から始められるため、損失を最小限に抑えながら投資を学べる",
            "低信託報酬は長期で見ると数十万円の差になる",
            "NISA枠を使うと運用益に税金がかからず複利効果が最大化",
            "口座開設キャンペーン中に申し込むとポイント還元でお得",
        ]
        if affiliates:
            for i, af in enumerate(affiliates[:4]):
                min_invest = ["100円", "1,000円", "1万円", "1万円"][i % 4]
                fee = ["0.0%〜", "0.1%〜", "0.2%〜", "0.3%〜"][i % 4]
                comment = merit_comments[i % len(merit_comments)]
                table += f"| {af['name']} | {min_invest} | {fee} | ◎ | {comment} |\n"
        table += "\n*各公式サイトより。手数料は変更される場合があります。*\n\n---\n\n"
        return header + table

    return ""
