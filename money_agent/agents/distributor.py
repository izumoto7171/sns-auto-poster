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

SNS_DRAFTS_DIR = BASE_DIR / "data" / "sns_drafts"
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
        # 汎用パターン（dx_tools以外のカテゴリ）— 起承転結構造
        empathy_x = (
            f"「{keyword}、難しそうで手が出ない…」\n\n"
            f"最初の自分もそうだった。\n"
            f"でも実際に試したら、設定5分・無料・日本語OK だった。\n\n"
            f"「なんで今まで後回しにしてたんだろう」と思った。\n\n"
            f"初心者向けに手順まとめました👇"
        )
        empathy_bsky = (
            f"「{keyword}に興味あるけど難しそう」という方へ。\n\n"
            f"実際に触ってみたら思ったよりシンプルでした。\n"
            f"使い方まとめたので、よかったらどうぞ。"
        )

        benefit_x = (
            f"{keyword}を1週間使って変わったこと。\n\n"
            f"・作業時間が半分になった\n"
            f"・「これもできるの？」が毎日あった\n"
            f"・無料プランで十分だと気づいた\n\n"
            f"最初の1歩だけが難しかった。\n\n"
            f"具体的な使い方と選び方まとめました👇"
        )
        benefit_bsky = (
            f"{keyword}について書きました。\n\n"
            f"無料で始められるものも多いです。\n"
            f"興味ある方はぜひ読んでみてください。"
        )

        authority_x = (
            f"「{keyword}で失敗した」という声をよく聞く。\n\n"
            f"原因のほとんどは「選び方を間違えた」こと。\n"
            f"機能より先に「自分の使い方」を決めないと、どれを選んでも続かない。\n\n"
            f"失敗しない選び方の基準まとめました。読んで損なし👇"
        )
        authority_bsky = (
            f"「{keyword}」の記事です。\n\n"
            f"よくある失敗パターンと、それを避ける方法も書いています。\n"
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


def _generate_sns_texts(article: dict, blog_url: str = "") -> dict:
    """SNS投稿文を生成（X / Bluesky）— 実際の投稿に使う1パターン"""
    keyword = article.get("keyword", "")
    title = article.get("title", "")
    category = article.get("category", "")
    _url = ("\n" + blog_url) if blog_url else ""

    # 起承転結テンプレート（起:共感 → 承:状況深掘り → 転:気づき → 結:CTA）
    if category == "dx_tools":
        x_options = [
            (
                f"「月末の経理作業、また徹夜か…」\n\n"
                f"Excel・紙・メールで回してきた経理が、毎月同じところで詰まる。\n"
                f"スタッフに頼みたくても、引継ぎのコストが怖くて任せられない。\n\n"
                f"でも実は、クラウドツール1つで「月次3日→1日」にした会社がある。\n\n"
                f"【{keyword}】の比較・選び方をまとめました👇"
            ),
            (
                f"DXって「大企業がやるもの」と思ってませんか？\n\n"
                f"実は従業員5人以下の会社ほど、効果が出やすい。\n"
                f"理由は「一人が複数の業務を抱えている」から。\n\n"
                f"月数千円のツールで、毎月10時間以上を取り戻せる可能性があります。\n\n"
                f"「{title[:30]}」詳細はブログで👇"
            ),
            (
                f"「ITが苦手だから…」で損してる経営者が多すぎる。\n\n"
                f"freeeもマネーフォワードも、設定は1時間かからない。\n"
                f"操作で詰まったら電話サポートがある。\n\n"
                f"それでも「難しそう」と思うなら、まず30日無料で試すだけでいい。\n\n"
                f"選び方の基準まとめました👇"
            ),
        ]
        bsky_options = [
            (
                f"経理を自動化したい中小企業の方へ。\n\n"
                f"「毎月の締め作業が重すぎる」という声をよく聞きます。\n"
                f"freee・マネーフォワードどちらが合うか、規模別に整理しました。\n\n"
                f"詳しくはブログで。"
            ),
            (
                f"DXツールは「入れて終わり」ではなく「入れてから楽になる」もの。\n\n"
                f"導入後の変化を数字で見せている記事を書きました。\n"
                f"参考になれば嬉しいです。"
            ),
        ]
    elif category == "investment_savings":
        x_options = [
            (
                f"「節約しよう」と思って家計簿アプリを入れた。\n\n"
                f"でも3日でレシート入力が面倒になって放置。\n"
                f"気づいたら4つのアプリを試して、全部続かなかった。\n\n"
                f"原因は「手入力が前提のアプリを選んでいたこと」だった。\n\n"
                f"自動連携型に切り替えたら、登録ゼロで支出が丸見えに。\n\n"
                f"失敗しないアプリの選び方まとめました👇"
            ),
            (
                f"電気代、毎月「高いな」と思いながら何もしてない人へ。\n\n"
                f"新電力への切り替えって、実は15分で完了する。\n"
                f"年間2〜5万円変わることもある。\n\n"
                f"「どこに切り替えればいいかわからない」という人向けに比較しました。\n\n"
                f"詳細はブログで👇"
            ),
            (
                f"「投資は難しい」と思っていた自分が、\n"
                f"100円から始めて半年で月3000円の不労所得を得るまで。\n\n"
                f"難しかったのは「最初の1歩」だけだった。\n\n"
                f"初心者が本当に使いやすいサービス、比較してまとめました。\n"
                f"読んで損なし👇"
            ),
        ]
        bsky_options = [
            (
                f"節約アプリ、続かない理由の9割は「入力の手間」です。\n\n"
                f"自動連携型に絞って比較した記事を書きました。\n"
                f"参考になれば嬉しいです。"
            ),
            (
                f"格安SIMへの切り替え、迷っている方へ。\n\n"
                f"実際に使った感想と、データ通信量別のおすすめをまとめました。\n"
                f"ぜひ読んでみてください。"
            ),
        ]
    elif category == "side_hustle":
        x_options = [
            (
                f"副業を始めようとして、最初の1ヶ月で諦めた。\n\n"
                f"案件がとれない。単価が安すぎる。何をすればいいかわからない。\n"
                f"「自分には向いてないのかも」と思い始めた頃。\n\n"
                f"でも続けた人に共通しているのは「最初の1件をとった後に辞めなかった」こと。\n\n"
                f"初心者が最初の1件をとるまでの手順、まとめました👇"
            ),
            (
                f"「{keyword}」って本当に稼げるの？\n\n"
                f"正直に言います。\n"
                f"最初の3ヶ月は月1〜2万円がリアルなライン。\n"
                f"ただし、正しい方法を知っているかどうかで6ヶ月後が大きく変わる。\n\n"
                f"失敗パターンと成功パターン、両方まとめました👇"
            ),
        ]
        bsky_options = [
            (
                f"副業初心者の方へ。\n\n"
                f"最初の1件がいちばん難しくて、2件目からは急に楽になります。\n"
                f"その「最初の1件」の取り方をまとめた記事です。\n"
                f"参考になれば。"
            ),
        ]
    else:
        # ai_tools / productivity / ai_saas 汎用
        x_options = [
            (
                f"「{keyword}、使ってみたいけど自分には難しそう…」\n\n"
                f"そう思って後回しにしていた。\n"
                f"でも実際に触ってみたら、設定5分・日本語対応・無料プランあり。\n\n"
                f"「なんで今まで使わなかったんだろう」と思った。\n\n"
                f"初心者向けに使い方まとめました👇"
            ),
            (
                f"AIツールって「使いこなせる人だけのもの」だと思ってた。\n\n"
                f"実際に1週間使ってみて変わったこと：\n"
                f"・資料作成が半分の時間に\n"
                f"・調べ物の精度が上がった\n"
                f"・「あれ、これもできるじゃん」が毎日続いた\n\n"
                f"【{keyword}】の具体的な使い方まとめました👇"
            ),
            (
                f"無料なのに使わないのはもったいない。\n\n"
                f"{keyword}、今すぐ試せます。\n"
                f"クレカ登録不要・日本語OK・スマホだけでも使える。\n\n"
                f"何から始めればいいか迷っている方向けに手順まとめました。\n"
                f"詳細はブログで👇"
            ),
        ]
        bsky_options = [
            (
                f"「{keyword}」について書きました。\n\n"
                f"難しいと思っていたけど、実際触ってみたら思ったより簡単でした。\n"
                f"初心者目線でまとめています。よかったら読んでみてください。"
            ),
            (
                f"無料で使えるのに知らない人が多い{keyword}。\n\n"
                f"使い方と、実際に役立った場面をまとめました。\n"
                f"参考になれば嬉しいです。"
            ),
        ]

    x_text = random.choice(x_options)
    bsky_text = random.choice(bsky_options)
    if _url:
        x_text += _url
        bsky_text += _url
    return {
        "x": x_text,
        "bluesky": bsky_text,
    }


def run(article: dict, dry_run: bool = False) -> dict:
    """
    ディストリビューター実行

    Returns:
        {
            "hatena":  bool,         # 投稿成功フラグ
            "note":    bool,
            "x":       bool,
            "bluesky": bool,
            "urls":    {             # 投稿成功時のURL（失敗時は空文字）
                "hatena":  str,
                "note":    str,
                "bluesky": str,
            },
            "errors":  {             # 失敗したプラットフォームのエラー1行
                "hatena":  str,
                "note":    str,
                "x":       str,
                "bluesky": str,
            },
        }
    """
    slot = article.get("slot", 0)
    keyword = article.get("keyword", "")
    print(f"\n  📡 [Distributor-{slot}] 「{keyword}」配信開始...")

    results = {
        "hatena": False, "note": False, "x": False, "bluesky": False,
        "urls": {"hatena": "", "note": "", "bluesky": ""},
        "errors": {},
    }

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
    try:
        sys.path.insert(0, str(ROOT_DIR))
        from hatena_automation.hatena_poster import post_article as hatena_post_article
        title = article.get("title", "")
        body = article.get("body", "")
        category = article.get("category", "")
        raw = hatena_post_article(title, body, category=category)
        # post_article はURL文字列を返す（失敗時は ""、ローカルは "file://..."）
        hatena_url = raw if isinstance(raw, str) else ""
        ok = bool(hatena_url) and not hatena_url.startswith("file://")
        results["hatena"] = ok
        results["urls"]["hatena"] = hatena_url if ok else ""
        status = "✅" if ok else "❌"
        print(f"  {status} [Distributor-{slot}] はてな投稿" + (f" → {hatena_url}" if ok else ""))
    except Exception as e:
        err_msg = f"{type(e).__name__}: {e}"
        results["errors"]["hatena"] = err_msg
        print(f"  ❌ [Distributor-{slot}] はてな失敗: {err_msg}")

    # === Google Indexing API（はてな投稿成功時）===
    if results["hatena"]:
        try:
            sys.path.insert(0, str(BASE_DIR))
            from money_agent.google_indexing import notify_article
            idx_result = notify_article(article, hatena_url=results["urls"]["hatena"])
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
        raw = note_post_article(title, body)
        note_url = raw if isinstance(raw, str) else ""
        ok = bool(note_url)
        results["note"] = ok
        results["urls"]["note"] = note_url if ok else ""
        status = "✅" if ok else "❌"
        print(f"  {status} [Distributor-{slot}] note投稿" + (f" → {note_url}" if ok else ""))
    except Exception as e:
        err_msg = f"{type(e).__name__}: {e}"
        results["errors"]["note"] = err_msg
        print(f"  ❌ [Distributor-{slot}] note失敗: {err_msg}")

    # === X 投稿 ===
    # はてな/note 投稿後に URL が確定するのでここで生成する
    _blog_url = results["urls"].get("hatena") or results["urls"].get("note") or ""
    sns_texts = _generate_sns_texts(article, blog_url=_blog_url)

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
        results["x"] = bool(x_ok)
        status = "✅" if x_ok else "❌"
        print(f"  {status} [Distributor-{slot}] X投稿")
        if not x_ok:
            results["errors"]["x"] = "tweepy/twikit/browser 全フォールバック失敗"
    except Exception as e:
        err_msg = f"{type(e).__name__}: {e}"
        results["errors"]["x"] = err_msg
        print(f"  ❌ [Distributor-{slot}] X失敗: {err_msg}")

    # === Bluesky 投稿 ===
    try:
        from bluesky_automation.bsky_poster import post_to_bluesky
        bsky_result = post_to_bluesky(sns_texts["bluesky"])
        # post_to_bluesky は {"success": bool, "url": str, "error": str} を返す
        if isinstance(bsky_result, dict):
            ok = bsky_result.get("success", False)
            bsky_url = bsky_result.get("url", "")
            bsky_err = bsky_result.get("error", "")
        else:
            # 旧バージョン互換: 戻り値が bool の場合
            ok = bool(bsky_result)
            bsky_url = ""
            bsky_err = ""
        results["bluesky"] = ok
        results["urls"]["bluesky"] = bsky_url
        if ok:
            print(f"  ✅ [Distributor-{slot}] Bluesky投稿" + (f" → {bsky_url}" if bsky_url else ""))
        else:
            err_msg = bsky_err or "投稿失敗（詳細不明）"
            results["errors"]["bluesky"] = err_msg
            print(f"  ❌ [Distributor-{slot}] Bluesky失敗: {err_msg}")
    except Exception as e:
        # atproto の認証エラーや接続エラーを詳細にログ出力
        exc_type = type(e).__name__
        err_detail = str(e)
        # 401 Unauthorized の特定
        if "401" in err_detail or "Unauthorized" in err_detail or "AuthenticationRequired" in err_detail:
            err_msg = f"Auth Error (401 Unauthorized): BSKY_HANDLE / BSKY_APP_PASSWORD を確認"
        elif "NetworkError" in exc_type or "ConnectionError" in exc_type or "Timeout" in exc_type:
            err_msg = f"Network Error: {err_detail[:80]}"
        else:
            err_msg = f"{exc_type}: {err_detail[:100]}"
        results["errors"]["bluesky"] = err_msg
        print(f"  ❌ [Distributor-{slot}] Bluesky失敗: {err_msg}")

    success_count = sum(bool(results[k]) for k in ("hatena", "note", "x", "bluesky"))
    print(f"  📊 [Distributor-{slot}] 配信完了: {success_count}/4プラットフォーム")
    return results
