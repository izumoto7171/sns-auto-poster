"""
CEO AIエージェント — アフィリエイト天下統一システム

【社員構成】
  CEO (このファイル)
   ├── MarketResearcher — 高単価×低競合ジャンルを発掘
   ├── DataAnalyst      — CVR計算 → リライト優先順位付け → RewritePlan
   ├── Analyst          — RewritePlan + 投稿データ → ActionPlan を決定
   ├── Researcher ×N    — キーワード並列選定
   ├── Writer    ×N    — 記事並列生成（新規 or リライト）
   ├── ApprovalFlow     — 人間承認チェックポイント
   └── Distributor      — はてな→note→X→Bluesky全配信

【ActionPlan の primary_action で動的フロー制御】
  write_new        → Researcher → Writer(新規) → Distribute
  rewrite_existing → rewrite_targets を Writer(リライト) → Distribute
  change_genre     → state のジャンルを更新 → write_new フローへ
  market_research  → MarketResearcher → state 更新 → write_new フローへ

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

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))


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
from db_client import db

# ── 設定 ──────────────────────────────────────────────────────
NUM_WRITERS = 3   # 並列ライター数
# QUALITY_MODE=false でテンプレートモードにロールバック可能
QUALITY_MODE = os.environ.get("QUALITY_MODE", "true").lower() in ("true", "1", "yes")

_DEFAULT_STATE = {
    "total_articles": 0,
    "today_articles": 0,
    "last_run": "",
    "analyst_report": {},
    "used_keywords": [],
    "daily_log": [],
    "market_research": {},
    "target_genre": "",
}


# ── 共有ステート管理（DB版）──────────────────────────────────

def _load_state() -> dict:
    try:
        state = db.get_agent_state()
        if state:
            return state
    except Exception as e:
        print(f"[CEO] stateDB読み込み失敗: {e}")
    return dict(_DEFAULT_STATE)


def _save_state(state: dict):
    state["last_run"] = datetime.datetime.now().isoformat()
    try:
        db.save_agent_state(state)
    except Exception as e:
        print(f"[CEO] stateDB書き込み失敗: {e}")


def _reset_daily_counter(state: dict) -> dict:
    today = datetime.date.today().isoformat()
    if state.get("last_date") != today:
        state["today_articles"] = 0
        state["last_date"] = today
    return state


# ── 市場調査の必要性判定 ─────────────────────────────────────

def _market_research_stale(state: dict, threshold_days: int = 7) -> bool:
    """市場データが threshold_days 以上古い場合 True"""
    last_market = state.get("market_research", {}).get("generated_at", "")
    if not last_market:
        return True
    try:
        last_dt = datetime.datetime.fromisoformat(last_market)
        return (datetime.datetime.now() - last_dt).days >= threshold_days
    except Exception:
        return True


# ── リライト用 research dict を生成 ─────────────────────────

def _make_rewrite_research(target: dict, slot: int, state: dict) -> dict:
    """
    rewrite_target → researcher.run() の代わりに使う research dict を生成。
    Writer にはキーワードとしてタイトルを渡し、リライト指示を付加する。
    """
    category = target.get("category", state.get("target_genre", "AIツール・SaaS"))

    # Researcher を呼んでアフィリエイトリンクだけ取得（キーワード上書き）
    try:
        base = researcher.run(state, slot=slot)
        base["keyword"]  = target.get("title", base["keyword"])
        base["category"] = category
        base["slot"]     = slot
        base["rewrite_instruction"] = target.get("rewrite_instruction", "")
        base["rewrite_mode"] = True
        return base
    except Exception as e:
        print(f"  [CEO] rewrite research 生成エラー (slot={slot}): {e}")
        return {
            "keyword":              target.get("title", "リライト記事"),
            "category":             category,
            "affiliates":           [],
            "slot":                 slot,
            "rewrite_instruction":  target.get("rewrite_instruction", ""),
            "rewrite_mode":         True,
        }


# ── サブコマンド関数 ──────────────────────────────────────────

def run_market_research() -> dict:
    print("\n" + "=" * 60)
    print("  MarketResearcher 起動")
    print("=" * 60)
    state = _load_state()
    result = market_researcher.run(state)
    _generate_roadmap(result)
    return result


def run_data_analysis() -> dict:
    print("\n" + "=" * 60)
    print("  DataAnalyst 起動")
    print("=" * 60)
    state = _load_state()
    return data_analyst.run(state)


def _generate_roadmap(market_data: dict):
    genre      = market_data.get("recommended_genre", "AIツール・SaaS")
    strategy   = market_data.get("monthly_10man_strategy", "")
    keywords   = market_data.get("target_keywords", [])
    quick_wins = market_data.get("quick_wins", [])
    risk       = market_data.get("risk", "")
    top5       = market_data.get("top5_genres", [])

    roadmap = f"""# アフィリエイト天下統一 ロードマップ
生成日: {datetime.datetime.now().strftime('%Y年%m月%d日')}

---

## 推奨ジャンル: **{genre}**

**理由:** {market_data.get('reason', '')}

**月10万円戦略:** {strategy}

**リスク:** {risk}

---

## ジャンル別スコアランキング

| ジャンル | スコア | 単価 | 競合度 | トレンド |
|---|---|---|---|---|
""" + "\n".join(
        f"| {g['genre']} | {g['score']} | ¥{g['unit_price']:,} | {'高' if g['competition'] >= 7 else ('中' if g['competition'] >= 4 else '低')} | {g['trend']} |"
        for g in top5
    ) + f"""

---

## フェーズ別ロードマップ

### PHASE 1: 土台作り（1〜2週間）
- [ ] 「{genre}」ジャンルのASPプログラムに申請・承認
- [ ] ターゲットキーワードリストを確定
- 狙うキーワード: {', '.join(keywords[:3])}

### PHASE 2: 記事量産（2週間〜1ヶ月）
- [ ] CEOエージェントで毎日記事自動生成（1日4回）
- [ ] 週1回の人間レビュー（承認フロー）
- [ ] DataAnalystが自動でリライト候補を特定

### PHASE 3: 収益化（1〜2ヶ月）
- [ ] 検索流入が始まる記事の強化
- [ ] CVRが高いカテゴリに集中投下

### PHASE 4: スケール（2〜3ヶ月）
- [ ] 月10万円達成
- [ ] 勝ちパターンを全カテゴリに横展開

---

## 今週すぐできること

{chr(10).join(f'- [ ] {w}' for w in quick_wins)}

---

*MarketResearcherエージェントが自動生成*
"""

    roadmap_file = ROOT_DIR / "ROADMAP.md"
    roadmap_file.write_text(roadmap, encoding="utf-8")
    print("  ロードマップ生成: ROADMAP.md")


# ── CEO メイン実行 ────────────────────────────────────────────

def run_ceo(dry_run: bool = False, auto_approve: bool = False):
    now = datetime.datetime.now().strftime("%Y/%m/%d %H:%M")
    print("\n" + "=" * 60)
    print("  CEO AIエージェント 起動")
    print(f"  {now}  |  ライター数: {NUM_WRITERS}本/回")
    if dry_run:
        print("  DRY-RUN モード（投稿しません）")
    if auto_approve:
        print("  AUTO-APPROVE モード（承認フローをスキップ）")
    print("=" * 60)

    state = _load_state()
    state = _reset_daily_counter(state)

    # ─────────────────────────────────────────────────
    # PHASE 0a: DataAnalyst — CVR分析・リライト計画
    # ─────────────────────────────────────────────────
    print("\nPHASE 0a: DataAnalyst — CVR分析・リライト計画生成中...")
    data_analysis: dict = {}
    try:
        data_analysis = data_analyst.run(state)
        state["data_analysis"] = data_analysis
        rewrite_count = len([
            r for r in data_analysis.get("rewrite_queue", [])
            if r.get("rewrite_priority") == "HIGH"
        ])
        if rewrite_count > 0:
            print(f"  リライト優先記事: {rewrite_count}件")
    except Exception as e:
        print(f"  DataAnalyst エラー: {e}")

    # ─────────────────────────────────────────────────
    # PHASE 0b: Analyst — ActionPlan 生成
    # ─────────────────────────────────────────────────
    print("\nPHASE 0b: Analyst — ActionPlan 生成中...")
    action_plan: dict = {}
    try:
        action_plan = analyst.run(state, data_analysis=data_analysis)
        state["analyst_report"] = action_plan
        print(f"  primary_action : {action_plan.get('primary_action', '?')}")
        print(f"  target_genre   : {action_plan.get('target_genre', '-')}")
        print(f"  today_strategy : {action_plan.get('today_strategy', '-')}")
        print(f"  reasoning      : {action_plan.get('reasoning', '')[:80]}")
    except Exception as e:
        print(f"  Analyst エラー: {e}")
        action_plan = {"primary_action": "write_new"}

    primary_action = action_plan.get("primary_action", "write_new")

    # ─────────────────────────────────────────────────
    # PHASE 1: ActionPlan に基づく動的フロー制御
    # ─────────────────────────────────────────────────
    print(f"\nPHASE 1: ActionPlan 実行 → {primary_action}")

    if primary_action == "market_research":
        # 市場調査を実行してから write_new に移行
        print("  MarketResearcher を起動...")
        try:
            market_data = market_researcher.run(state)
            state["market_research"] = market_data
            _generate_roadmap(market_data)
            # ジャンルを更新
            new_genre = market_data.get("recommended_genre", "")
            if new_genre:
                state["target_genre"] = new_genre
                print(f"  target_genre を更新: {new_genre}")
        except Exception as e:
            print(f"  MarketResearcher エラー: {e}")
        primary_action = "write_new"

    elif primary_action == "change_genre":
        # ジャンルを切り替えて write_new に移行
        new_genre = action_plan.get("target_genre", "")
        if new_genre:
            state["target_genre"] = new_genre
            print(f"  ジャンル変更: {new_genre}")
        primary_action = "write_new"

    # ─────────────────────────────────────────────────
    # PHASE 2: Researcher / rewrite_targets — 記事ソース確定
    # ─────────────────────────────────────────────────
    print(f"\nPHASE 2: {'リライト対象' if primary_action == 'rewrite_existing' else 'Researcher'} — 記事ソース確定中...")
    research_results: list[dict] = []

    if primary_action == "rewrite_existing":
        rewrite_targets = action_plan.get("rewrite_targets", [])
        if not rewrite_targets:
            print("  リライト対象なし → write_new に切り替え")
            primary_action = "write_new"
        else:
            for slot, target in enumerate(rewrite_targets[:NUM_WRITERS]):
                res = _make_rewrite_research(target, slot, state)
                research_results.append(res)
                print(f"  [Rewrite-{slot}] 「{res['keyword'][:40]}」")

    if primary_action == "write_new":
        for slot in range(NUM_WRITERS):
            try:
                res = researcher.run(state, slot=slot)
                research_results.append(res)
            except Exception as e:
                print(f"  Researcher-{slot} エラー: {e}")

    if not research_results:
        print("  記事ソース確定に全失敗。終了します。")
        _save_state(state)
        return

    keywords_selected = [r["keyword"] for r in research_results]
    print(f"  確定キーワード: {keywords_selected}")

    # ─────────────────────────────────────────────────
    # PHASE 3: Writer × N — 記事並列生成
    # ─────────────────────────────────────────────────
    print(f"\nPHASE 3: Writer ×{len(research_results)} — 記事並列生成中...")
    articles: list[dict] = []

    def write_article(res: dict) -> dict:
        return writer.run(state, res)

    with ThreadPoolExecutor(max_workers=NUM_WRITERS) as executor:
        futures = {executor.submit(write_article, res): res for res in research_results}
        for future in as_completed(futures):
            res = futures[future]
            try:
                article = future.result()
                articles.append(article)
            except Exception as e:
                print(f"  Writer-{res.get('slot', '?')} エラー: {e}")

    articles.sort(key=lambda a: a.get("slot", 0))
    print(f"  {len(articles)}本の記事を生成完了")

    if not articles:
        print("  記事生成に全失敗。終了します。")
        _save_state(state)
        return

    if dry_run:
        print("\nDRY-RUN — 承認待ちに保存して終了")
        for a in articles:
            filepath = save_pending(a)
            print(f"  [{a.get('slot')}] {a.get('title', '')[:50]}")
            print(f"       → {filepath}")
        print_approval_summary(load_pending_articles())
        _save_state(state)
        print_dashboard()
        return

    # ─────────────────────────────────────────────────
    # PHASE 4: 承認フロー
    # ─────────────────────────────────────────────────
    if not auto_approve:
        print(f"\nPHASE 4: 承認フロー — 記事を pending に保存中...")
        for a in articles:
            save_pending(a)
            print(f"  保存: {a.get('keyword', '')} → pending/")

        approved_articles = get_approved_pending()
        if approved_articles:
            print(f"  承認済み記事: {len(approved_articles)}件 → 配信します")
            articles_to_distribute = approved_articles
        else:
            print(f"  承認待ち記事: {len(load_pending_articles())}件")
            print("  money_agent/approved.json にキーワードを追加してください")
            print_approval_summary(load_pending_articles())
            _save_state(state)
            print_dashboard()
            return
    else:
        articles_to_distribute = articles

    # ─────────────────────────────────────────────────
    # PHASE 5: Distributor — 全プラットフォームへ配信
    # ─────────────────────────────────────────────────
    print(f"\nPHASE 5: Distributor — {len(articles_to_distribute)}本を配信中...")
    dist_results: list[dict] = []
    for article in articles_to_distribute:
        try:
            result = distributor.run(article, dry_run=False)
            dist_results.append(result)
            if "_filename" in article:
                mark_as_published(article["_filename"])
            record_post(
                platform="hatena+note+x+bsky",
                title=article.get("title", ""),
                keyword=article.get("keyword", ""),
                category=article.get("category", ""),
                affiliate_count=article.get("affiliate_count", 0),
            )
        except Exception as e:
            print(f"  Distributor エラー: {e}")

    # ─────────────────────────────────────────────────
    # PHASE 6: ステート更新 & 日次ログ
    # ─────────────────────────────────────────────────
    state["total_articles"] = state.get("total_articles", 0) + len(articles_to_distribute)
    state["today_articles"] = state.get("today_articles", 0) + len(articles)

    used = state.get("used_keywords", [])
    used.extend(keywords_selected)
    state["used_keywords"] = used[-200:]

    # 配信成功数を記録（Analyst の連続ゼロ収益判定に使用）
    dist_success_count = sum(
        sum(v for v in r.values() if isinstance(v, int))
        for r in dist_results
    )
    log_entry = {
        "time":         datetime.datetime.now().isoformat(),
        "articles":     len(articles),
        "keywords":     keywords_selected,
        "dist_success": [dist_success_count],
        "action":       primary_action,
        "genre":        action_plan.get("target_genre", ""),
    }
    state.setdefault("daily_log", []).append(log_entry)
    state["daily_log"] = state["daily_log"][-100:]

    _save_state(state)

    # サマリー
    print("\n" + "=" * 60)
    print("  CEO サイクル完了")
    print(f"  生成記事: {len(articles)}本 | 配信成功件数: {dist_success_count}")
    print(f"  今日の累計: {state['today_articles']}本 | 通算: {state['total_articles']}本")
    pending_count = len(load_pending_articles())
    if pending_count > 0:
        print(f"  承認待ち: {pending_count}件")
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
        print(f"現在のジャンル: {state.get('target_genre', '未設定')}")
        from money_agent.approval_flow import load_pending_articles, print_approval_summary
        print_approval_summary(load_pending_articles())
        from money_agent.geo_verifier import print_geo_kpi_report
        print_geo_kpi_report()
    else:
        print(f"不明なモード: {mode}")
        sys.exit(1)
