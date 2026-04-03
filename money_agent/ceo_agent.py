"""
CEO AIエージェント — アフィリエイト天下統一システム

【構造】
  CEO (このファイル)
   ├── Analyst    — 何が売れているか分析
   ├── Researcher × NUM_WRITERS — キーワード並列選定
   ├── Writer     × NUM_WRITERS — 記事並列生成 (3倍速)
   └── Distributor              — はてな→note→X→Bluesky全配信

【実行】
  python3 money_agent/ceo_agent.py run        # 本番
  python3 money_agent/ceo_agent.py dry-run    # 記事生成のみ（投稿なし）
  python3 money_agent/ceo_agent.py dashboard  # KPI確認
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

def run_ceo(dry_run: bool = False):
    now = datetime.datetime.now().strftime("%Y/%m/%d %H:%M")
    print("\n" + "=" * 60)
    print("  🏢 CEO AIエージェント 起動")
    print(f"  🕐 {now}  |  ライター数: {NUM_WRITERS}本/回")
    if dry_run:
        print("  🔍 DRY-RUN モード（実際の投稿はしません）")
    print("=" * 60)

    state = _load_state()
    state = _reset_daily_counter(state)

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
        print("\n🔍 DRY-RUN — 投稿せずに終了")
        for a in articles:
            print(f"  📄 [{a.get('slot')}] {a.get('title', '')[:50]}")
        print_dashboard()
        return

    # ─────────────────────────────────────────────────
    # PHASE 4: Distributor — 全プラットフォームへ配信
    # ─────────────────────────────────────────────────
    print(f"\n📡 PHASE 4: Distributor が {len(articles)}本を配信中...")
    dist_results = []
    for article in articles:
        try:
            result = distributor.run(article, dry_run=dry_run)
            dist_results.append(result)
            # 収益ログ記録
            record_post(
                keyword=article.get("keyword", ""),
                category=article.get("category", ""),
                platform="hatena+note+x+bsky",
                success=any(result.values()),
            )
        except Exception as e:
            print(f"  ❌ Distributor エラー: {e}")

    # ─────────────────────────────────────────────────
    # PHASE 5: ステート更新 & サマリー
    # ─────────────────────────────────────────────────
    state["total_articles"] = state.get("total_articles", 0) + len(articles)
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
    print(f"  📝 生成記事: {len(articles)}本  |  配信成功: {total_success}件")
    print(f"  📊 今日の累計: {state['today_articles']}本  |  通算: {state['total_articles']}本")
    print("=" * 60)

    print_dashboard()


# ── エントリーポイント ─────────────────────────────────────────

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "dry-run"

    if mode == "run":
        run_ceo(dry_run=False)
    elif mode == "dry-run":
        run_ceo(dry_run=True)
    elif mode == "dashboard":
        print_dashboard()
        state = _load_state()
        print(f"\n通算記事数: {state.get('total_articles', 0)}本")
        print(f"今日の記事数: {state.get('today_articles', 0)}本")
        print(f"最終実行: {state.get('last_run', '-')}")
    else:
        print(f"不明なモード: {mode}")
        sys.exit(1)
