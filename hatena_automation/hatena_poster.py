"""
はてなブログ 自動投稿スクリプト（AtomPub API版）

Cookie失効リスクを排除するため、AtomPub API + Basic認証に移行。
Playwright / Cookie 依存なし。

【環境変数】
  HATENA_ID       — はてなID（例: pi-natu-butter）
  HATENA_BLOG_ID  — ブログID（例: smart-earn-life.hateblo.jp）
  HATENA_API_KEY  — AtomPub APIキー
                    取得先: https://blog.hatena.ne.jp/{HATENA_ID}/{BLOG_ID}/config/api

【使い方】
  python3 hatena_automation/hatena_poster.py preview [keyword]
  python3 hatena_automation/hatena_poster.py post    [keyword]
  python3 hatena_automation/hatena_poster.py test    [keyword]  # ドライラン（投稿しない）
  python3 hatena_automation/hatena_poster.py log
"""

import os
import sys
import re
import base64
import requests
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hatena_article_generator import generate_article, preview_article

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))
from db_client import db
from utils.decorators import api_retry

DRAFTS_DIR = Path(__file__).parent / "drafts"

# ─────────────────────────────────────────
# 環境変数
# ─────────────────────────────────────────
def load_env():
    env_path = ROOT_DIR / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


def _get_credentials() -> tuple[str, str, str]:
    """HATENA_ID / HATENA_BLOG_ID / HATENA_API_KEY を返す"""
    hatena_id   = os.environ.get("HATENA_ID", "")
    blog_id     = os.environ.get("HATENA_BLOG_ID", "")
    api_key     = os.environ.get("HATENA_API_KEY", "")
    return hatena_id, blog_id, api_key


# ─────────────────────────────────────────
# Markdown → HTML変換
# ─────────────────────────────────────────
def markdown_to_html(body_md: str) -> str:
    """Markdown → はてなブログ向け HTML に変換"""
    body_html = body_md
    body_html = re.sub(r"^## (.+)$",  r"<h2>\1</h2>",  body_html, flags=re.MULTILINE)
    body_html = re.sub(r"^### (.+)$", r"<h3>\1</h3>",  body_html, flags=re.MULTILINE)
    body_html = re.sub(r"^#### (.+)$",r"<h4>\1</h4>",  body_html, flags=re.MULTILINE)
    body_html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", body_html)
    body_html = re.sub(r"\*(.+?)\*",     r"<em>\1</em>",         body_html)

    # Markdownテーブル → HTMLテーブル
    lines   = body_html.split("\n")
    result  = []
    in_table = False
    table_rows: list[list[str]] = []

    for line in lines:
        if "|" in line and line.strip().startswith("|"):
            if not in_table:
                in_table = True
                table_rows = []
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            table_rows.append(cells)
        else:
            if in_table:
                result.append(_table_to_html(table_rows))
                in_table = False
                table_rows = []
            result.append(line)

    if in_table:
        result.append(_table_to_html(table_rows))

    body_html = "\n".join(result)

    # 段落変換（見出し・テーブル・HTML要素以外を <p> で囲む）
    paragraphs = body_html.split("\n\n")
    converted  = []
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        if p.startswith(("<h", "<table", "<ul", "<ol", "<pre", "<blockquote")):
            converted.append(p)
        else:
            converted.append(f"<p>{p}</p>")

    return "\n".join(converted)


def _table_to_html(rows: list[list[str]]) -> str:
    sep_pat = re.compile(r"^[-:]+$")
    html = "<table border='1' style='border-collapse:collapse;width:100%;margin:1em 0'>\n"
    header_done = False
    for row in rows:
        if all(sep_pat.match(c.strip()) for c in row if c.strip()):
            continue
        tag   = "th" if not header_done else "td"
        style = " style='padding:6px 12px;background:#f5f5f5'" if tag == "th" else " style='padding:6px 12px;'"
        html += "<tr>" + "".join(f"<{tag}{style}>{c}</{tag}>" for c in row) + "</tr>\n"
        header_done = True
    return html + "</table>"


# ─────────────────────────────────────────
# 下書きフォールバック
# ─────────────────────────────────────────
def _save_as_draft(article: dict) -> str:
    """APIキーなし or 投稿失敗時: Markdownファイルとして保存してパスを返す"""
    DRAFTS_DIR.mkdir(exist_ok=True)
    ts         = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = re.sub(r'[^\w\u3040-\u9fff]', '_', article.get("title", "draft"))[:30]
    filepath   = DRAFTS_DIR / f"{ts}_{safe_title}.md"
    content    = (
        f"---\ntitle: {article.get('title', '')}\n"
        f"keyword: {article.get('keyword', '')}\n"
        f"category: {article.get('category', '')}\n"
        f"tags: {article.get('tags', [])}\n---\n\n"
        f"{article.get('body', '')}\n"
    )
    filepath.write_text(content, encoding="utf-8")
    return str(filepath)


# ─────────────────────────────────────────
# AtomPub API 投稿
# ─────────────────────────────────────────
def post_article(
    title: str,
    body: str,
    category: str = "",
    headless: bool = True,  # 後方互換のために残す（使わない）
    draft: bool = False,
    tags: list[str] | None = None,
) -> str:
    """
    はてなブログAtomPub APIで記事を投稿してURLを返す。
    認証失敗・ネットワークエラー時はローカルに下書き保存して 'file://...' を返す。
    """
    hatena_id, blog_id, api_key = _get_credentials()

    if not hatena_id or not blog_id:
        print("[Hatena] HATENA_ID / HATENA_BLOG_ID 未設定 → ローカルに下書き保存")
        path = _save_as_draft({"title": title, "body": body, "category": category, "tags": tags or []})
        return f"file://{path}"

    if not api_key:
        print("[Hatena] HATENA_API_KEY 未設定 → ローカルに下書き保存")
        path = _save_as_draft({"title": title, "body": body, "category": category, "tags": tags or []})
        return f"file://{path}"

    body_html       = markdown_to_html(body)
    all_tags        = [category] + (tags or []) if category else (tags or [])
    categories_xml  = "\n    ".join(f'<category term="{t}" />' for t in all_tags)
    draft_xml       = "<app:draft>yes</app:draft>" if draft else "<app:draft>no</app:draft>"

    atom_xml = f"""<?xml version="1.0" encoding="utf-8"?>
<entry xmlns="http://www.w3.org/2005/Atom"
       xmlns:app="http://www.w3.org/2007/app">
  <title>{title}</title>
  <author><name>{hatena_id}</name></author>
  <content type="text/html">{body_html}</content>
  {categories_xml}
  <app:control>
    {draft_xml}
  </app:control>
</entry>"""

    endpoint = f"https://blog.hatena.ne.jp/{hatena_id}/{blog_id}/atom/entry"
    auth     = base64.b64encode(f"{hatena_id}:{api_key}".encode()).decode()
    headers  = {
        "Content-Type":  "application/atom+xml; charset=utf-8",
        "Authorization": f"Basic {auth}",
    }

    @api_retry("hatena", context=f"hatena投稿: {title[:40]}")
    def _do_post() -> requests.Response:
        return requests.post(endpoint, data=atom_xml.encode("utf-8"), headers=headers, timeout=30)

    resp = _do_post()
    if resp is None:
        print(f"[Hatena] 全リトライ消耗 → 投稿スキップ: {title[:50]}")
        return ""

    return _handle_response(resp, title, hatena_id, blog_id,
                            {"title": title, "body": body, "category": category, "tags": tags or []})


def _handle_response(resp: requests.Response, title: str, hatena_id: str, blog_id: str, article: dict) -> str:
    """
    AtomPub レスポンスをステータスコード別にハンドリングし、URL を返す。
    失敗時は空文字列を返す（呼び出し元が db.insert_post で記録する）。
    """
    status = resp.status_code

    if status in (200, 201):
        match = re.search(r'<link[^>]*rel="alternate"[^>]*href="([^"]+)"', resp.text)
        url   = match.group(1) if match else ""
        print(f"[Hatena] 投稿成功: {title[:50]}")
        if url:
            print(f"[Hatena] URL: {url}")
        return url

    elif status == 400:
        msg = f"HTTP 400 Bad Request: {resp.text[:300]}"
        print(f"[Hatena] リクエスト不正 — {msg}")
        return ""

    elif status == 401:
        msg = (
            f"HTTP 401 Unauthorized: APIキー認証失敗。"
            f"https://blog.hatena.ne.jp/{hatena_id}/{blog_id}/config/api で確認してください"
        )
        print(f"[Hatena] {msg}")
        return ""

    elif status == 403:
        msg = f"HTTP 403 Forbidden: アクセス権なし — {resp.text[:200]}"
        print(f"[Hatena] {msg}")
        return ""

    elif status == 429:
        msg = f"HTTP 429 Too Many Requests: レートリミット超過"
        print(f"[Hatena] {msg}")
        return ""

    elif 500 <= status < 600:
        msg = f"HTTP {status} Server Error: {resp.text[:200]}"
        print(f"[Hatena] サーバーエラー — {msg}")
        return ""

    else:
        msg = f"HTTP {status}: {resp.text[:200]}"
        print(f"[Hatena] 予期しないレスポンス — {msg}")
        return ""


# ─────────────────────────────────────────
# DBログ
# ─────────────────────────────────────────
def save_log(article: dict, success: bool, url: str = "", error_message: str = ""):
    """投稿結果を DB に記録する"""
    try:
        db.insert_post(
            platform="hatena",
            post_type=article.get("category", ""),
            label=article.get("keyword", ""),
            chars=article.get("chars", len(article.get("body", ""))),
            text=article.get("title", "")[:500],
            success=success,
            url=url,
            error_message=error_message,
        )
    except Exception as e:
        print(f"[Hatena] DBログ書き込み失敗: {e}")


def show_log(n: int = 10):
    """DBから投稿ログを取得して表示"""
    try:
        entries = db.get_posts(platform="hatena", limit=n)
    except Exception as e:
        print(f"[Hatena] DBログ読み込み失敗: {e}")
        return
    print(f"\n はてなブログ投稿ログ（直近{n}件）")
    print("─" * 55)
    for entry in entries:
        dt_str = entry.get("datetime") or entry.get("created_at", "")
        try:
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00")).replace(tzinfo=None)
            dt_fmt = dt.strftime("%m/%d %H:%M")
        except Exception:
            dt_fmt = dt_str[:16]
        st = "OK" if entry.get("success") else "NG"
        print(f"[{st}] {dt_fmt} [{entry.get('post_type','')}] {str(entry.get('text',''))[:35]}")
        if entry.get("url"):
            print(f"   -> {entry['url']}")
        if not entry.get("success") and entry.get("error_message"):
            print(f"   ERROR: {str(entry['error_message'])[:80]}")


# ─────────────────────────────────────────
# メイン
# ─────────────────────────────────────────
if __name__ == "__main__":
    load_env()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "preview"

    if cmd == "preview":
        kw      = sys.argv[2] if len(sys.argv) > 2 else None
        article = generate_article(force_keyword=kw)
        preview_article(article)
        DRAFTS_DIR.mkdir(exist_ok=True)
        ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = DRAFTS_DIR / f"hatena_{ts}.md"
        fname.write_text(f"# {article['title']}\n\n**キーワード**: {article['keyword']}\n\n{article['body']}", encoding="utf-8")
        print(f"\n 下書き保存: {fname}")

    elif cmd == "test":
        kw      = sys.argv[2] if len(sys.argv) > 2 else None
        article = generate_article(force_keyword=kw)
        print(f"\n[DRY RUN] はてなブログ投稿予定")
        print(f"{'─'*50}")
        print(f"タイトル : {article['title']}")
        print(f"キーワード: {article['keyword']}")
        print(f"文字数   : {article['chars']}文字")
        print(f"{'─'*50}")
        save_log(article, success=True, url="", error_message="dry_run")

    elif cmd == "post":
        kw      = sys.argv[2] if len(sys.argv) > 2 else None
        article = generate_article(force_keyword=kw)
        preview_article(article)
        print("\n はてなブログに投稿します...")
        url = post_article(
            title=article["title"],
            body=article["body"],
            category=article.get("category", ""),
            tags=article.get("tags", []),
        )
        success = bool(url and not url.startswith("file://"))
        error   = "" if success else "投稿失敗（レスポンスエラーまたはAPIキー未設定）"
        save_log(article, success=success, url=url, error_message=error)
        if success:
            print(f"投稿完了: {url}")
        else:
            print("投稿失敗")

    elif cmd == "log":
        show_log()

    else:
        print("使い方:")
        print("  python hatena_poster.py preview [kw]   # 記事プレビュー・下書き保存")
        print("  python hatena_poster.py test [kw]      # ドライラン（投稿なし）")
        print("  python hatena_poster.py post [kw]      # AtomPub API で投稿")
        print("  python hatena_poster.py log            # 投稿ログ（DB）")
