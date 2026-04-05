"""
CEO AIエージェント — アフィリエイト天下統一システム

【社員構成】
  CEO (このファイル)
   ├── 🔬 MarketResearcher — 高単価×低競合ジャンルを発掘
   ├── 📊 Analyst          — パフォーマンス分析 → 今日の戦略決定
   ├── 📈 DataAnalyst      — CVR計算 → リライト優先順位付け
   ├── 🔍 Researcher ×N    — キーワード並列選定
   ├── ✍️  Writer    ×N    — 記事並列生成（3倍速）
   ├── ⏳ ApprovalFlow     — 人間承認チェックポイント
   └── 📡 Distributor      — はてな→note→X→Bluesky全配信

【実行】
  python3 money_agent/ceo_agent.py run          # 本番（承認フローあり）
  python3 money_agent/ceo_agent.py run-auto     # 本番（自動承認・即投稿）
  python3 money_agent/ceo_agent.py dry-run      # 生成のみ（投稿なし）
  python3 money_agent/ceo_agent.py market       # 市場調査のみ
  python3 money_agent/ceo_agent.py analyze      # データ分析のみ
  python3 money_agent/ceo_agent.py dashboard    # KPI確認
"""

import os
import sys
import json
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# パス設定
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

# .env 読み込み
def _load_env():
    env_path = ROOT_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v)

_load_env()

from money_agent.agents import analyst, researcher, writer, distributor
from money_agent.agents import market_researcher, data_analyst
from money_agent.approval_flow import (
    save_pending, get_approved_pending, mark_as_published,
    print_approval_summary, load_pending_articles,
)
from money_agent.revenue_tracker import record_post, print_dashboard

# ── 設定 ──────────────────────────────────────────────────────
NUM_WRITERS = 3          # 並列ライター数（記事生成数/回）
STATE_FILE = Path(__file__).parent / "agent_state.json"


# ── 共有ステート管理 ──────────────────────────────────────────

def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "total_articles": 0,
        "today_articles": 0,
        "last_run": "",
        "analyst_report": {},
        "used_keywords": [],
        "daily_log": [],
    }


def _save_state(state: dict):
    state["last_run"] = datetime.datetime.now().isoformat()
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _reset_daily_counter(state: dict) -> dict:
    """日付が変わったら今日の記事カウントをリセット"""
    today = datetime.date.today().isoformat()
    if state.get("last_date") != today:
        state["today_articles"] = 0
        state["last_date"] = today
    return state


# ── CEO メイン実行 ────────────────────────────────────────────

def run_market_research() -> dict:
    """市場調査のみ実行"""
    print("\n" + "=" * 60)
    print("  🔬 市場調査エージェント 起動")
    print("=" * 60)
    state = _load_state()
    result = market_researcher.run(state)
    _generate_roadmap(result)
    return result


def run_data_analysis() -> dict:
    """データ分析のみ実行"""
    print("\n" + "=" * 60)
    print("  📈 データ分析エージェント 起動")
    print("=" * 60)
    state = _load_state()
    return data_analyst.run(state)


def _generate_roadmap(market_data: dict):
    """市場調査結果からロードマップを生成"""
    genre = market_data.get("recommended_genre", "AIツール・SaaS")
    strategy = market_data.get("monthly_10man_strategy", "")
    keywords = market_data.get("target_keywords", [])
    quick_wins = market_data.get("quick_wins", [])
    risk = market_data.get("risk", "")
    top5 = market_data.get("top5_genres", [])

    roadmap = f"""# アフィリエイト天下統一 ロードマップ
生成日: {datetime.datetime.now().strftime('%Y年%m月%d日')}

---

## 🎯 推奨ジャンル: **{genre}**

**理由:** {market_data.get('reason', '')}

**月10万円戦略:** {strategy}

**リスク:** {risk}

---

## 📊 ジャンル別スコアランキング（高いほど稼ぎやすい）

| ジャンル | スコア | 単価 | 競合度 | トレンド |
|---|---|---|---|---|
""" + "\n".join(
        f"| {g['genre']} | {g['score']} | ¥{g['unit_price']:,} | {'🔴' * min(g['competition']//3+1,3)} | {g['trend']} |"
        for g in top5
    ) + f"""

---

## 🗓️ フェーズ別ロードマップ

### PHASE 1: 土台作り（1〜2週間）
- [ ] 「{genre}」ジャンルのASPプログラムに申請・承認
- [ ] ターゲットキーワードリストを確定
- [ ] はてなブログのカテゴリ・タグ設定を最適化
- 狙うキーワード: {', '.join(keywords[:3])}

### PHASE 2: 記事量産（2週間〜1ヶ月）
- [ ] CEOエージェントで毎日12記事自動生成
- [ ] 週1回の人間レビュー（承認フロー）
- [ ] リライト対象をDataAnalystが自動特定
- 目標: 月84記事（12記事×7日）

### PHASE 3: 収益化（1〜2ヶ月）
- [ ] 検索流入が始まる記事の強化
- [ ] CVRが高いカテゴリに集中投下
- [ ] MarketResearcherが毎週市場を再分析
- 目標: 月1,000PV → 月5,000PV

### PHASE 4: スケール（2〜3ヶ月）
- [ ] 月10万円達成（単価×件数の最適化）
- [ ] 勝ちパターンを全カテゴリに横展開
- [ ] エージェント数を5本に増やして月20記事/日

---

## ⚡ 今週すぐできること

{chr(10).join(f'- [ ] {w}' for w in quick_wins)}

---

## 🤖 AIエージェント体制

| 役割 | エージェント | 実行頻度 |
|---|---|---|
| 市場調査 | MarketResearcher | 週1回（月曜） |
| 戦略分析 | Analyst | 毎回（1日4回） |
| CVR分析 | DataAnalyst | 毎回 |
| キーワード選定 | Researcher ×3 | 毎回 |
| 記事生成 | Writer ×3並列 | 毎回 |
| 承認チェック | 人間（あなた） | 週1-2回 |
| 全SNS配信 | Distributor | 毎回 |

---

*このロードマップはMarketResearcherエージェントが自動生成しました*
"""

    roadmap_file = Path(__file__).parent.parent / "ROADMAP.md"
    roadmap_file.write_text(roadmap, encoding="utf-8")
    print(f"\n  📄 ロードマップ生成: ROADMAP.md")


def run_ceo(dry_run: bool = False, auto_approve: bool = False):
    now = datetime.datetime.now().strftime("%Y/%m/%d %H:%M")
    print("\n" + "=" * 60)
    print("  🏢 CEO AIエージェント 起動")
    print(f"  🕐 {now}  |  ライター数: {NUM_WRITERS}本/回")
    if dry_run:
        print("  🔍 DRY-RUN モード（実際の投稿はしません）")
    if auto_approve:
        print("  ⚡ AUTO-APPROVE モード（承認フローをスキップ）")
    print("=" * 60)

    state = _load_state()
    state = _reset_daily_counter(state)

    # ─────────────────────────────────────────────────
    # PHASE 0: 週1回の市場調査 & データ分析
    # ─────────────────────────────────────────────────
    weekday = datetime.datetime.now().weekday()  # 0=月曜
    if weekday == 0:  # 月曜のみ市場調査実行
        print("\n🔬 PHASE 0a: MarketResearcher が市場調査中（週1回）...")
        try:
            market_data = market_researcher.run(state)
            state["market_research"] = market_data
            _generate_roadmap(market_data)
        except Exception as e:
            print(f"  ⚠️ MarketResearcher エラー: {e}")

    print("\n📈 PHASE 0b: DataAnalyst がCVR分析中...")
    try:
        analysis = data_analyst.run(state)
        state["data_analysis"] = analysis
        rewrite_count = len(analysis.get("rewrite_queue", []))
        if rewrite_count > 0:
            print(f"  ⚡ リライト優先記事: {rewrite_count}件")
    except Exception as e:
        print(f"  ⚠️ DataAnalyst エラー: {e}")

    # ─────────────────────────────────────────────────
    # PHASE 1: Analyst — 今日の戦略を決定
    # ─────────────────────────────────────────────────
    print("\n📊 PHASE 1: Analyst が戦略を分析中...")
    try:
        analyst_report = analyst.run(state)
        state["analyst_report"] = analyst_report
        print(f"  💡 今日の戦略: {analyst_report.get('today_strategy', '-')}")
    except Exception as e:
        print(f"  ⚠️ Analyst エラー: {e}")
        analyst_report = {}
        state["analyst_report"] = {}

    # ─────────────────────────────────────────────────
    # PHASE 2: Researcher × NUM_WRITERS — キーワード選定
    # ─────────────────────────────────────────────────
    print(f"\n🔍 PHASE 2: Researcher ×{NUM_WRITERS} がキーワードを選定中...")
    research_results = []
    for slot in range(NUM_WRITERS):
        try:
            res = researcher.run(state, slot=slot)
            research_results.append(res)
        except Exception as e:
            print(f"  ❌ Researcher-{slot} エラー: {e}")

    if not research_results:
        print("  ❌ キーワード選定に全失敗。終了します。")
        return

    keywords_selected = [r["keyword"] for r in research_results]
    print(f"  ✅ 選定キーワード: {keywords_selected}")

    # ─────────────────────────────────────────────────
    # PHASE 3: Writer × NUM_WRITERS — 記事並列生成
    # ─────────────────────────────────────────────────
    print(f"\n✍️  PHASE 3: Writer ×{len(research_results)} が記事を並列生成中...")
    articles = []

    def write_article(res):
        return writer.run(state, res)

    with ThreadPoolExecutor(max_workers=NUM_WRITERS) as executor:
        futures = {executor.submit(write_article, res): res for res in research_results}
        for future in as_completed(futures):
            try:
                article = future.result()
                articles.append(article)
            except Exception as e:
                res = futures[future]
                print(f"  ❌ Writer-{res['slot']} エラー: {e}")

    articles.sort(key=lambda a: a.get("slot", 0))
    print(f"  ✅ {len(articles)}本の記事を生成完了")

    if not articles:
        print("  ❌ 記事生成に全失敗。終了します。")
        return

    if dry_run:
        print("\n🔍 DRY-RUN — 承認待ちに保存して終了")
        for a in articles:
            filepath = save_pending(a)
            print(f"  📄 [{a.get('slot')}] {a.get('title', '')[:50]}")
            print(f"       → {filepath}")
        print_approval_summary(load_pending_articles())
        print_dashboard()
        return

    # ─────────────────────────────────────────────────
    # PHASE 4: 承認フロー（auto_approve=False の場合）
    # ─────────────────────────────────────────────────
    if not auto_approve:
        print(f"\n⏳ PHASE 4: 承認フロー — 記事を pending に保存中...")
        for a in articles:
            save_pending(a)
            print(f"  💾 保存: {a.get('keyword', '')} → pending/")

        # 承認済みの記事のみ配信
        approved_articles = get_approved_pending()
        if approved_articles:
            print(f"\n  ✅ 承認済み記事: {len(approved_articles)}件 → 配信します")
            articles_to_distribute = approved_articles
        else:
            print(f"\n  ⏳ 承認待ち記事: {len(load_pending_articles())}件")
            print("     money_agent/approved.json にキーワードを追加してください")
            print_approval_summary(load_pending_articles())
            _save_state(state)
            print_dashboard()
            return
    else:
        articles_to_distribute = articles

    # ─────────────────────────────────────────────────
    # PHASE 5: Distributor — 全プラットフォームへ配信
    # ─────────────────────────────────────────────────
    print(f"\n📡 PHASE 5: Distributor が {len(articles_to_distribute)}本を配信中...")
    dist_results = []
    for article in articles_to_distribute:
        try:
            result = distributor.run(article, dry_run=False)
            dist_results.append(result)
            # 承認済みファイルを削除
            if "_filename" in article:
                mark_as_published(article["_filename"])
            # 収益ログ記録
            record_post(
                platform="hatena+note+x+bsky",
                title=article.get("title", ""),
                keyword=article.get("keyword", ""),
                category=article.get("category", ""),
                affiliate_count=article.get("affiliate_count", 0),
            )
        except Exception as e:
            print(f"  ❌ Distributor エラー: {e}")

    # ─────────────────────────────────────────────────
    # PHASE 6: ステート更新 & サマリー
    # ─────────────────────────────────────────────────
    state["total_articles"] = state.get("total_articles", 0) + len(articles_to_distribute)
    state["today_articles"] = state.get("today_articles", 0) + len(articles)

    # 使用済みキーワードを追記
    used = state.get("used_keywords", [])
    used.extend(keywords_selected)
    state["used_keywords"] = used[-200:]  # 直近200件のみ保持

    # 日次ログ
    log_entry = {
        "time": datetime.datetime.now().isoformat(),
        "articles": len(articles),
        "keywords": keywords_selected,
        "dist_success": [sum(r.values()) for r in dist_results],
    }
    state.setdefault("daily_log", []).append(log_entry)
    state["daily_log"] = state["daily_log"][-100:]  # 直近100件

    _save_state(state)

    # サマリー表示
    total_success = sum(sum(r.values()) for r in dist_results)
    print("\n" + "=" * 60)
    print(f"  ✅ CEO サイクル完了")
    print(f"  📝 生成記事: {len(articles)}本 | 配信成功: {total_success}件")
    print(f"  📊 今日の累計: {state['today_articles']}本 | 通算: {state['total_articles']}本")
    pending_count = len(load_pending_articles())
    if pending_count > 0:
        print(f"  ⏳ 承認待ち: {pending_count}件")
    print("=" * 60)

    print_dashboard()


# ── エントリーポイント ─────────────────────────────────────────

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "dry-run"

    if mode == "run":
        run_ceo(dry_run=False, auto_approve=False)
    elif mode == "run-auto":
        run_ceo(dry_run=False, auto_approve=True)
    elif mode == "dry-run":
        run_ceo(dry_run=True)
    elif mode == "market":
        run_market_research()
    elif mode == "analyze":
        run_data_analysis()
    elif mode == "dashboard":
        print_dashboard()
        state = _load_state()
        print(f"\n通算記事数: {state.get('total_articles', 0)}本")
        print(f"今日の記事数: {state.get('today_articles', 0)}本")
        print(f"最終実行: {state.get('last_run', '-')}")
        from money_agent.approval_flow import load_pending_articles, print_approval_summary
        print_approval_summary(load_pending_articles())
    else:
        print(f"不明なモード: {mode}")
        sys.exit(1)
