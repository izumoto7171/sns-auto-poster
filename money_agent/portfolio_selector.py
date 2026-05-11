"""
アフィリエイト案件ポートフォリオ自動選択

【役割】
  - program_portfolio.json から案件を読み込み
  - テーマ・クールダウン・Supabase クリック実績で重み付けして選択
  - 1つの案件への依存を防ぎ、リスク分散と収益最大化を両立する

【使い方】
  from money_agent.portfolio_selector import select_program, select_programs_for_theme

  # 単一選択（記事生成1件ぶん）
  program = select_program(theme="side_hustle")

  # 複数選択（note 記事に2案件埋め込む場合など）
  programs = select_programs_for_theme(theme="tax", count=2)
"""

import json
import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

PORTFOLIO_FILE = Path(__file__).parent / "data" / "program_portfolio.json"

# 同一案件を再利用するまでの最短日数
COOLDOWN_DAYS = 3

# テーマエイリアス（SNS用テーマ → ポートフォリオのテーマキー）
THEME_ALIASES = {
    "ai_tools":          ["ai_tools", "side_hustle", "productivity"],
    "side_hustle":       ["side_hustle", "freelance", "startup"],
    "investment_savings":["investment_savings", "nisa", "tax"],
    "productivity":      ["productivity", "ai_tools", "lifestyle"],
    "lifestyle":         ["lifestyle", "investment_savings"],
    "tax":               ["tax", "accounting", "freelance"],
    "freelance":         ["freelance", "side_hustle", "accounting"],
    "accounting":        ["accounting", "tax", "freelance"],
    "blog":              ["blog", "side_hustle", "ai_tools"],
    "startup":           ["startup", "freelance", "side_hustle"],
    "nisa":              ["nisa", "investment_savings", "tax"],
}


# ── ファイル操作 ──────────────────────────────────────────

def _load() -> dict:
    return json.loads(PORTFOLIO_FILE.read_text(encoding="utf-8"))


def _save(data: dict):
    PORTFOLIO_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Supabase からクリック実績を取得 ──────────────────────────

def _get_click_scores() -> dict[str, int]:
    """
    Supabase affiliate_links から campaign_id ごとのクリック数合計を返す。
    Supabase未設定の場合は空dictを返す（クリック実績なしとして扱う）。
    """
    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    supabase_key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not (supabase_url and supabase_key):
        return {}

    try:
        import requests
        r = requests.get(
            f"{supabase_url}/rest/v1/affiliate_links"
            f"?select=campaign_id,click_count"
            f"&click_count=gt.0",
            headers={
                "apikey":        supabase_key,
                "Authorization": f"Bearer {supabase_key}",
            },
            timeout=10,
        )
        r.raise_for_status()
        scores: dict[str, int] = {}
        for rec in r.json():
            cid = rec.get("campaign_id", "")
            if cid:
                scores[cid] = scores.get(cid, 0) + rec.get("click_count", 0)
        return scores
    except Exception as e:
        print(f"[Portfolio] Supabaseクリック取得スキップ: {e}")
        return {}


# ── クールダウン判定 ──────────────────────────────────────

def _is_cooled_down(program: dict) -> bool:
    """last_used_at から COOLDOWN_DAYS 以上経過していれば True"""
    last = program.get("last_used_at")
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) - last_dt >= timedelta(days=COOLDOWN_DAYS)
    except Exception:
        return True


# ── 重み計算 ──────────────────────────────────────────────

def _calc_weight(program: dict, click_scores: dict[str, int]) -> float:
    """
    案件の選択重みを計算する。
    - EPC が高いほど有利
    - Supabase クリック数が多いほど有利（実績補正）
    - priority が低い数字ほど有利
    """
    base   = max(program.get("epc", 0), 0.1)                    # EPC（最低0.1）
    clicks = click_scores.get(program["id"], 0)
    click_bonus = min(clicks * 0.5, 20.0)                       # クリック補正（上限20）
    priority_bonus = max(10 - program.get("priority", 9), 0)    # 優先度補正
    return base + click_bonus + priority_bonus


# ── メイン選択ロジック ────────────────────────────────────

def select_program(theme: str = None, exclude_ids: list = None) -> Optional[dict]:
    """
    テーマに合ったアクティブな案件を1件選択して返す。

    Args:
        theme:       コンテンツのテーマ（'side_hustle', 'tax' など）
        exclude_ids: 同一記事内で既に使用した案件ID（重複防止）

    Returns:
        案件dict（id, name, affiliate_url, description, ... 含む）
        候補なしの場合は None
    """
    data = _load()
    programs = data.get("programs", [])
    exclude_ids = exclude_ids or []

    # アクティブ & 除外なし & クールダウン済み
    candidates = [
        p for p in programs
        if p.get("status") == "active"
        and p["id"] not in exclude_ids
        and _is_cooled_down(p)
    ]

    if not candidates:
        # クールダウン中でも候補なしなら全アクティブから選ぶ（フォールバック）
        candidates = [
            p for p in programs
            if p.get("status") == "active" and p["id"] not in exclude_ids
        ]

    if not candidates:
        print("[Portfolio] 選択可能な案件がありません")
        return None

    # テーマフィルタ（一致する候補があれば優先）
    if theme:
        target_themes = THEME_ALIASES.get(theme, [theme])
        themed = [
            p for p in candidates
            if any(t in p.get("themes", []) for t in target_themes)
        ]
        if themed:
            candidates = themed

    # Supabase クリック実績で重み付き抽選
    click_scores = _get_click_scores()
    weights = [_calc_weight(p, click_scores) for p in candidates]
    total   = sum(weights)
    if total == 0:
        selected = random.choice(candidates)
    else:
        r = random.uniform(0, total)
        cumulative = 0.0
        selected = candidates[-1]
        for p, w in zip(candidates, weights):
            cumulative += w
            if r <= cumulative:
                selected = p
                break

    print(
        f"[Portfolio] 選択: {selected['name']} "
        f"(theme={theme}, epc={selected.get('epc', 0)}, "
        f"clicks={click_scores.get(selected['id'], 0)})"
    )
    return selected


def select_programs_for_theme(theme: str = None, count: int = 2) -> list[dict]:
    """
    記事に埋め込む複数案件をまとめて選択する（重複なし）。

    Args:
        theme: コンテンツのテーマ
        count: 取得件数

    Returns:
        案件dictのリスト（取得できた分だけ返す）
    """
    result = []
    used_ids = []
    for _ in range(count):
        p = select_program(theme=theme, exclude_ids=used_ids)
        if p is None:
            break
        result.append(p)
        used_ids.append(p["id"])
    return result


def mark_program_used(program_id: str):
    """
    案件を「使用済み」にしてクールダウンを開始する。
    select_program() で得た案件を記事に使用した後に呼び出す。
    """
    data = _load()
    for p in data.get("programs", []):
        if p["id"] == program_id:
            p["last_used_at"] = _utcnow()
            _save(data)
            print(f"[Portfolio] クールダウン開始: {p['name']} ({COOLDOWN_DAYS}日間)")
            return
    print(f"[Portfolio] ID '{program_id}' が見つかりません")


def add_program(program: dict):
    """
    新規案件をポートフォリオに追加する。
    A8.netで新規承認されたときに呼び出す。

    Args:
        program: {id, name, company, category, themes, reward, epc,
                  confirm_rate, affiliate_url, description, priority} を含むdict
    """
    data = _load()
    existing_ids = [p["id"] for p in data.get("programs", [])]
    if program["id"] in existing_ids:
        print(f"[Portfolio] '{program['id']}' は既に登録済みです")
        return

    program.setdefault("status",       "active")
    program.setdefault("last_used_at", None)
    program.setdefault("priority",     len(data["programs"]) + 1)
    data["programs"].append(program)
    _save(data)
    print(f"[Portfolio] 追加完了: {program['name']}")


def show_status():
    """現在のポートフォリオ状況をコンソールに表示"""
    data    = _load()
    click_scores = _get_click_scores()
    programs = data.get("programs", [])

    active  = [p for p in programs if p.get("status") == "active"]
    pending = [p for p in programs if p.get("status") != "active"]

    print(f"\n=== アフィリエイトポートフォリオ ({len(programs)}件) ===\n")
    print(f"【アクティブ ({len(active)}件)】")
    for p in sorted(active, key=lambda x: x.get("priority", 99)):
        cooled  = "✅" if _is_cooled_down(p) else f"💤{COOLDOWN_DAYS}d"
        clicks  = click_scores.get(p["id"], 0)
        weight  = _calc_weight(p, click_scores)
        last    = p.get("last_used_at", "未使用") or "未使用"
        print(
            f"  [{cooled}] {p['name']:<30} "
            f"EPC:{p.get('epc',0):>6.2f} "
            f"clicks:{clicks:>4} "
            f"weight:{weight:>6.1f} "
            f"最終:{last[:10]}"
        )

    if pending:
        print(f"\n【非アクティブ ({len(pending)}件)】")
        for p in pending:
            print(f"  [{p.get('status','?')}] {p['name']}")
    print()


if __name__ == "__main__":
    import sys
    from pathlib import Path as _Path

    env_path = _Path(__file__).parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        show_status()
    elif cmd == "select":
        theme = sys.argv[2] if len(sys.argv) > 2 else None
        p = select_program(theme=theme)
        if p:
            print(f"\n選択結果: {p['name']}")
            print(f"  URL: {p['affiliate_url'][:60]}...")
