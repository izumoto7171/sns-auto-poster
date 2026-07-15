"""
GEO パイロット検証ツール
公開記事が AI 検索（Perplexity / ChatGPT Search）に引用されているかを確認し、
懸念点セクションの精度も検証する。

使い方:
  python3 money_agent/geo_verifier.py check           # 全記事をチェック
  python3 money_agent/geo_verifier.py check-keyword "ChatGPT 中小企業"
  python3 money_agent/geo_verifier.py report          # KPIレポート表示
  python3 money_agent/geo_verifier.py tune-concerns   # 懸念点プロンプト調整提案
"""

import json
import os
import sys
import re
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
ROOT_DIR = BASE_DIR.parent
sys.path.insert(0, str(ROOT_DIR))

from db_client import db


# ── 1. AI 検索での引用確認 ─────────────────────────────────────

def _search_perplexity_web(keyword: str, our_domain: str) -> dict:
    """
    Perplexity の公開検索ページをスクレイピングして引用を確認する。
    API キーがある場合は Perplexity API を使用。
    """
    result = {
        "keyword": keyword,
        "engine": "perplexity",
        "cited": False,
        "citation_snippet": "",
        "checked_at": datetime.now().isoformat(),
    }

    api_key = os.environ.get("PERPLEXITY_API_KEY", "")
    if not api_key:
        result["skipped"] = True
        result["reason"] = "PERPLEXITY_API_KEY 未設定"
        return result

    try:
        import requests
        resp = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.1-sonar-large-128k-online",
                "messages": [{"role": "user", "content": keyword}],
                "return_citations": True,
            },
            timeout=30,
        )
        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        citations = data.get("citations", [])

        # ドメインが引用に含まれているか確認
        for cite in citations:
            if our_domain in cite:
                result["cited"] = True
                result["citation_snippet"] = content[:200]
                result["citation_url"] = cite
                break

        result["full_answer_preview"] = content[:300]
    except Exception as e:
        result["error"] = str(e)

    return result


def _check_gemini_grounding(keyword: str, our_domain: str) -> dict:
    """
    Gemini Search Grounding で引用確認（Gemini API + Google Search grounding）
    """
    result = {
        "keyword": keyword,
        "engine": "gemini_grounding",
        "cited": False,
        "citation_snippet": "",
        "checked_at": datetime.now().isoformat(),
    }

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        result["skipped"] = True
        result["reason"] = "GEMINI_API_KEY 未設定"
        return result

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"日本語で答えてください: {keyword} について教えてください",
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )

        text = resp.text or ""
        # grounding metadata からソースURLを取得
        sources = []
        if hasattr(resp, "candidates") and resp.candidates:
            cand = resp.candidates[0]
            if hasattr(cand, "grounding_metadata") and cand.grounding_metadata:
                gm = cand.grounding_metadata
                if hasattr(gm, "search_entry_point"):
                    pass
                # grounding_chunks から URL を取得
                chunks = getattr(gm, "grounding_chunks", []) or []
                for chunk in chunks:
                    web = getattr(chunk, "web", None)
                    if web:
                        uri = getattr(web, "uri", "")
                        if uri:
                            sources.append(uri)

        for src in sources:
            if our_domain in src:
                result["cited"] = True
                result["citation_url"] = src
                result["citation_snippet"] = text[:200]
                break

        result["full_answer_preview"] = text[:300]
        result["sources"] = sources[:5]
    except Exception as e:
        result["error"] = str(e)

    return result


def check_article_citations(articles: list[dict], our_domain: str = "hatenablog.com") -> list[dict]:
    """
    記事リストに対して AI 検索での引用確認を実行する。
    articles: [{"keyword": ..., "title": ..., "url": ...}, ...]
    """
    results = []
    print(f"\n[GEO Verifier] {len(articles)}件の記事を AI 検索で確認中...")

    for i, art in enumerate(articles, 1):
        keyword = art.get("keyword", "")
        print(f"  [{i}/{len(articles)}] 「{keyword[:30]}」確認中...")

        gemini_result = _check_gemini_grounding(keyword, our_domain)
        perplexity_result = _search_perplexity_web(keyword, our_domain)

        cited_anywhere = gemini_result.get("cited") or perplexity_result.get("cited")

        record = {
            "keyword": keyword,
            "title": art.get("title", ""),
            "url": art.get("url", ""),
            "cited_anywhere": cited_anywhere,
            "gemini": gemini_result,
            "perplexity": perplexity_result,
            "checked_at": datetime.now().isoformat(),
        }
        results.append(record)

        # API レート制限対策
        if i < len(articles):
            time.sleep(2)

    return results


# ── 2. 引用結果を Supabase に保存 ──────────────────────────────

def save_citation_results(results: list[dict]):
    """引用確認結果を geo_citations テーブルに保存"""
    for r in results:
        try:
            db.upsert_geo_citation({
                "keyword": r["keyword"],
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "cited_anywhere": r.get("cited_anywhere", False),
                "gemini_cited": r.get("gemini", {}).get("cited", False),
                "perplexity_cited": r.get("perplexity", {}).get("cited", False),
                "gemini_snippet": r.get("gemini", {}).get("citation_snippet", ""),
                "checked_at": r["checked_at"],
            })
        except Exception as e:
            # テーブル未作成の場合はローカルに保存
            print(f"  [GEO] DB保存失敗（ローカルにフォールバック）: {e}")
            _save_citation_local(r)


def _save_citation_local(record: dict):
    """DBが使えない場合のローカル保存"""
    log_file = BASE_DIR / "data" / "geo_citations.jsonl"
    log_file.parent.mkdir(exist_ok=True)
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ── 3. 懸念点プロンプトの調整提案 ──────────────────────────────

def analyze_concern_gaps(articles_with_performance: list[dict]) -> dict:
    """
    低CTR・低引用率の記事と懸念点セクションを比較し、
    Gemini にプロンプト改善案を提案させる。
    """
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return {"error": "GEMINI_API_KEY 未設定"}

    # CTR や引用率が低い記事を抽出
    low_performers = [
        a for a in articles_with_performance
        if a.get("ctr", 1.0) < 0.03 or not a.get("cited_anywhere", True)
    ]

    if not low_performers:
        return {"message": "改善が必要な記事なし。懸念点セクションは機能しています。"}

    # Gemini に分析させる
    try:
        from google import genai
        client = genai.Client(api_key=api_key)

        articles_summary = "\n".join([
            f"- キーワード: {a.get('keyword', '')} / CTR: {a.get('ctr', 0):.1%} / 引用: {a.get('cited_anywhere', False)}"
            for a in low_performers[:5]
        ])

        prompt = f"""以下のアフィリエイト記事は、AI検索での引用率またはCTRが低いです。

{articles_summary}

これらの記事の「読者の懸念点」を抽出するプロンプトを改善するために、
具体的に何を変えるべきか教えてください。

以下のJSON形式で回答してください（コードブロック不要）:
{{
  "diagnosis": "現在のプロンプトの問題点（1〜2文）",
  "improved_prompt_addition": "プロンプトに追加すべき指示（具体的な文章）",
  "example_concerns": ["改善後の懸念点例1", "改善後の懸念点例2", "改善後の懸念点例3"]
}}"""

        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        text = resp.text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        return json.loads(text)
    except Exception as e:
        return {"error": str(e)}


def apply_concern_prompt_improvement(improvement: dict):
    """
    analyze_concern_gaps の提案を geo_enhancer.py のプロンプトに反映する。
    手動確認後に呼ぶ想定。
    """
    addition = improvement.get("improved_prompt_addition", "")
    if not addition:
        print("[GEO Verifier] 改善提案なし")
        return

    geo_path = BASE_DIR / "geo_enhancer.py"
    content = geo_path.read_text(encoding="utf-8")

    # 既存プロンプトの末尾に追記
    old_fragment = '例: ["簡単に月100万円などの誇大広告には要注意'
    # プロンプト内の該当箇所に追記する
    target = '例: ["月額料金が継続的にかかるのが不安", "無料プランで本当に使えるか試したい", "他サービスとの違いがわからない"]"""'
    if target in content:
        new_fragment = target.replace(
            '"]"""',
            f'"]\n\n追加条件（データから判明した改善点）:\n{addition}"]"""'
        )
        geo_path.write_text(content.replace(target, new_fragment), encoding="utf-8")
        print(f"[GEO Verifier] geo_enhancer.py のプロンプトを更新しました")
    else:
        print("[GEO Verifier] プロンプト更新対象が見つかりませんでした（手動で確認してください）")
        print(f"  追加提案: {addition}")


# ── 4. GEO KPI レポート ────────────────────────────────────────

def print_geo_kpi_report():
    """引用率・CTR・オファークリック率のレポートを出力"""
    print("\n" + "=" * 60)
    print("  GEO KPI レポート")
    print(f"  {datetime.now().strftime('%Y/%m/%d %H:%M')}")
    print("=" * 60)

    # ローカルの引用ログを読む（DB フォールバック）
    log_file = BASE_DIR / "data" / "geo_citations.jsonl"
    citations = []
    if log_file.exists():
        for line in log_file.read_text(encoding="utf-8").splitlines():
            try:
                citations.append(json.loads(line))
            except Exception:
                pass

    if not citations:
        print("  引用確認データなし。`geo_verifier.py check` を先に実行してください。")
    else:
        cited_count = sum(1 for c in citations if c.get("cited_anywhere"))
        total = len(citations)
        citation_rate = cited_count / total if total else 0

        print(f"\n  回答引用率: {cited_count}/{total}件 ({citation_rate:.0%})")
        print(f"  目標: 10〜20%（パイロット期）→ 30%以上（安定期）")

        if citation_rate < 0.1:
            print("\n  状況: 引用率が低い → 以下を確認してください")
            print("    1. 結論ファーストブロックが記事冒頭200字以内にあるか")
            print("    2. JSON-LD が正しく出力されているか（ブラウザのソース確認）")
            print("    3. 記事公開から2週間以上経過しているか")
        elif citation_rate < 0.3:
            print("\n  状況: 改善中。懸念点セクションの精度調整を推奨")
            print("    → `python3 money_agent/geo_verifier.py tune-concerns` を実行")
        else:
            print("\n  状況: 良好。比較テーブルのデータを更新して維持を")

        print(f"\n  引用済みキーワード:")
        for c in citations:
            if c.get("cited_anywhere"):
                print(f"    ✅ {c.get('keyword', '')[:40]}")

        print(f"\n  未引用キーワード（要改善）:")
        for c in citations[:5]:
            if not c.get("cited_anywhere"):
                print(f"    ❌ {c.get('keyword', '')[:40]}")

    # 収益データとのクロス分析
    try:
        posts = db.get_revenue_records(year=datetime.now().year, month=datetime.now().month)
        if posts:
            by_category = {}
            for p in posts:
                cat = p.get("category", "不明")
                if cat not in by_category:
                    by_category[cat] = {"posts": 0, "revenue": 0, "af_links": 0}
                by_category[cat]["posts"] += 1
                by_category[cat]["revenue"] += p.get("estimated_revenue_30days", 0)
                by_category[cat]["af_links"] += p.get("affiliate_count", 0)

            print(f"\n  カテゴリ別 オファークリック率推定（推定収益/記事数）")
            ranked = sorted(by_category.items(), key=lambda x: x[1]["revenue"] / max(x[1]["posts"], 1), reverse=True)
            for cat, d in ranked:
                rev_per_post = d["revenue"] // max(d["posts"], 1)
                print(f"    {cat:20s}: ¥{rev_per_post:,}/記事  ({d['posts']}件)")

            best = ranked[0][0] if ranked else ""
            if best:
                print(f"\n  推奨: 「{best}」に特化した特集記事の増産を検討")
    except Exception as e:
        print(f"\n  収益データ取得エラー: {e}")

    print("=" * 60)


# ── 5. 3シナリオKPI診断エンジン ───────────────────────────────

def diagnose_kpi(citation_rate: float, offer_ctr: float) -> dict:
    """
    引用率 × オファークリック率の組み合わせから状況を診断し
    次のアクションを返す。

    参考閾値（パイロット期）:
      citation_rate:  低 < 0.10 ≤ 中 < 0.30 ≤ 高
      offer_ctr:      低 < 0.01 ≤ 中 < 0.03 ≤ 高
    """
    citation_high = citation_rate >= 0.10
    offer_high    = offer_ctr    >= 0.01

    if citation_high and not offer_high:
        return {
            "scenario": "引用率○ / オファークリック率✕",
            "diagnosis": (
                "AI検索には評価されているが、CTAが魅力的ではない。"
                "結論ブロック直後のリンクテキストや、比較テーブルの「なぜ有利か」列が弱い可能性。"
            ),
            "actions": [
                "geo_enhancer.py の _build_inline_cta() でボタンテキストを変更\n"
                "  → 「詳細を確認する」→「今すぐ無料で試す（クレカ不要）」に強化",
                "アフィリエイトリンクのキャンペーン情報（af['campaign']）を設定して期間限定感を追加",
                "比較テーブルの「なぜ有利か」列を、より具体的な数値訴求に更新",
            ],
            "priority": "high",
        }

    elif not citation_high and offer_high:
        return {
            "scenario": "引用率✕ / オファークリック率○",
            "diagnosis": (
                "直接流入した読者の心は掴んでいるが、AI検索エンジンの信頼を得られていない。"
                "JSON-LDの構造化データ・比較テーブルの網羅性・記事冒頭の結論配置に問題がある可能性。"
            ),
            "actions": [
                "記事のソースを確認し、JSON-LD <script> タグが本文最後に存在するか検証",
                "seo_article_generator.py の build_data_comparison_table() を拡充\n"
                "  → 現在3〜4列のテーブルを5〜6列に増やし、数値の具体度を上げる",
                "結論ブロックが記事冒頭200文字以内に配置されているか確認\n"
                "  → geo_enhancer.py の build_conclusion_first() で結論をより短く要約",
                "記事に独自計測データ・一次情報を追加（AI は「一般論」より「実測値」を引用しやすい）",
            ],
            "priority": "high",
        }

    elif not citation_high and not offer_high:
        return {
            "scenario": "引用率✕ / オファークリック率✕",
            "diagnosis": (
                "キーワードの検索意図（ペルソナ）と記事の内容がミスマッチしている。"
                "または記事がまだ公開から2週間未満でインデックスされていない。"
            ),
            "actions": [
                "researcher.py の READER_PERSONAS を見直す\n"
                "  → ターゲット読者が実際に使う言葉・悩みの解像度を上げる",
                "pilot_mode=True で低競合キーワードに切り替える\n"
                "  → ceo_agent.py で state['pilot_mode'] = True を設定",
                "geo_verifier.py tune-concerns を実行して懸念点プロンプトを調整",
                "公開から14日未満なら判断を保留し、2週間後に再度チェック",
            ],
            "priority": "critical",
        }

    else:  # 両方高い
        return {
            "scenario": "引用率○ / オファークリック率○",
            "diagnosis": "システムが正常に機能しています。このパターンを横展開してください。",
            "actions": [
                "勝ちパターンのカテゴリ・キーワード構造を他カテゴリに複製",
                "成功した懸念点セクションのプロンプトをベースにジャンルを拡大",
                "パイロットモードを解除して通常の記事量産モードに移行可能",
            ],
            "priority": "low",
        }


def print_kpi_diagnosis(citation_rate: float = None, offer_ctr: float = None):
    """
    引用率・オファークリック率を自動取得または引数から受け取り、診断結果を出力する。
    """
    # 引数がなければ自動取得
    if citation_rate is None:
        log_file = BASE_DIR / "data" / "geo_citations.jsonl"
        if log_file.exists():
            lines = [l for l in log_file.read_text(encoding="utf-8").splitlines() if l.strip()]
            if lines:
                records = [json.loads(l) for l in lines]
                citation_rate = sum(1 for r in records if r.get("cited_anywhere")) / len(records)
        citation_rate = citation_rate or 0.0

    if offer_ctr is None:
        try:
            data_file = BASE_DIR / "data" / "data_analysis.json"
            if data_file.exists():
                data = json.loads(data_file.read_text(encoding="utf-8"))
                offer_ctr = data.get("geo_kpi", {}).get("top_offer_ctr", 0.0)
        except Exception:
            pass
        offer_ctr = offer_ctr or 0.0

    result = diagnose_kpi(citation_rate, offer_ctr)

    print("\n" + "=" * 60)
    print("  GEO KPI 診断レポート")
    print("=" * 60)
    print(f"\n  引用率:         {citation_rate:.1%}  {'✅' if citation_rate >= 0.10 else '❌'}")
    print(f"  オファークリック率: {offer_ctr:.2%}  {'✅' if offer_ctr >= 0.01 else '❌'}")
    print(f"\n  シナリオ: 【{result['scenario']}】")
    print(f"\n  診断: {result['diagnosis']}")
    print(f"\n  推奨アクション（優先度: {result['priority']}）:")
    for i, action in enumerate(result["actions"], 1):
        # インデント付きで出力
        lines = action.split("\n")
        print(f"    {i}. {lines[0]}")
        for line in lines[1:]:
            print(f"       {line}")

    # 承認待ち推奨の状況も表示
    pending_file = BASE_DIR / "data" / "pending_recommendations.json"
    if pending_file.exists():
        try:
            records = json.loads(pending_file.read_text(encoding="utf-8"))
            pending = [r for r in records if not r.get("approved") and not r.get("applied")]
            if pending:
                print(f"\n  承認待ち推奨: {len(pending)}件")
                print(f"  → data/pending_recommendations.json を確認し、")
                print(f'     "approved": true に変更してください')
                latest = pending[-1]
                rec = latest.get("recommendations", {})
                print(f"  最新推奨: ジャンル={rec.get('best_genre', '-')} / "
                      f"KPI={rec.get('kpi_summary', '-')[:40]}")
        except Exception:
            pass

    print("=" * 60)
    return result


# ── CLI エントリーポイント ─────────────────────────────────────

if __name__ == "__main__":
    # .env 読み込み
    env_path = ROOT_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v)

    mode = sys.argv[1] if len(sys.argv) > 1 else "report"

    if mode == "check":
        # 直近の投稿記事をDBから取得してチェック
        try:
            posts = db.get_revenue_records(year=datetime.now().year, month=datetime.now().month)
            articles = [
                {"keyword": p.get("keyword", ""), "title": p.get("title", ""), "url": p.get("url", "")}
                for p in posts[:10]  # パイロット期は最初の10件
            ]
        except Exception:
            articles = []

        if not articles:
            print("確認対象の記事が見つかりません。投稿履歴が必要です。")
            sys.exit(1)

        results = check_article_citations(articles)
        save_citation_results(results)

        cited = sum(1 for r in results if r.get("cited_anywhere"))
        print(f"\n引用率: {cited}/{len(results)} ({cited/len(results):.0%})")

    elif mode == "check-keyword" and len(sys.argv) > 2:
        keyword = sys.argv[2]
        results = check_article_citations([{"keyword": keyword, "title": keyword, "url": ""}])
        print(json.dumps(results[0], ensure_ascii=False, indent=2))

    elif mode == "tune-concerns":
        # 低パフォーマー分析
        try:
            posts = db.get_revenue_records(year=datetime.now().year, month=datetime.now().month)
            articles_with_perf = [
                {
                    "keyword": p.get("keyword", ""),
                    "ctr": p.get("estimated_revenue_30days", 0) / max(p.get("estimated_pv_30days", 1), 1) / 1000,
                    "cited_anywhere": False,
                }
                for p in posts
            ]
        except Exception:
            articles_with_perf = []

        improvement = analyze_concern_gaps(articles_with_perf)
        print("\n懸念点プロンプト改善提案:")
        print(json.dumps(improvement, ensure_ascii=False, indent=2))

        if improvement.get("improved_prompt_addition"):
            ans = input("\nこの改善を geo_enhancer.py に適用しますか？ [y/N]: ")
            if ans.lower() == "y":
                apply_concern_prompt_improvement(improvement)

    elif mode == "report":
        print_geo_kpi_report()

    elif mode == "diagnose":
        # 引数で明示的に数値を渡すことも可能: diagnose 0.15 0.025
        cr = float(sys.argv[2]) if len(sys.argv) > 2 else None
        oc = float(sys.argv[3]) if len(sys.argv) > 3 else None
        print_kpi_diagnosis(cr, oc)

    elif mode == "approve":
        # 承認待ち推奨を一覧表示して承認操作
        pending_file = BASE_DIR / "data" / "pending_recommendations.json"
        if not pending_file.exists():
            print("承認待ち推奨はありません")
        else:
            records = json.loads(pending_file.read_text(encoding="utf-8"))
            pending = [r for r in records if not r.get("approved") and not r.get("applied")]
            if not pending:
                print("承認待ち推奨はありません（すべて承認済みまたは適用済み）")
            else:
                for i, r in enumerate(pending):
                    rec = r.get("recommendations", {})
                    print(f"\n[{i+1}] ID: {r['id']} / 生成: {r['generated_at'][:16]}")
                    print(f"     ジャンル: {rec.get('best_genre', '-')}")
                    print(f"     GEO推奨: {rec.get('geo_recommendation', '-')[:60]}")
                    print(f"     KPI: {rec.get('kpi_summary', '-')[:60]}")
                    print(f"     高優先リライト: {len(rec.get('high_priority_rewrites', []))}件")

                print("\n承認するIDの番号を入力してください（all=全承認、スキップ=Enter）: ", end="")
                ans = input().strip()
                if ans.lower() == "all":
                    for r in pending:
                        r["approved"] = True
                        r["approved_by_human"] = True
                elif ans.isdigit():
                    idx = int(ans) - 1
                    if 0 <= idx < len(pending):
                        pending[idx]["approved"] = True
                        pending[idx]["approved_by_human"] = True
                        print(f"承認: {pending[idx]['id']}")
                pending_file.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
                print("保存しました")

    elif mode == "pilot-on":
        # CEO の state に pilot_mode=True を設定（DBに書き込む）
        try:
            state = db.get_agent_state() or {}
            state["pilot_mode"] = True
            db.save_agent_state(state)
            print("パイロットモード: ON\n次回実行から低競合キーワードを優先します")
        except Exception as e:
            print(f"DB更新失敗: {e}")

    elif mode == "pilot-off":
        try:
            state = db.get_agent_state() or {}
            state["pilot_mode"] = False
            db.save_agent_state(state)
            print("パイロットモード: OFF\n通常のキーワード選定に戻ります")
        except Exception as e:
            print(f"DB更新失敗: {e}")

    else:
        print("使い方: geo_verifier.py [check|check-keyword <kw>|tune-concerns|report|diagnose|approve|pilot-on|pilot-off]")
