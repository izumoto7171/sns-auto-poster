"""
A8.net 提携承認済みプログラムの自動同期スクリプト

【フロー】
1. A8.net にログイン（requests セッション）
2. 提携済みプログラム一覧を全ページ取得
3. program_portfolio.json の status="candidate" 案件と名前照合
4. マッチした案件:
   - ins_id を記録
   - fetch_best_link() でアフィリエイトURLを取得
   - status="active" に更新・portfolio.json に書き戻し
5. サマリーを出力

【実行】
  python3 money_agent/a8_sync_approved.py           # 通常実行
  python3 money_agent/a8_sync_approved.py --dry-run # 書き込みなし・確認のみ
  python3 money_agent/a8_sync_approved.py --force   # 既存 active も含め URL を再取得
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path

ROOT_DIR       = Path(__file__).parent.parent
PORTFOLIO_PATH = ROOT_DIR / "money_agent" / "config" / "program_portfolio.json"

sys.path.insert(0, str(ROOT_DIR / "money_agent"))
sys.path.insert(0, str(ROOT_DIR))
from utils.notifier import notify as _discord_notify

A8_PUB_BASE       = "https://pub.a8.net"
PARTNER_LIST_URL  = f"{A8_PUB_BASE}/a8v2/media/partnerProgramListAction.do"

# 名前照合の最低類似度（0.0〜1.0）
MATCH_THRESHOLD = 0.65


def load_env():
    env_path = ROOT_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def _similarity(a: str, b: str) -> float:
    """2つの文字列の類似度（0.0〜1.0）"""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _safe_text(element, default: str = "") -> str:
    if element is None:
        return default
    try:
        return element.get_text(strip=True)
    except Exception:
        return default


# ── A8.net ログイン ────────────────────────────────────────────

def a8_login():
    """
    requests セッションで A8.net にログインする。
    a8_approved_auto.py の実装を流用。
    """
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        print("[Sync] requests または beautifulsoup4 未インストール")
        return None

    media_id = os.environ.get("A8_MEDIA_ID", "")
    password = os.environ.get("A8_PASSWORD", "")
    if not media_id or not password:
        print("[Sync] A8_MEDIA_ID / A8_PASSWORD が未設定")
        return None

    login_url = f"{A8_PUB_BASE}/a8v2/media/loginAction.do"
    headers   = {
        "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ja,en;q=0.9",
    }

    session = requests.Session()
    session.headers.update(headers)

    for attempt in range(3):
        try:
            resp = session.get(login_url, timeout=30)
            from bs4 import BeautifulSoup
            soup    = BeautifulSoup(resp.text, "html.parser")
            payload = {"login": media_id, "passwd": password, "moa": "/a8"}
            for inp in soup.select("input[type=hidden]"):
                name = inp.get("name")
                val  = inp.get("value", "")
                if name and name not in payload:
                    payload[name] = val

            login_resp = session.post(login_url, data=payload, timeout=30)
            if "logoutAction" in login_resp.text or "ログアウト" in login_resp.text:
                print("[Sync] ログイン成功")
                return session
            else:
                print("[Sync] ログイン失敗（ID/パスワードを確認してください）")
                _discord_notify(
                    "money_agent/a8_sync_approved.py",
                    "A8.net ログイン失敗（ID/パスワード不一致の可能性）",
                    "A8_MEDIA_ID / A8_PASSWORD を確認してください",
                )
                return None

        except Exception as e:
            wait = 10 * (attempt + 1)
            print(f"[Sync] ログインエラー ({attempt + 1}/3): {e} → {wait}秒後にリトライ")
            if attempt == 2:
                _discord_notify(
                    "money_agent/a8_sync_approved.py",
                    "A8.net ログイン失敗（リトライ上限到達）",
                    str(e),
                )
            time.sleep(wait)

    return None


# ── 提携済みプログラム一覧取得（全ページ） ─────────────────────

def fetch_all_approved(session) -> list[dict]:
    """
    A8.net の提携済みプログラム一覧を全ページ取得する。
    各エントリ: {"ins_id": str, "name": str, "company": str, "reward": str, "epc": float}
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    all_programs: list[dict] = []
    page_num = 1

    while True:
        url    = f"{PARTNER_LIST_URL}?act=search&p={page_num}"
        try:
            resp   = session.get(url, timeout=15)
            soup   = BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            print(f"[Sync] ページ {page_num} 取得エラー: {e}")
            break

        link_elements = soup.select("a[href*='linkAction.do?insId=']")
        if not link_elements:
            # これ以上ページがない
            break

        page_programs: list[dict] = []
        for a in link_elements:
            try:
                href      = a.get("href", "") or ""
                ins_match = re.search(r"insId=([^&]+)", href)
                if not ins_match:
                    continue
                ins_id = ins_match.group(1)
                if any(p["ins_id"] == ins_id for p in page_programs):
                    continue

                # 親コンテナから情報を抽出
                container = a
                for _ in range(12):
                    parent = getattr(container, "parent", None)
                    if parent is None:
                        break
                    container = parent
                    text      = container.get_text(" ", strip=True)
                    if "成果報酬" in text or "EPC" in text:
                        break

                text = container.get_text(" ", strip=True)

                name_m    = re.search(r"プログラム名\s*(.+?)(?:対応デバイス|成果報酬|$)", text)
                company_m = re.search(r"広告主名\s*(.+?)(?:プログラム名|$)", text)
                reward_m  = re.search(r"成果報酬\s*(.+?)(?:EPC|確定率|$)", text)
                epc_m     = re.search(r"EPC\s+([\d.]+)", text)

                name    = name_m.group(1).strip()[:80]   if name_m    else ins_id
                company = company_m.group(1).strip()[:50] if company_m else ""
                reward  = reward_m.group(1).strip()[:100] if reward_m  else ""
                epc     = float(epc_m.group(1))           if epc_m     else 0.0

                page_programs.append({
                    "ins_id":  ins_id,
                    "name":    name,
                    "company": company,
                    "reward":  reward,
                    "epc":     epc,
                })
            except Exception as e:
                print(f"[Sync] アイテム解析スキップ: {e}")
                continue

        all_programs.extend(page_programs)
        print(f"[Sync] ページ {page_num}: {len(page_programs)}件取得（累計 {len(all_programs)}件）")

        # 次ページへのリンクがなければ終了
        next_link = soup.select_one("a[href*='p={}']".format(page_num + 1))
        if not next_link:
            break

        page_num += 1
        time.sleep(1)

    print(f"[Sync] 提携済みプログラム合計: {len(all_programs)}件")
    return all_programs


# ── 候補との名前照合 ──────────────────────────────────────────

def match_candidates(
    candidates: list[dict],
    approved: list[dict],
) -> list[tuple[dict, dict, float]]:
    """
    candidate × approved を照合し、類似度が閾値以上のペアを返す。
    Returns: [(candidate, approved_program, similarity), ...]
    """
    matches = []
    for cand in candidates:
        cand_name = cand.get("name", "")
        best_sim  = 0.0
        best_prog = None

        for prog in approved:
            sim = _similarity(cand_name, prog["name"])
            if sim > best_sim:
                best_sim  = sim
                best_prog = prog

        if best_prog and best_sim >= MATCH_THRESHOLD:
            matches.append((cand, best_prog, best_sim))
            print(f"  マッチ [{best_sim:.0%}] {cand_name!r} ≒ {best_prog['name']!r}")
        else:
            top = f"({best_prog['name']!r} {best_sim:.0%})" if best_prog else ""
            print(f"  未マッチ [{best_sim:.0%}] {cand_name!r} {top}")

    return matches


# ── アフィリエイトURL取得（a8_approved_auto.py の実装を再利用） ─

def fetch_best_link(session, ins_id: str) -> str:
    """EPC 最高のテキストリンクを返す（a8_approved_auto.py と同実装）"""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return ""

    url = f"{A8_PUB_BASE}/a8v2/media/linkAction.do?insId={ins_id}"
    try:
        resp = session.get(url, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text("\n")
    except Exception as e:
        print(f"[Sync] リンクページ取得エラー ({ins_id}): {e}")
        return ""

    best_url = ""
    best_epc = -1.0
    lines    = [l.strip() for l in text.split("\n") if l.strip()]

    for i, line in enumerate(lines):
        if not line.startswith("https://px.a8.net"):
            continue
        try:
            context = lines[max(0, i - 10):i]
            epc_val = 0.0
            for ctx in reversed(context):
                m = re.match(r"^([\d.]+)$", ctx)
                if m:
                    try:
                        epc_val = float(m.group(1))
                    except ValueError:
                        pass
                    break
            is_text = any("テキスト" in c or "メール" in c for c in context[-15:])
            if is_text and epc_val > best_epc:
                best_epc = epc_val
                best_url = line
        except Exception:
            continue

    if not best_url:
        for line in lines:
            if line.startswith("https://px.a8.net"):
                best_url = line
                break

    return best_url


# ── portfolio.json 更新 ───────────────────────────────────────

def update_portfolio(
    candidate: dict,
    approved_prog: dict,
    affiliate_url: str,
    dry_run: bool,
) -> None:
    """candidate エントリを active に昇格させて portfolio.json を更新する"""
    data     = json.loads(PORTFOLIO_PATH.read_text(encoding="utf-8"))
    programs = data["programs"]

    for p in programs:
        if p.get("id") == candidate.get("id"):
            if dry_run:
                print(f"    [DryRun] {p['name']} → active (url={affiliate_url[:60]}...)")
                return

            p["status"]        = "active"
            p["affiliate_url"] = affiliate_url
            p["ins_id"]        = approved_prog["ins_id"]
            p["epc"]           = approved_prog.get("epc", 0.0)
            p["reward"]        = approved_prog.get("reward", p.get("reward", ""))
            p["company"]       = approved_prog.get("company", p.get("company", ""))
            break
    else:
        print(f"    [警告] portfolio にID {candidate.get('id')} が見つかりません")
        return

    PORTFOLIO_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"    [更新] {candidate['name']} → status=active  ins_id={approved_prog['ins_id']}")


# ── メイン ──────────────────────────────────────────────────────

def run(dry_run: bool = False, force: bool = False) -> None:
    print(f"\n=== A8.net 提携同期 開始 {'[DRY RUN]' if dry_run else ''} ===")

    # candidate を読み込む
    data       = json.loads(PORTFOLIO_PATH.read_text(encoding="utf-8"))
    all_progs  = data.get("programs", [])
    candidates = [p for p in all_progs if p.get("status") == "candidate"]

    if force:
        # --force 時は active も対象（affiliate_url 再取得）
        candidates += [p for p in all_progs if p.get("status") == "active"]
        print(f"[Sync] --force モード: active 含む {len(candidates)}件を対象")
    else:
        print(f"[Sync] candidate 案件: {len(candidates)}件")

    if not candidates:
        print("[Sync] 対象案件なし。終了。")
        return

    # A8.net ログイン
    session = a8_login()
    if not session:
        print("[Sync] ログイン失敗。終了。")
        return

    # 提携済み一覧を取得
    approved = fetch_all_approved(session)
    if not approved:
        print("[Sync] 提携済みプログラムが取得できませんでした。終了。")
        return

    # 名前照合
    print("\n[Sync] 名前照合中...")
    matches = match_candidates(candidates, approved)
    print(f"\n[Sync] マッチ: {len(matches)}件 / {len(candidates)}件")

    if not matches:
        print("[Sync] 承認済み案件が見つかりませんでした。")
        return

    # 各マッチをアップデート
    updated = 0
    for candidate, approved_prog, sim in matches:
        print(f"\n  処理: {candidate['name']} (類似度 {sim:.0%})")
        print(f"    A8 プログラム: {approved_prog['name']} (ins_id={approved_prog['ins_id']})")

        affiliate_url = fetch_best_link(session, approved_prog["ins_id"])
        if not affiliate_url:
            print(f"    アフィリエイトURL取得失敗。スキップ。")
            continue

        print(f"    URL: {affiliate_url[:80]}")
        update_portfolio(candidate, approved_prog, affiliate_url, dry_run)
        if not dry_run:
            updated += 1
        time.sleep(1)

    print(f"\n=== 完了: {updated}件を active に昇格 ===")
    if dry_run:
        print("（--dry-run のため実際の書き込みは行っていません）")


def main():
    load_env()
    parser = argparse.ArgumentParser(description="A8.net 提携承認済み案件の自動同期")
    parser.add_argument("--dry-run", action="store_true", help="書き込みなし・確認のみ")
    parser.add_argument("--force",   action="store_true", help="active 案件も含め URL を再取得")
    args = parser.parse_args()
    run(dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    main()
