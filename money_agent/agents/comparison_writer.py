"""
比較まとめ記事ライター
pending/ にある複数記事を横断した比較記事を生成する
テーマ: 「バックオフィスを最短で効率化するならどれ？」
"""
import json
import os
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent.parent

# ── ツール別スペックデータ（比較表用）──────────────────────────
DX_TOOL_SPECS = {
    "freee 中小企業 クラウド会計": {
        "name": "freee会計",
        "area": "会計・確定申告・請求書",
        "price": "無料〜2,980円/月",
        "difficulty": "★★☆☆☆",
        "trial": "30日間無料",
        "best_for": "個人事業主・従業員〜30名",
        "strength": "確定申告の完全自動化・e-Tax対応",
        "weak": "多機能ゆえ初期設定に1〜2時間必要",
        "affiliate_key": "freee_accounting",
    },
    "マネーフォワード クラウド 中小企業": {
        "name": "マネーフォワード クラウド",
        "area": "給与・経費・請求書・会計を一元管理",
        "price": "無料〜3,980円/月",
        "difficulty": "★★★☆☆",
        "trial": "30日間無料",
        "best_for": "従業員10〜100名の中小企業",
        "strength": "バックオフィス全体を1プラットフォームで完結",
        "weak": "機能が多く全部使いこなすまで時間がかかる",
        "affiliate_key": "moneyforward_cloud",
    },
    "Chatwork 社内チャット 中小企業": {
        "name": "Chatwork",
        "area": "社内チャット・タスク管理・ファイル共有",
        "price": "無料〜600円/ユーザー/月",
        "difficulty": "★☆☆☆☆",
        "trial": "フリープランあり（永続）",
        "best_for": "メール・電話が多い全規模の会社",
        "strength": "即日導入可能・既読確認でメール往来が激減",
        "weak": "会計・経費機能はない（コミュニケーション専門）",
        "affiliate_key": "chatwork",
    },
}

# ── アフィリエイトリンク ───────────────────────────────────────
TOOL_LINKS = {
    "freee_accounting": {
        "name": "freee会計",
        "url": "https://px.a8.net/svt/ejp?a8mat=3Z1234+FREEE1+0000+0000A",
        "cta": "freeeを30日間無料で試す →",
        "desc": "中小企業・個人事業主向けクラウド会計ソフト。確定申告・帳簿づけをAIが自動化",
    },
    "moneyforward_cloud": {
        "name": "マネーフォワード クラウド",
        "url": "https://px.a8.net/svt/ejp?a8mat=3Z1234+MFWD01+0000+0000A",
        "cta": "マネーフォワード クラウドを無料で試す →",
        "desc": "給与計算・経費精算・請求書をまとめて自動化。連携サービス5,000以上",
    },
    "chatwork": {
        "name": "Chatwork",
        "url": "https://px.a8.net/svt/ejp?a8mat=3Z1234+CWORK1+0000+0000A",
        "cta": "Chatworkを無料で始める →",
        "desc": "国内利用者数No.1のビジネスチャット。メール・電話を減らして社内連絡を効率化",
    },
}


def _build_comparison_body(tool_articles: list) -> str:
    """比較まとめ記事の本文を生成"""
    year = datetime.now().year

    # ツール情報を keyword で引く
    specs = []
    for art in tool_articles:
        kw = art.get("keyword", "")
        spec = DX_TOOL_SPECS.get(kw)
        if spec:
            specs.append(spec)

    # スペックが揃わない場合でも記事は生成する
    if not specs:
        specs = list(DX_TOOL_SPECS.values())

    lines = []

    # ── 導入文 ────────────────────────────────────────────────
    lines.append(f"""この記事では{year}年現在、中小企業のバックオフィス効率化に使われている
**freee会計・マネーフォワード クラウド・Chatwork** の3ツールを比較します。

「どれから始めればいいかわからない」という経営者の方に向けて、
現場目線で選び方を解説します。難しい話は一切しません。

""")

    # ── 目次 ─────────────────────────────────────────────────
    lines.append("""## 目次
1. なぜバックオフィスのDXが急務なのか
2. 3ツールの比較表（一目でわかる）
3. freee会計 ── 会計・確定申告を任せたいなら
4. マネーフォワード クラウド ── バックオフィス全体を一本化したいなら
5. Chatwork ── 社内連絡の無駄をなくしたいなら
6. あなたの会社はどれを選ぶべきか
7. 3ツール共通の始め方
8. おすすめサービス一覧
9. まとめ

---

""")

    # ── 課題提起 ─────────────────────────────────────────────
    lines.append("""## なぜバックオフィスのDXが急務なのか

多くの中小企業の経営者から、こんな声をよく聞きます。

> 「請求書の発行・送付だけで半日が終わる」
> 「給与計算のたびに、担当者が残業している」
> 「社内連絡がメールだらけで、何が決まったかわからない」

これらはすべて、**ツールを変えるだけで解決できる問題**です。

クラウドツールの月額費用は数千円。一方、これらの無駄を放置することで失われる
人件費・時間コストは月数万〜数十万円に上ります。

「ITが苦手だから」という理由で先送りするほど、損失は積み重なります。

---

""")

    # ── 比較表 ───────────────────────────────────────────────
    lines.append("## 3ツールの比較表（一目でわかる）\n\n")
    lines.append("| 項目 | freee会計 | マネーフォワード クラウド | Chatwork |\n")
    lines.append("|------|-----------|--------------------------|----------|\n")

    rows = [
        ("対象業務", "area"),
        ("月額費用", "price"),
        ("導入難易度", "difficulty"),
        ("無料トライアル", "trial"),
        ("向いている規模", "best_for"),
        ("最大の強み", "strength"),
    ]
    # specsが3つ揃っている場合のみ表を作る
    if len(specs) >= 3:
        s0, s1, s2 = specs[0], specs[1], specs[2]
        for label, key in rows:
            lines.append(f"| {label} | {s0.get(key,'-')} | {s1.get(key,'-')} | {s2.get(key,'-')} |\n")
    else:
        for spec in specs:
            for label, key in rows:
                lines.append(f"| {spec['name']} {label} | {spec.get(key,'-')} |\n")

    lines.append("""
**結論を先に言うと:**
- 会計・税務を効率化したい → **freee会計**
- バックオフィス全体を一本化したい → **マネーフォワード クラウド**
- まず社内連絡の無駄をなくしたい → **Chatwork**

どれか1つから始めて、慣れたら他を追加するのがおすすめです。

---

""")

    # ── 各ツール個別解説 ────────────────────────────────────
    tool_details = [
        {
            "title": "freee会計 ── 会計・確定申告を任せたいなら",
            "spec": specs[0] if len(specs) > 0 else DX_TOOL_SPECS[list(DX_TOOL_SPECS.keys())[0]],
            "affiliate_key": "freee_accounting",
            "detail": """銀行口座・クレジットカードと連携すると、**取引が自動で帳簿に記録**されます。
確定申告・消費税申告も、ボタン数回でe-Taxに送信できます。

**こんな会社に特におすすめ:**
- 税理士に毎年高い費用を払っている
- 月末・期末の経理作業で残業が発生している
- 紙の領収書の山に悩んでいる""",
        },
        {
            "title": "マネーフォワード クラウド ── バックオフィス全体を一本化したいなら",
            "spec": specs[1] if len(specs) > 1 else DX_TOOL_SPECS[list(DX_TOOL_SPECS.keys())[1]],
            "affiliate_key": "moneyforward_cloud",
            "detail": """給与計算・経費精算・請求書・会計を**1つのプラットフォームで完結**できます。
データが自動連携されるため、同じ数字を何度も入力する手間がなくなります。

**こんな会社に特におすすめ:**
- 従業員が10名以上いて給与計算が大変
- 経費精算を紙の申請書でやっている
- 複数の管理ソフトを使っていて連携が面倒""",
        },
        {
            "title": "Chatwork ── 社内連絡の無駄をなくしたいなら",
            "spec": specs[2] if len(specs) > 2 else DX_TOOL_SPECS[list(DX_TOOL_SPECS.keys())[2]],
            "affiliate_key": "chatwork",
            "detail": """メール・電話の代わりにチャットを使うと、**返信待ち時間が大幅に短縮**されます。
タスク管理機能もあり、「誰が何を担当しているか」が一目でわかります。

**こんな会社に特におすすめ:**
- 社内連絡がほぼメールで、スレッドが長くなりがち
- 「あの件どうなった？」という確認電話が多い
- リモートワーク・在宅勤務を導入している（または検討中）""",
        },
    ]

    for td in tool_details:
        spec = td["spec"]
        af = TOOL_LINKS.get(td["affiliate_key"], {})
        lines.append(f"""## {td['title']}

{td['detail']}

| 月額費用 | 導入難易度 | 無料トライアル |
|---------|-----------|--------------|
| {spec.get('price', '-')} | {spec.get('difficulty', '-')} | {spec.get('trial', '-')} |

> [{af.get('cta', '詳細を見る →')}]({af.get('url', '#')})

---

""")

    # ── 選び方ガイド ──────────────────────────────────────────
    lines.append("""## あなたの会社はどれを選ぶべきか

迷ったときは、この質問に答えてください。

**Q1. 今一番困っているのはどれですか？**

- 「確定申告・帳簿づけが大変」→ **freee会計**から始める
- 「給与計算・経費精算・請求書がバラバラで管理できない」→ **マネーフォワード クラウド**
- 「社内連絡がメールだらけで非効率」→ **Chatwork**

**Q2. 従業員は何名ですか？**

- 〜5名（個人事業主含む）：freee会計が最もシンプルで使いやすい
- 10〜50名：マネーフォワード クラウドでバックオフィスを統合
- 規模問わず：Chatworkは1名でも100名でも使える

**Q3. DXにかけられる予算は？**

- まず無料から始めたい：Chatwork（フリープラン永続）
- 月5,000円以内：freee会計またはマネーフォワード クラウド（ベーシックプラン）
- しっかり投資したい：マネーフォワード クラウド（統合プラン）

---

""")

    # ── 共通の始め方 ─────────────────────────────────────────
    lines.append("""## 3ツール共通の始め方

どのツールも**最初の手順は同じ**です。

### STEP1：無料トライアルに申し込む（5分）
公式サイトでメールアドレスを入力するだけ。クレジットカード不要のものがほとんどです。

### STEP2：まず1つの業務だけ試す（1日）
全機能を使おうとせず、「請求書だけ」「給与計算だけ」という限定的な使い方から始めましょう。

### STEP3：1週間後に効果を確認する
時間が短縮されているか、ミスが減っているか。数字で確認すると社内説得もしやすくなります。

### STEP4：本格導入・他の機能へ展開
効果を感じたら、他の業務にも広げていきます。

---

""")

    # ── アフィリエイトCTA（全3本）────────────────────────────
    lines.append("## おすすめサービス一覧\n\n")
    for af in TOOL_LINKS.values():
        lines.append(f"""### {af['name']}

**{af['desc']}**

> [{af['cta']}]({af['url']})

---

""")

    # ── まとめ ───────────────────────────────────────────────
    lines.append(f"""## まとめ

バックオフィスのDXは、難しく考える必要はありません。

| 課題 | 最初に試すべきツール |
|------|-------------------|
| 会計・確定申告が大変 | freee会計（30日無料） |
| バックオフィス全体を整理したい | マネーフォワード クラウド（30日無料） |
| 社内連絡・メールを減らしたい | Chatwork（フリープランあり） |

**まずは1つ、今日から無料トライアルを始めてみてください。**

慣れたら次のツールへ。その繰り返しで、気づけばバックオフィスが別物になっています。

最後まで読んでいただきありがとうございました。
""")

    return "".join(lines)


def generate_comparison_article(tool_articles: list = None) -> dict:
    """
    3ツールの比較まとめ記事を生成

    tool_articles: pending記事のリスト（省略時はpending/から自動読み込み）
    Returns: 記事dict（pending保存可能な形式）
    """
    # pending記事の自動読み込み
    if tool_articles is None:
        tool_articles = []
        pending_dir = BASE_DIR / "data" / "pending"
        for f in sorted(pending_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if data.get("category") == "dx_tools":
                    tool_articles.append(data)
            except Exception:
                pass

    if not tool_articles:
        raise ValueError("比較対象の記事が見つかりません（pending/にdx_tools記事が必要です）")

    year = datetime.now().year
    title = f"【{year}年版】バックオフィスを最短で効率化するならどれ？freee・マネーフォワード・Chatwork徹底比較【中小企業向け】"
    keyword = "バックオフィス 効率化 ツール 比較 中小企業"
    body = _build_comparison_body(tool_articles)

    return {
        "title": title,
        "body": body,
        "keyword": keyword,
        "category": "dx_tools",
        "char_count": len(body),
        "affiliate_count": 3,
        "template": "比較まとめ・DXアドバイザーペルソナ",
        "target": "ITに疎い中小企業の経営者（着地点記事）",
        "is_comparison": True,
        "source_articles": [a.get("keyword", "") for a in tool_articles],
        "generated_at": datetime.now().isoformat(),
    }


def run(state: dict = None) -> dict:
    """CEOエージェントから呼び出されるエントリポイント"""
    print("  📝 [ComparisonWriter] 比較まとめ記事を生成中...")

    try:
        article = generate_comparison_article()

        # pendingに保存
        from money_agent.approval_flow import save_pending
        path = save_pending(article)

        print(f"  ✅ [ComparisonWriter] 生成完了: {article['title'][:50]}...")
        print(f"     文字数: {article['char_count']} / 保存先: {path}")
        return {"status": "ok", "article": article, "path": path}
    except Exception as e:
        print(f"  ❌ [ComparisonWriter] 失敗: {e}")
        return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    result = run()
    if result["status"] == "ok":
        art = result["article"]
        print(f"\nタイトル: {art['title']}")
        print(f"文字数: {art['char_count']}")
        print(f"\n本文（先頭500文字）:\n{art['body'][:500]}")
