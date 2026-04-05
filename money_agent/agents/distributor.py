"""
ディストリビューターエージェント
生成記事をはてな→note→X→Blueskyへ順次配信する

【SNS投稿バリエーション機能】
記事承認時に3パターンの投稿案を sns_drafts/ に自動保存する。
- 共感型: 読者の悩みへの共感から入る
- ベネフィット型: 具体的な利益・効果を訴求
- 権威・信頼型: 比較・プロ視点で信頼を獲得
"""
import sys
import os
import random
import json
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent.parent
ROOT_DIR = BASE_DIR.parent

SNS_DRAFTS_DIR = BASE_DIR / "sns_drafts"
SNS_DRAFTS_DIR.mkdir(exist_ok=True)


def generate_sns_variants(article: dict) -> dict:
    """
    1記事に対して3パターンのSNS投稿案を生成

    Returns:
        {
            "empathy":    {"x": str, "bluesky": str},   # 共感型
            "benefit":    {"x": str, "bluesky": str},   # ベネフィット型
            "authority":  {"x": str, "bluesky": str},   # 権威・信頼型
        }
    """
    keyword = article.get("keyword", "")
    title = article.get("title", "")
    category = article.get("category", "")
    is_comparison = article.get("is_comparison", False)

    # DX・中小企業向けの専用文言
    if category == "dx_tools":
        empathy_x = (
            f"請求書の発行だけで一日が終わる…\n"
            f"そんな経営者の悩み、実はこれ一つで解決します。\n\n"
            f"「{title[:30]}」\n\n"
            f"ITが苦手でも大丈夫。30日間無料で試せます。\n"
            f"詳しくはブログで↓"
        )
        empathy_bsky = (
            f"「毎月の経理作業が重すぎる」という経営者の方へ。\n\n"
            f"クラウドツール1つで解決できます。\n"
            f"難しくありません。一緒に試してみませんか。"
        )

        benefit_x = (
            f"月額数千円で事務員一人分の仕事。\n"
            f"DXって実はコスト削減の最短ルートです。\n\n"
            f"【{keyword}】の記事を書きました。\n"
            f"✅ 無料トライアルあり\n"
            f"✅ 導入事例あり\n"
            f"✅ 選び方ガイドあり"
        )
        benefit_bsky = (
            f"クラウド会計・チャットツールを導入した会社の声：\n"
            f"「月次締めが3日→1日になった」\n"
            f"「メール往来が70%減った」\n\n"
            f"月数千円の投資で、毎月数万円の残業代が減ります。"
        )

        if is_comparison:
            authority_x = (
                f"freeeとマネフォ、どっちがいい？\n"
                f"中小企業が選ぶべき基準をプロの視点でまとめました。\n\n"
                f"「{title[:35]}」\n\n"
                f"比較表あり。あなたの会社に合ったツールがわかります。"
            )
        else:
            authority_x = (
                f"【{keyword}】を導入した中小企業の実例まとめました。\n\n"
                f"・月次締め：3日→1日\n"
                f"・経費精算：紙ゼロ化\n"
                f"・問い合わせ対応：30分→5分\n\n"
                f"選び方のポイントも解説。"
            )
        authority_bsky = (
            f"DXツール選びで迷っている経営者の方へ。\n\n"
            f"freee・マネーフォワード・Chatworkを実際に比較しました。\n"
            f"会社の規模・課題によって最適解が違います。\n"
            f"詳しくはブログで。"
        )

    else:
        # 汎用パターン（dx_tools以外のカテゴリ）
        empathy_x = (
            f"「{keyword}、難しそうで手が出ない…」\n\n"
            f"そんな方のために書きました。\n"
            f"初心者でも再現できる手順付きです。\n\n"
            f"詳しくはブログで↓"
        )
        empathy_bsky = (
            f"「{keyword}に興味あるけど、自分には無理かも」\n\n"
            f"そんなことないです。記事にまとめたのでよかったらどうぞ。"
        )

        benefit_x = (
            f"【新記事】{title[:35]}...\n\n"
            f"✅ 具体的な手順あり\n"
            f"✅ おすすめサービス紹介\n"
            f"✅ 初心者でもすぐ実践可能\n\n"
            f"プロフィールのブログからチェック↓"
        )
        benefit_bsky = (
            f"{keyword}について書きました。\n\n"
            f"無料で始められるものも多いです。\n"
            f"興味ある方はぜひ読んでみてください。"
        )

        authority_x = (
            f"【{keyword}】について徹底解説しました。\n\n"
            f"よくある失敗パターンと、それを避ける方法も書いています。\n"
            f"読んで損なし。"
        )
        authority_bsky = (
            f"「{keyword}」の記事です。\n\n"
            f"実際に試した経験をもとに書きました。\n"
            f"参考になれば嬉しいです。"
        )

    return {
        "empathy": {
            "label": "共感型",
            "x": empathy_x,
            "bluesky": empathy_bsky,
        },
        "benefit": {
            "label": "ベネフィット型",
            "x": benefit_x,
            "bluesky": benefit_bsky,
        },
        "authority": {
            "label": "権威・信頼型",
            "x": authority_x,
            "bluesky": authority_bsky,
        },
    }


def save_sns_drafts(article: dict) -> str:
    """
    SNS投稿バリエーションを sns_drafts/ に保存
    記事承認後に呼び出すことで発信準備を整える

    Returns: 保存ファイルパス
    """
    keyword = article.get("keyword", "unknown").replace(" ", "_")
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{date_str}_{keyword}_sns.json"
    filepath = SNS_DRAFTS_DIR / filename

    variants = generate_sns_variants(article)
    draft = {
        "article_keyword": article.get("keyword", ""),
        "article_title": article.get("title", ""),
        "category": article.get("category", ""),
        "created_at": datetime.now().isoformat(),
        "variants": variants,
        "usage_hint": (
            "投稿前に人間が確認・編集してください。"
            "empathy→共感型 / benefit→ベネフィット型 / authority→権威・信頼型"
        ),
    }
    filepath.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(filepath)


def _generate_sns_texts(article: dict) -> dict:
    """SNS投稿文を生成（X / Bluesky）— 実際の投稿に使う1パターン"""
    keyword = article.get("keyword", "")
    title = article.get("title", "")
    category = article.get("category", "")

    if category == "dx_tools":
        x_options = [
            f"請求書の発行だけで一日が終わる…\nそんな経営者の悩み、実はこれ一つで解決します。\n\n「{title[:30]}」\n\nITが苦手でも大丈夫。30日間無料で試せます。",
            f"月額数千円で事務員一人分の仕事。\nDXって実はコスト削減の最短ルートです。\n\n【{keyword}】\n✅ 無料トライアルあり ✅ 導入事例あり",
            f"freeeとマネフォ、どっちがいい？\n中小企業が選ぶべき基準をプロの視点でまとめました。\n\n比較表あり。",
        ]
        bsky_options = [
            f"「毎月の経理作業が重すぎる」という経営者の方へ。\nクラウドツール1つで解決できます。詳しくはブログで。",
            f"DXツール選びで迷っている中小企業の方向けに比較記事を書きました。\nfreee・マネーフォワード・Chatworkを比較しています。",
        ]
    else:
        x_options = [
            f"✅ 新記事\n\n「{title[:35]}...」\n\n{keyword}について基礎から実践まで解説しました。\nアフィリエイトリンクもまとめてます👇",
            f"💡 {keyword}で収益を上げる方法を記事にまとめました\n\n初心者でも再現できる具体的な手順付き✅",
            f"【新記事】{title[:28]}...\n\n✅ 具体的な手順あり\n✅ おすすめサービス紹介\n✅ よくある失敗も解説",
        ]
        bsky_options = [
            f"新記事を書きました📝\n\n{keyword}についてまとめました。気になる方はぜひ。",
            f"「{keyword}」の記事です。\n\n初心者向けに分かりやすく解説したつもりです。",
        ]

    return {
        "x": random.choice(x_options),
        "bluesky": random.choice(bsky_options),
    }


def run(article: dict, dry_run: bool = False) -> dict:
    """
    ディストリビューター実行
    Returns: 配信結果
    """
    slot = article.get("slot", 0)
    keyword = article.get("keyword", "")
    print(f"\n  📡 [Distributor-{slot}] 「{keyword}」配信開始...")

    results = {"hatena": False, "note": False, "x": False, "bluesky": False}

    # 承認済み記事のSNS投稿バリエーションを保存（発信準備）
    try:
        draft_path = save_sns_drafts(article)
        print(f"  📋 [Distributor-{slot}] SNS投稿案3パターン保存: {Path(draft_path).name}")
    except Exception as e:
        print(f"  ⚠️ [Distributor-{slot}] SNS下書き保存スキップ: {e}")

    if dry_run:
        print(f"  🔍 [Distributor-{slot}] dry-run — 投稿スキップ")
        return results

    # === はてなブログ投稿 ===
    hatena_url = ""
    try:
        sys.path.insert(0, str(ROOT_DIR))
        from hatena_automation.hatena_poster import post_article as hatena_post_article
        title = article.get("title", "")
        body = article.get("body", "")
        category = article.get("category", "")
        results["hatena"] = hatena_post_article(title, body, category=category)
        status = "✅" if results["hatena"] else "❌"
        print(f"  {status} [Distributor-{slot}] はてな投稿")
    except Exception as e:
        print(f"  ❌ [Distributor-{slot}] はてな失敗: {e}")

    # === Google Indexing API（はてな投稿成功時）===
    if results["hatena"]:
        try:
            sys.path.insert(0, str(BASE_DIR))
            from money_agent.google_indexing import notify_article
            idx_result = notify_article(article, hatena_url=hatena_url)
            if idx_result.get("success"):
                print(f"  ✅ [Distributor-{slot}] Googleインデックス通知: {idx_result.get('url','')[:50]}")
            else:
                err = idx_result.get("error", "")
                if "GOOGLE_INDEXING_CREDENTIALS" in err:
                    print(f"  ℹ️ [Distributor-{slot}] Googleインデックス通知スキップ（認証情報未設定）")
                else:
                    print(f"  ⚠️ [Distributor-{slot}] Googleインデックス通知失敗: {err[:60]}")
        except Exception as e:
            print(f"  ⚠️ [Distributor-{slot}] Googleインデックス通知スキップ: {e}")

    # === note投稿 ===
    try:
        from note_automation.note_poster import post_article as note_post_article
        title = article.get("title", "")
        body = article.get("body", "")
        results["note"] = note_post_article(title, body)
        status = "✅" if results["note"] else "❌"
        print(f"  {status} [Distributor-{slot}] note投稿")
    except Exception as e:
        print(f"  ❌ [Distributor-{slot}] note失敗: {e}")

    # === X / Bluesky 投稿 ===
    sns_texts = _generate_sns_texts(article)

    try:
        sys.path.insert(0, str(ROOT_DIR / "x_automation"))
        from x_automation.x_poster import post_with_tweepy, post_with_twikit, post_with_browser
        x_text = sns_texts["x"]
        # tweepy（公式・有料）→ twikit（非公式・無料）→ browser（Playwright）の順でフォールバック
        x_ok = post_with_tweepy(x_text)
        if not x_ok:
            print(f"  ⚠️ [Distributor-{slot}] tweepy失敗、twikit で再試行...")
            x_ok = post_with_twikit(x_text)
        if not x_ok:
            print(f"  ⚠️ [Distributor-{slot}] twikit失敗、ブラウザ で再試行...")
            x_ok = post_with_browser(x_text)
        results["x"] = x_ok
        status = "✅" if x_ok else "❌"
        print(f"  {status} [Distributor-{slot}] X投稿")
    except Exception as e:
        print(f"  ❌ [Distributor-{slot}] X失敗: {e}")

    try:
        from bluesky_automation.bsky_poster import post_to_bluesky
        post_to_bluesky(sns_texts["bluesky"])
        results["bluesky"] = True
        print(f"  ✅ [Distributor-{slot}] Bluesky投稿")
    except Exception as e:
        print(f"  ❌ [Distributor-{slot}] Bluesky失敗: {e}")

    success_count = sum(results.values())
    print(f"  📊 [Distributor-{slot}] 配信完了: {success_count}/4プラットフォーム")
    return results
