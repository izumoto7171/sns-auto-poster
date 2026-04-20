"""
note.com 自動投稿スクリプト（API版）

Cookie失効リスクを排除するため、note.com 内部 API + メール/パスワード認証に移行。
Playwright / Cookie 依存なし。

【環境変数】
  NOTE_EMAIL    — note.com ログイン用メールアドレス
  NOTE_PASSWORD — note.com ログインパスワード

【使い方】
  python3 note_automation/note_poster.py preview
  python3 note_automation/note_poster.py post
  python3 note_automation/note_poster.py test   # ドライラン（投稿しない）
  python3 note_automation/note_poster.py log

【note.com API について】
  非公式内部APIを使用（https://note.com/api/v1/sessions, /api/v2/text_notes）。
  APIが変更された場合はローカルに下書き保存してエラーログをDBに記録します。
"""

import os
import sys
import re
import json
import requests
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from note_article_generator import generate_article, preview_article

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))
from db_client import db
from utils.decorators import api_retry

DRAFTS_DIR = Path(__file__).parent / "drafts"

NOTE_API_BASE = "https://note.com"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


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


def _get_credentials() -> tuple[str, str]:
    """NOTE_EMAIL / NOTE_PASSWORD を返す"""
    return (
        os.environ.get("NOTE_EMAIL", ""),
        os.environ.get("NOTE_PASSWORD", ""),
    )


# ─────────────────────────────────────────
# note.com API 認証
# ─────────────────────────────────────────
def _authenticate() -> requests.Session:
    """
    note.com にメール+パスワードでログインしてセッションを返す。
    失敗時は RuntimeError を送出する。
    """
    email, password = _get_credentials()
    if not email or not password:
        raise RuntimeError(
            "NOTE_EMAIL / NOTE_PASSWORD が未設定です。"
            "GitHub Secrets または .env に追加してください。"
        )

    session = requests.Session()
    session.headers.update({
        "User-Agent":      _UA,
        "Accept":          "application/json, text/plain, */*",
        "Accept-Language": "ja,en;q=0.9",
        "Referer":         "https://note.com/login",
        "Origin":          "https://note.com",
    })

    # CSRF トークンを取得（ログインページ経由）
    try:
        init_resp = session.get(f"{NOTE_API_BASE}/login", timeout=15)
        csrf_match = re.search(r'<meta[^>]+name=["\']csrf-token["\'][^>]+content=["\']([^"\']+)["\']', init_resp.text)
        if csrf_match:
            session.headers["X-CSRF-Token"] = csrf_match.group(1)
    except Exception:
        pass  # CSRFトークン取得失敗は無視して続行

    # ログイン
    login_resp = session.post(
        f"{NOTE_API_BASE}/api/v1/sessions",
        json={"login": email, "password": password},
        headers={"Content-Type": "application/json"},
        timeout=20,
    )

    if login_resp.status_code not in (200, 201):
        raise RuntimeError(
            f"note.com ログイン失敗 HTTP {login_resp.status_code}: "
            f"{login_resp.text[:200]}"
        )

    data = login_resp.json()
    # レスポンスに user_session_token がある場合はヘッダーにもセット
    token = (
        data.get("data", {}).get("user_session_token")
        or data.get("user_session_token")
        or ""
    )
    if token:
        session.headers["X-Note-Token"] = token

    print("[note] ログイン成功")
    return session


# ─────────────────────────────────────────
# 下書きフォールバック
# ─────────────────────────────────────────
def _save_as_draft(article: dict) -> str:
    DRAFTS_DIR.mkdir(exist_ok=True)
    ts         = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = re.sub(r'[^\w\u3040-\u9fff]', '_', article.get("title", "draft"))[:30]
    filepath   = DRAFTS_DIR / f"{ts}_{safe_title}.md"
    content    = f"# {article.get('title', '')}\n\n{article.get('body', '')}\n"
    filepath.write_text(content, encoding="utf-8")
    return str(filepath)


# ─────────────────────────────────────────
# note 投稿
# ─────────────────────────────────────────
def post_article(
    title: str,
    body: str,
    headless: bool = True,  # 後方互換のために残す（使わない）
    tags: list[str] | None = None,
) -> str:
    """
    note.com に記事を投稿してURLを返す。
    ログイン失敗・投稿失敗時は空文字列を返す。
    """
    try:
        session = _authenticate()
    except RuntimeError as e:
        print(f"[note] 認証失敗: {e}")
        return ""

    # HTML変換（note は HTML を受け付ける）
    body_html = _markdown_to_html(body)

    payload = {
        "name":   title,
        "body":   body_html,
        "status": "published",
        "tags":   tags or [],
        "price":  0,
    }

    @api_retry("note", context=f"note投稿: {title[:40]}")
    def _do_post() -> requests.Response:
        return session.post(
            f"{NOTE_API_BASE}/api/v2/text_notes",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )

    resp = _do_post()
    if resp is None:
        print(f"[note] 全リトライ消耗 → 投稿スキップ: {title[:50]}")
        return ""

    return _handle_response(resp, title)


def _handle_response(resp: requests.Response, title: str) -> str:
    """note.com API レスポンスをステータスコード別にハンドリング"""
    status = resp.status_code

    if status in (200, 201):
        try:
            data      = resp.json().get("data", {})
            note_key  = data.get("key", "")
            urlname   = data.get("user", {}).get("urlname", "")
            url       = f"https://note.com/{urlname}/n/{note_key}" if note_key and urlname else ""
            print(f"[note] 投稿成功: {title[:50]}")
            if url:
                print(f"[note] URL: {url}")
            return url
        except Exception as e:
            print(f"[note] レスポンス解析エラー: {e}")
            return ""

    elif status == 400:
        print(f"[note] リクエスト不正 HTTP 400: {resp.text[:300]}")
        return ""

    elif status == 401:
        print(f"[note] 認証エラー HTTP 401: セッション切れ or 認証情報不正")
        return ""

    elif status == 403:
        print(f"[note] アクセス拒否 HTTP 403: {resp.text[:200]}")
        return ""

    elif status == 422:
        # バリデーションエラー（タイトル・本文の制約違反など）
        try:
            errors = resp.json().get("errors", resp.text[:200])
        except Exception:
            errors = resp.text[:200]
        print(f"[note] バリデーションエラー HTTP 422: {errors}")
        return ""

    elif status == 429:
        print(f"[note] レートリミット HTTP 429: しばらく待って再試行してください")
        return ""

    elif 500 <= status < 600:
        print(f"[note] サーバーエラー HTTP {status}: {resp.text[:200]}")
        return ""

    else:
        print(f"[note] 予期しないレスポンス HTTP {status}: {resp.text[:200]}")
        return ""


# ─────────────────────────────────────────
# Markdown → HTML変換
# ─────────────────────────────────────────
def _markdown_to_html(md: str) -> str:
    """Markdown を note.com 向け HTML に変換"""
    html = md
    html = re.sub(r"^## (.+)$",   r"<h2>\1</h2>",  html, flags=re.MULTILINE)
    html = re.sub(r"^### (.+)$",  r"<h3>\1</h3>",  html, flags=re.MULTILINE)
    html = re.sub(r"^#### (.+)$", r"<h4>\1</h4>",  html, flags=re.MULTILINE)
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"\*(.+?)\*",     r"<em>\1</em>",         html)
    html = re.sub(r"^- (.+)$",      r"<li>\1</li>",         html, flags=re.MULTILINE)

    paragraphs = html.split("\n\n")
    converted  = []
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        if p.startswith(("<h", "<ul", "<ol", "<li", "<table", "<blockquote")):
            converted.append(p)
        else:
            converted.append(f"<p>{p}</p>")
    return "\n".join(converted)


# ─────────────────────────────────────────
# DBログ
# ─────────────────────────────────────────
def save_log(article: dict, success: bool, url: str = "", error_message: str = ""):
    """投稿結果を DB に記録する"""
    try:
        db.insert_post(
            platform="note",
            post_type=article.get("label", article.get("category", "")),
            label=article.get("label", ""),
            chars=article.get("chars", len(article.get("body", ""))),
            text=article.get("title", "")[:500],
            success=success,
            url=url,
            error_message=error_message,
        )
    except Exception as e:
        print(f"[note] DBログ書き込み失敗: {e}")


def show_log(n: int = 10):
    """DBから投稿ログを取得して表示"""
    try:
        entries = db.get_posts(platform="note", limit=n)
    except Exception as e:
        print(f"[note] DBログ読み込み失敗: {e}")
        return
    print(f"\n note投稿ログ（直近{n}件）")
    print("─" * 50)
    for entry in entries:
        dt_str = entry.get("datetime") or entry.get("created_at", "")
        try:
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00")).replace(tzinfo=None)
            dt_fmt = dt.strftime("%m/%d %H:%M")
        except Exception:
            dt_fmt = dt_str[:16]
        st = "OK" if entry.get("success") else "NG"
        print(f"[{st}] {dt_fmt} [{entry.get('post_type','')}] {str(entry.get('text',''))[:25]}")
        if not entry.get("success") and entry.get("error_message"):
            print(f"   ERROR: {str(entry['error_message'])[:80]}")


# ─────────────────────────────────────────
# メイン
# ─────────────────────────────────────────
if __name__ == "__main__":
    load_env()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "preview"

    if cmd == "preview":
        article = generate_article()
        preview_article(article)
        DRAFTS_DIR.mkdir(exist_ok=True)
        ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = DRAFTS_DIR / f"article_{ts}.md"
        out_path.write_text(f"# {article['title']}\n\n{article['body']}", encoding="utf-8")
        print(f"\n 下書き保存: {out_path}")

    elif cmd == "test":
        article = generate_article()
        preview_article(article)
        print("\n[DRY RUN] note に投稿予定（実際には投稿しません）")
        print(f"  タイトル: {article['title']}")
        print(f"  文字数  : {article['chars']}文字")
        save_log(article, success=True, url="", error_message="dry_run")

    elif cmd == "post":
        article = generate_article()
        preview_article(article)
        print("\n note に投稿します...")
        url     = post_article(article["title"], article["body"])
        success = bool(url)
        error   = "" if success else "投稿失敗（APIエラーまたは認証失敗）"
        save_log(article, success=success, url=url, error_message=error)
        if success:
            print(f"投稿完了: {url}")
        else:
            path = _save_as_draft(article)
            print(f"投稿失敗 → ローカル下書き保存: {path}")

    elif cmd == "log":
        show_log()

    else:
        print("使い方:")
        print("  python note_poster.py preview   # 記事プレビュー・下書き保存")
        print("  python note_poster.py test       # ドライラン（投稿なし）")
        print("  python note_poster.py post       # note.com API で投稿")
        print("  python note_poster.py log        # 投稿ログ（DB）")
