"""
はてなブログ AtomPub API 投稿モジュール

【はてなAPIキーの取得方法】
  1. https://blog.hatena.ne.jp/[HATENA_ID]/[BLOG_ID]/config/api にアクセス
  2. 「APIキー」を確認してコピー
  3. .env の HATENA_API_KEY= に設定（または GitHub Secrets に登録）

【APIキーが設定されていない場合】
  money_agent/hatena_drafts/ フォルダにMarkdownファイルとして保存される。
  手動でコピペして投稿することができる。
"""

import os
import re
import sys
import base64
import requests
from datetime import datetime
from pathlib import Path

HATENA_ID      = os.environ.get("HATENA_ID", "")
HATENA_BLOG_ID = os.environ.get("HATENA_BLOG_ID", "")
HATENA_API_KEY = os.environ.get("HATENA_API_KEY", "")
DRAFTS_DIR     = Path(__file__).parent / "hatena_drafts"

# Supabase クライアント（DBログ用）
sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    from db_client import db as _db
    _DB_AVAILABLE = True
except Exception:
    _DB_AVAILABLE = False


def _log_to_db(article: dict, success: bool, url: str = "", error_message: str = ""):
    """投稿結果を DB に記録する（失敗しても例外は抑制）"""
    if not _DB_AVAILABLE:
        return
    try:
        _db.insert_post(
            platform="hatena",
            post_type=article.get("category", ""),
            label=article.get("keyword", article.get("program_name", "")),
            chars=len(article.get("body", "")),
            text=article.get("title", "")[:500],
            success=success,
            url=url,
            error_message=error_message,
        )
    except Exception as e:
        print(f"[Hatena] DBログ書き込み失敗: {e}")


def markdown_to_html(body_md: str) -> str:
    """Markdown → HTML（Hatenaブログ向け）"""
    body_html = body_md
    body_html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", body_html, flags=re.MULTILINE)
    body_html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", body_html, flags=re.MULTILINE)
    body_html = re.sub(r"^#### (.+)$", r"<h4>\1</h4>", body_html, flags=re.MULTILINE)
    body_html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", body_html)
    body_html = re.sub(r"\*(.+?)\*", r"<em>\1</em>", body_html)

    # Markdownテーブル → HTMLテーブル
    lines = body_html.split("\n")
    result = []
    in_table = False
    table_rows = []

    for line in lines:
        if "|" in line and line.strip().startswith("|"):
            if not in_table:
                in_table = True
                table_rows = []
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            table_rows.append(cells)
        else:
            if in_table:
                html = "<table border='1' style='border-collapse:collapse;width:100%;margin:1em 0'>\n"
                for i, row in enumerate(table_rows):
                    # セパレーター行をスキップ
                    if all(re.match(r"^[-:]+$", c.strip()) for c in row if c.strip()):
                        continue
                    tag = "th" if i == 0 else "td"
                    style = " style='padding:6px 12px;'" if tag == "td" else " style='padding:6px 12px;background:#f5f5f5'"
                    html += "<tr>" + "".join(f"<{tag}{style}>{c}</{tag}>" for c in row) + "</tr>\n"
                html += "</table>"
                result.append(html)
                in_table = False
                table_rows = []
            result.append(line)

    if in_table:
        html = "<table border='1' style='border-collapse:collapse;width:100%;margin:1em 0'>\n"
        for i, row in enumerate(table_rows):
            if all(re.match(r"^[-:]+$", c.strip()) for c in row if c.strip()):
                continue
            tag = "th" if i == 0 else "td"
            style = " style='padding:6px 12px;'" if tag == "td" else " style='padding:6px 12px;background:#f5f5f5'"
            html += "<tr>" + "".join(f"<{tag}{style}>{c}</{tag}>" for c in row) + "</tr>\n"
        html += "</table>"
        result.append(html)

    body_html = "\n".join(result)

    # 段落変換（見出し・テーブル以外）
    paragraphs = body_html.split("\n\n")
    converted = []
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        if p.startswith(("<h", "<table", "<ul", "<ol", "<pre", "<blockquote")):
            converted.append(p)
        else:
            converted.append(f"<p>{p}</p>")

    return "\n".join(converted)


def save_as_draft(article: dict) -> str:
    """APIキーがない場合のフォールバック: Markdownファイルとして保存"""
    DRAFTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = re.sub(r'[^\w\u3040-\u9fff]', '_', article.get("title", "draft"))[:30]
    filename = f"{timestamp}_{safe_title}.md"
    filepath = DRAFTS_DIR / filename

    content = f"""---
title: {article.get("title", "")}
keyword: {article.get("keyword", "")}
category: {article.get("category", "")}
tags: {article.get("tags", [])}
generated_at: {article.get("generated_at", "")}
---

{article.get("body", "")}
"""
    filepath.write_text(content, encoding="utf-8")
    return str(filepath)


def post(article: dict, draft: bool = False) -> str:
    """
    はてなブログに AtomPub API で記事を投稿してURLを返す。
    APIキー未設定 / 認証失敗時はローカルに Markdown として保存してそのパスを返す。
    投稿結果（成否・エラー）は DB にも記録する。
    """
    title     = article.get("title", "無題")
    tags      = article.get("tags", [])
    category  = article.get("category", "副業")
    body_html = markdown_to_html(article.get("body", ""))

    # category は呼び出し元によって str / list の両方が渡ってくるため正規化する
    categories = (category if isinstance(category, list) else [category]) + list(tags)
    categories = [str(c) for c in categories if c]

    if not HATENA_ID or not HATENA_BLOG_ID:
        msg = "HATENA_ID / HATENA_BLOG_ID 未設定"
        print(f"[Hatena] {msg} → ローカルに下書き保存")
        path = save_as_draft(article)
        _log_to_db(article, success=False, error_message=msg)
        return f"file://{path}"

    if not HATENA_API_KEY:
        msg = "HATENA_API_KEY未設定"
        print(f"[Hatena] {msg} → ローカルに下書き保存")
        path = save_as_draft(article)
        print(f"[Hatena] 下書き保存: {path}")
        _log_to_db(article, success=False, error_message=msg)
        return f"file://{path}"

    # XML特殊文字のエスケープ必須。エスケープしないと本文中のアフィリエイトURLに
    # 含まれる & などで「400 XML Parse Failed」になる（楽天URLで顕在化）
    from xml.sax.saxutils import escape, quoteattr

    categories_xml = "\n    ".join(f'<category term={quoteattr(t)} />' for t in categories)
    draft_xml      = "<app:draft>yes</app:draft>" if draft else "<app:draft>no</app:draft>"

    atom_xml = f"""<?xml version="1.0" encoding="utf-8"?>
<entry xmlns="http://www.w3.org/2005/Atom"
       xmlns:app="http://www.w3.org/2007/app">
  <title>{escape(title)}</title>
  <author><name>{HATENA_ID}</name></author>
  <content type="text/html">{escape(body_html)}</content>
  {categories_xml}
  <app:control>
    {draft_xml}
  </app:control>
</entry>"""

    endpoint = f"https://blog.hatena.ne.jp/{HATENA_ID}/{HATENA_BLOG_ID}/atom/entry"
    auth     = base64.b64encode(f"{HATENA_ID}:{HATENA_API_KEY}".encode()).decode()

    try:
        resp = requests.post(
            endpoint,
            data=atom_xml.encode("utf-8"),
            headers={
                "Content-Type":  "application/atom+xml; charset=utf-8",
                "Authorization": f"Basic {auth}",
            },
            timeout=30,
        )
    except requests.RequestException as e:
        error_msg = f"ネットワークエラー: {e}"
        print(f"[Hatena] {error_msg}")
        _log_to_db(article, success=False, error_message=error_msg)
        path = save_as_draft(article)
        return f"file://{path}"

    status = resp.status_code

    if status in (200, 201):
        match = re.search(r'<link[^>]*rel="alternate"[^>]*href="([^"]+)"', resp.text)
        url   = match.group(1) if match else ""
        print(f"[Hatena] 投稿成功: {title[:50]}")
        if url:
            print(f"[Hatena] URL: {url}")
        _log_to_db(article, success=True, url=url)
        return url

    elif status == 400:
        error_msg = f"HTTP 400 Bad Request: {resp.text[:200]}"
        print(f"[Hatena] リクエスト不正 — {error_msg}")
        _log_to_db(article, success=False, error_message=error_msg)
        path = save_as_draft(article)
        return f"file://{path}"

    elif status == 401:
        error_msg = (
            f"HTTP 401 Unauthorized: APIキー認証失敗。"
            f"https://blog.hatena.ne.jp/{HATENA_ID}/{HATENA_BLOG_ID}/config/api で確認してください"
        )
        print(f"[Hatena] {error_msg}")
        _log_to_db(article, success=False, error_message=error_msg)
        path = save_as_draft(article)
        print(f"[Hatena] 下書き保存: {path}")
        return f"file://{path}"

    elif status == 429:
        error_msg = "HTTP 429 Too Many Requests: レートリミット超過"
        print(f"[Hatena] {error_msg}")
        _log_to_db(article, success=False, error_message=error_msg)
        return ""

    elif 500 <= status < 600:
        error_msg = f"HTTP {status} Server Error: {resp.text[:200]}"
        print(f"[Hatena] サーバーエラー — {error_msg}")
        _log_to_db(article, success=False, error_message=error_msg)
        path = save_as_draft(article)
        return f"file://{path}"

    else:
        error_msg = f"HTTP {status}: {resp.text[:200]}"
        print(f"[Hatena] 予期しないレスポンス — {error_msg}")
        _log_to_db(article, success=False, error_message=error_msg)
        path = save_as_draft(article)
        return f"file://{path}"
