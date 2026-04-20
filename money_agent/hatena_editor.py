"""
はてなブログ記事エディター
比較クエリで流入している記事に「機能比較表」と「選定ガイド」を自動挿入する

【処理フロー】
1. search_console_analysis.json から「比較クエリ × 11〜20位」を抽出
2. Hatena AtomPub API で記事一覧を取得 → キーワードマッチで対象記事を特定
3. Gemini で「機能比較表」「あなたに向いているのはどっち？」を生成
4. AtomPub PUT で記事を更新（挿入済みはスキップ）

【実行方法】
  python3 money_agent/hatena_editor.py            # 自動モード
  python3 money_agent/hatena_editor.py dry-run    # 更新せず内容を確認
"""

import base64
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import requests

BASE_DIR        = Path(__file__).parent
ANALYSIS_FILE   = BASE_DIR / "search_console_analysis.json"
EDIT_LOG_FILE   = BASE_DIR / "hatena_edit_log.json"

HATENA_ID      = os.environ.get("HATENA_ID", "")
HATENA_BLOG_ID = os.environ.get("HATENA_BLOG_ID", "")
HATENA_API_KEY = os.environ.get("HATENA_API_KEY", "")

# Atom名前空間
ATOM_NS = "http://www.w3.org/2005/Atom"
APP_NS  = "http://www.w3.org/2007/app"
NS      = {"atom": ATOM_NS, "app": APP_NS}

# 比較対象ツールの別名定義
TOOL_ALIASES: dict[str, list[str]] = {
    "freee":        ["freee", "フリー"],
    "moneyforward": ["マネーフォワード", "マネフォ", "moneyforward", "mf クラウド"],
    "yayoi":        ["弥生", "やよい"],
    "chatwork":     ["chatwork", "チャットワーク"],
    "misoca":       ["misoca", "ミソカ"],
}

TOOL_DISPLAY_NAMES: dict[str, str] = {
    "freee":        "freee会計",
    "moneyforward": "マネーフォワード クラウド",
    "yayoi":        "弥生会計オンライン",
    "chatwork":     "Chatwork",
    "misoca":       "Misoca（弥生）",
}

# 比較クエリの検出シグナル
COMPARISON_SIGNALS = ["比較", "違い", "どっち", "vs ", "versus", "どちら"]

# 挿入済みマーカー（冪等性のため）
SENTINEL = "<!-- hatena_editor:comparison_inserted -->"


# ── 認証 ──────────────────────────────────────────────────────
def _auth_header() -> str:
    token = base64.b64encode(f"{HATENA_ID}:{HATENA_API_KEY}".encode()).decode()
    return f"Basic {token}"


# ── エントリ一覧取得 ────────────────────────────────────────
def _fetch_entry_list(max_pages: int = 5) -> list[dict]:
    """
    AtomPub でエントリ一覧を取得（最大 max_pages ページ）
    Returns: [{"title": str, "url": str, "entry_id": str}]
    """
    entries = []
    url     = f"https://blog.hatena.ne.jp/{HATENA_ID}/{HATENA_BLOG_ID}/atom/entry"
    headers = {"Authorization": _auth_header()}

    for _ in range(max_pages):
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code != 200:
                print(f"[HatenaEditor] エントリ一覧取得失敗 HTTP {resp.status_code}")
                break

            root = ET.fromstring(resp.text)

            for entry in root.findall(f"{{{ATOM_NS}}}entry"):
                title_el = entry.find(f"{{{ATOM_NS}}}title")
                title    = title_el.text or "" if title_el is not None else ""

                # link rel="alternate" を検索
                url_alt = ""
                for link_el in entry.findall(f"{{{ATOM_NS}}}link"):
                    if link_el.get("rel") == "alternate":
                        url_alt = link_el.get("href", "")
                        break

                id_el  = entry.find(f"{{{ATOM_NS}}}id")
                raw_id = id_el.text or "" if id_el is not None else ""
                # "tag:blog.hatena.ne.jp,2013:blog-xxx-12345678" → "12345678"
                m        = re.search(r"-(\d+)$", raw_id)
                entry_id = m.group(1) if m else ""

                if entry_id:
                    entries.append({"title": title, "url": url_alt, "entry_id": entry_id})

            # 次ページ
            next_url = ""
            for link_el in root.findall(f"{{{ATOM_NS}}}link"):
                if link_el.get("rel") == "next":
                    next_url = link_el.get("href", "")
                    break
            if next_url:
                url = next_url
            else:
                break

        except Exception as e:
            print(f"[HatenaEditor] エントリ一覧取得エラー: {e}")
            break

    return entries


# ── エントリ本文取得 ──────────────────────────────────────
def _fetch_entry_body(entry_id: str) -> tuple[str, str]:
    """
    entry_id の記事本文（HTML）とタイトルを返す
    Returns: (title, html_body)
    """
    url  = f"https://blog.hatena.ne.jp/{HATENA_ID}/{HATENA_BLOG_ID}/atom/entry/{entry_id}"
    resp = requests.get(url, headers={"Authorization": _auth_header()}, timeout=30)
    if resp.status_code != 200:
        return "", ""

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as e:
        print(f"[HatenaEditor] XML解析エラー: {e}")
        return "", ""

    title_el   = root.find(f"{{{ATOM_NS}}}title")
    title      = title_el.text or "" if title_el is not None else ""
    content_el = root.find(f"{{{ATOM_NS}}}content")
    body       = content_el.text or "" if content_el is not None else ""
    return title, body


# ── エントリ更新 ─────────────────────────────────────────
def _update_entry(entry_id: str, title: str, body_html: str) -> bool:
    """AtomPub PUT で記事を更新"""
    url     = f"https://blog.hatena.ne.jp/{HATENA_ID}/{HATENA_BLOG_ID}/atom/entry/{entry_id}"
    headers = {
        "Authorization": _auth_header(),
        "Content-Type":  "application/atom+xml; charset=utf-8",
    }
    atom_xml = f"""<?xml version="1.0" encoding="utf-8"?>
<entry xmlns="http://www.w3.org/2005/Atom"
       xmlns:app="http://www.w3.org/2007/app">
  <title>{title}</title>
  <author><name>{HATENA_ID}</name></author>
  <content type="text/html">{body_html}</content>
  <app:control>
    <app:draft>no</app:draft>
  </app:control>
</entry>"""

    try:
        resp = requests.put(url, data=atom_xml.encode("utf-8"), headers=headers, timeout=30)
        if resp.status_code in (200, 201):
            return True
        print(f"[HatenaEditor] PUT失敗 HTTP {resp.status_code}: {resp.text[:300]}")
        return False
    except Exception as e:
        print(f"[HatenaEditor] 更新エラー: {e}")
        return False


# ── SC分析から比較クエリを抽出 ──────────────────────────
def _load_comparison_queries() -> list[dict]:
    """
    search_console_analysis.json から「比較シグナルを含むクエリ」を返す。
    low_position_queries（11-20位） + top_queries（クリック多数）の両方を対象にする。
    """
    if not ANALYSIS_FILE.exists():
        return []
    try:
        data = json.loads(ANALYSIS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []

    pool = data.get("low_position_queries", []) + data.get("top_queries", [])
    seen: set[str] = set()
    result = []
    for q in pool:
        query = q.get("query", "")
        if query in seen:
            continue
        seen.add(query)
        if any(sig in query for sig in COMPARISON_SIGNALS):
            result.append(q)

    return result


# ── クエリからツールペアを抽出 ──────────────────────────
def _extract_tool_pair(query: str) -> tuple[str, str] | None:
    """
    "freee マネーフォワード 比較" → ("freee会計", "マネーフォワード クラウド")
    2ツール検出できなければ None
    """
    query_lower = query.lower()
    detected    = []
    for tool_key, aliases in TOOL_ALIASES.items():
        for alias in aliases:
            if alias.lower() in query_lower:
                detected.append(tool_key)
                break

    if len(detected) >= 2:
        return (
            TOOL_DISPLAY_NAMES.get(detected[0], detected[0]),
            TOOL_DISPLAY_NAMES.get(detected[1], detected[1]),
        )
    return None


# ── Gemini で比較セクションを生成 ──────────────────────
def _generate_comparison_sections(tool_a: str, tool_b: str, query: str) -> tuple[str, str]:
    """
    Gemini で機能比較表と選定ガイドを生成し、HTML変換して返す。
    Returns: (comparison_table_html, selection_guide_html)
    """
    sys.path.insert(0, str(BASE_DIR))
    from gemini_client import generate as gemini_generate, strip_code_block
    from hatena_atomapi import markdown_to_html

    prompt = f"""あなたはSEOライターです。以下の2ツールを比較する記事セクションを生成してください。

比較対象: {tool_a} vs {tool_b}
検索クエリ: {query}
想定読者: どちらを使えばいいか迷っている中小企業の経営者・経理担当者

## 出力1: 機能比較表（Markdown形式）
次の比較項目を必ず含めること:
- 月額料金（最安プラン）
- 無料トライアル期間
- 確定申告・税務申告対応
- 請求書発行
- 給与計算
- 経費精算
- 銀行・クレカ自動連携
- スマホアプリ
- サポート体制
- 向いているユーザー規模

## 出力2: 選定ガイド「あなたに向いているのはどっち？」（Markdown形式）
### {tool_a}を選ぶべき人（3〜5個の具体的なシナリオ）
### {tool_b}を選ぶべき人（3〜5個の具体的なシナリオ）
### 迷ったときの判断基準（1〜2段落）

制約:
- 価格は「目安」として記載し「変更になる場合あり」と注記する
- 過度な誇張なし、実践的な情報のみ

JSONで返してください（keyは comparison_table, selection_guide）:
{{"comparison_table": "Markdownテキスト", "selection_guide": "Markdownテキスト"}}"""

    raw = gemini_generate(prompt, use_cache=False)
    if not raw:
        return "", ""

    try:
        cleaned = strip_code_block(raw)
        data    = json.loads(cleaned)
        table_md = data.get("comparison_table", "")
        guide_md = data.get("selection_guide", "")
    except Exception:
        # JSON解析失敗時: 全文をガイドとして扱う
        print("[HatenaEditor] Gemini JSON解析失敗 — 全文をguideとして使用")
        table_md = ""
        guide_md = raw

    return markdown_to_html(table_md), markdown_to_html(guide_md)


# ── 記事への挿入 ─────────────────────────────────────────
def _insert_sections(html: str, table_html: str, guide_html: str) -> str:
    """
    比較表と選定ガイドを記事内の適切な位置に挿入する。
    SENTINEL があれば既に挿入済みとしてスキップ。
    """
    if SENTINEL in html:
        return html

    insert_block = (
        f"\n{SENTINEL}\n"
        f"<h2>機能比較表</h2>\n{table_html}\n"
        f"<h2>あなたに向いているのはどっち？</h2>\n{guide_html}\n"
    )

    # 挿入アンカー候補（先頭マッチした位置の直前に挿入）
    anchors = [
        r"<h2[^>]*>まとめ",
        r"<h2[^>]*>おすすめ",
        r"<h2[^>]*>料金",
        r"<h2[^>]*>選び方",
    ]
    for pattern in anchors:
        m = re.search(pattern, html, re.IGNORECASE)
        if m:
            return html[: m.start()] + insert_block + html[m.start() :]

    # アンカーが見つからなければ末尾に追加
    return html + insert_block


# ── タイトルとクエリのマッチングスコア ────────────────────
def _score_match(title: str, query: str) -> int:
    """タイトルにクエリの単語が何個含まれるかを返す（2文字以上の語のみ）"""
    title_lower = title.lower()
    score = 0
    for word in re.split(r"[\s　]+", query.lower()):
        if len(word) >= 2 and word in title_lower:
            score += 1
    return score


# ── 編集ログ ──────────────────────────────────────────────
def _load_edit_log() -> dict:
    if EDIT_LOG_FILE.exists():
        try:
            return json.loads(EDIT_LOG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_edit_log(log: dict) -> None:
    EDIT_LOG_FILE.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")


EDITOR_RESULT_FILE = Path("/tmp/editor_result.json")


def _write_result(result: dict):
    """GitHub Actions サマリー用に結果ファイルを書き出す（常に成功）"""
    try:
        EDITOR_RESULT_FILE.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        print(f"[HatenaEditor] 結果ファイル書き出し失敗: {e}")


# ── メイン処理 ────────────────────────────────────────────
def run(dry_run: bool = False) -> dict:
    """
    比較クエリ流入記事への比較表・ガイド自動挿入。

    失敗しても sys.exit(1) しない「ソフトエラー」設計。
    処理結果は /tmp/editor_result.json に書き出す。
    """
    print("[HatenaEditor] 比較クエリ流入記事への自動挿入を開始...")

    # API キー未設定は skip 扱い（エラーではない）
    if not HATENA_API_KEY:
        msg = "HATENA_API_KEY 未設定"
        print(f"[HatenaEditor] {msg} — スキップ（ソフトエラー）")
        result = {"status": "skip", "reason": "no_api_key", "error_summary": msg,
                  "updated": 0, "skipped": 0, "results": []}
        _write_result(result)
        return result

    # 比較クエリ抽出
    comparison_queries = _load_comparison_queries()
    if not comparison_queries:
        msg = f"比較クエリなし（{ANALYSIS_FILE.name} が未生成か比較シグナルのクエリが0件）"
        print(f"[HatenaEditor] {msg} — スキップ")
        result = {"status": "skip", "reason": "no_comparison_queries", "error_summary": msg,
                  "updated": 0, "skipped": 0, "results": []}
        _write_result(result)
        return result

    preview = [q["query"] for q in comparison_queries[:3]]
    print(f"[HatenaEditor] 比較クエリ {len(comparison_queries)} 件: {preview}")

    # エントリ一覧取得
    entries = _fetch_entry_list(max_pages=5)
    if not entries:
        msg = "AtomPub エントリ一覧取得失敗（API認証 or ネットワーク問題の可能性）"
        print(f"[HatenaEditor] {msg}")
        result = {"status": "error", "reason": "fetch_entries_failed", "error_summary": msg,
                  "updated": 0, "skipped": 0, "results": []}
        _write_result(result)
        return result

    print(f"[HatenaEditor] エントリ取得: {len(entries)} 件")

    edit_log      = _load_edit_log()
    updated_count = 0
    skipped_count = 0
    results       = []
    errors        = []  # 1行エラーサマリー収集

    # 各比較クエリについて対応記事を検索・更新
    for q_info in comparison_queries:
        query    = q_info["query"]
        position = q_info.get("position", 0)

        tool_pair = _extract_tool_pair(query)
        if not tool_pair:
            print(f"  [HatenaEditor] ツールペア抽出不可: {query}")
            continue

        tool_a, tool_b = tool_pair

        # タイトルスコアリングで最適記事を特定
        scored   = sorted(entries, key=lambda e: _score_match(e["title"], query), reverse=True)
        best     = scored[0]
        score    = _score_match(best["title"], query)

        if score == 0:
            print(f"  [HatenaEditor] 対応記事なし（スコア0）: {query}")
            continue

        entry_id = best["entry_id"]
        title    = best["title"]

        # 編集済みチェック（ログ）
        if edit_log.get(entry_id, {}).get("comparison_inserted"):
            print(f"  [HatenaEditor] 挿入済みスキップ: {title[:40]}")
            skipped_count += 1
            continue

        print(f"  [HatenaEditor] 対象: 「{title[:50]}」 順位:{position:.1f} スコア:{score}")

        # 記事本文を取得
        try:
            _, body_html = _fetch_entry_body(entry_id)
        except Exception as e:
            msg = f"本文取得例外 ({entry_id}): {type(e).__name__}: {e}"
            print(f"  [HatenaEditor] {msg}")
            errors.append(msg)
            results.append({"query": query, "entry_id": entry_id, "title": title,
                             "status": "error", "error": msg})
            continue

        if not body_html:
            msg = f"本文が空 ({entry_id}): AtomPub PUT 認証エラーの可能性"
            print(f"  [HatenaEditor] {msg}")
            errors.append(msg)
            results.append({"query": query, "entry_id": entry_id, "title": title,
                             "status": "error", "error": msg})
            continue

        # 挿入済みマーカーチェック
        if SENTINEL in body_html:
            print(f"  [HatenaEditor] 本文に挿入済みマーカーあり — スキップ")
            skipped_count += 1
            continue

        # Gemini で比較セクション生成
        print(f"  [HatenaEditor] Gemini生成: {tool_a} vs {tool_b}")
        try:
            table_html, guide_html = _generate_comparison_sections(tool_a, tool_b, query)
        except Exception as e:
            msg = f"Gemini生成例外 ({query}): {type(e).__name__}: {e}"
            print(f"  [HatenaEditor] {msg}")
            errors.append(msg)
            results.append({"query": query, "entry_id": entry_id, "title": title,
                             "status": "error", "error": msg})
            continue

        # Gemini 生成失敗 → 末尾に警告コメントだけ挿入してソフトエラー
        if not table_html and not guide_html:
            msg = f"Gemini生成結果が空 ({query}): Regex Mismatch か API制限の可能性"
            print(f"  [HatenaEditor] {msg} — 末尾に警告コメント挿入して継続")
            errors.append(msg)
            # 本文末尾に「要手動挿入」コメントを追記して処理を続行
            table_html = f"<!-- [HatenaEditor] 比較表生成失敗: {query} — 要手動作成 -->"
            guide_html = ""

        new_body = _insert_sections(body_html, table_html, guide_html)

        if dry_run:
            sentinel_pos = new_body.find(SENTINEL)
            preview_text = new_body[sentinel_pos: sentinel_pos + 400] if sentinel_pos >= 0 else ""
            print(f"  [HatenaEditor] [dry-run] 挿入プレビュー:\n{preview_text}\n")
            results.append({"query": query, "entry_id": entry_id, "title": title, "status": "dry_run"})
            updated_count += 1
            continue

        # PUT で更新
        try:
            success = _update_entry(entry_id, title, new_body)
        except Exception as e:
            msg = f"PUT更新例外 ({title[:30]}): {type(e).__name__}: {e}"
            print(f"  [HatenaEditor] {msg}")
            errors.append(msg)
            results.append({"query": query, "entry_id": entry_id, "title": title,
                             "status": "error", "error": msg})
            continue

        if success:
            edit_log[entry_id] = {
                "title":               title,
                "query":               query,
                "tool_pair":           [tool_a, tool_b],
                "comparison_inserted": True,
                "inserted_at":         datetime.now().isoformat(),
                "position_at_insert":  position,
            }
            _save_edit_log(edit_log)
            print(f"  [HatenaEditor] 更新成功: {title[:40]}")
            updated_count += 1
            results.append({"query": query, "entry_id": entry_id, "title": title, "status": "updated"})
        else:
            msg = f"PUT失敗 ({title[:30]}): API認証・レート制限・記事フォーマット問題の可能性"
            errors.append(msg)
            results.append({"query": query, "entry_id": entry_id, "title": title,
                             "status": "failed", "error": msg})

        time.sleep(2)  # API レート制限回避

    print(f"\n[HatenaEditor] 完了 — 更新: {updated_count} / スキップ: {skipped_count} / エラー: {len(errors)}")

    final = {
        "status":        "ok" if not errors else "partial",
        "updated":       updated_count,
        "skipped":       skipped_count,
        "results":       results,
        "errors":        errors,
        "error_summary": "; ".join(errors[:3]) if errors else "",
    }
    _write_result(final)
    return final


if __name__ == "__main__":
    # .env 読み込み
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    mode   = sys.argv[1] if len(sys.argv) > 1 else "run"
    result = run(dry_run=(mode == "dry-run"))
    print(json.dumps(result, ensure_ascii=False, indent=2))
