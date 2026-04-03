"""
Google Indexing API 連携
記事公開後、Googleにインデックス登録をリクエストする

【セットアップ】
1. Google Cloud Console → APIとサービス → 「Indexing API」を有効化
2. サービスアカウントを作成 → JSONキーをダウンロード
3. Search Console → 設定 → ユーザーと権限 → サービスアカウントのメールを「オーナー」で追加
4. JSONキーの内容を GitHub Secrets の GOOGLE_INDEXING_CREDENTIALS に貼り付け

【環境変数】
- GOOGLE_INDEXING_CREDENTIALS : サービスアカウントJSONの文字列（必須）
- HATENA_BLOG_DOMAIN          : ブログドメイン（省略時: smart-earn-life.hateblo.jp）
"""
import os
import json
import time
from pathlib import Path
from datetime import datetime

HATENA_BLOG_DOMAIN = os.environ.get("HATENA_BLOG_DOMAIN", "smart-earn-life.hateblo.jp")
HATENA_SITEMAP_URL = f"https://{HATENA_BLOG_DOMAIN}/sitemap.xml"
INDEXING_ENDPOINT  = "https://indexing.googleapis.com/v3/urlNotifications:publish"
GOOGLE_PING_URL    = "https://www.google.com/ping"
LOG_FILE           = Path(__file__).parent / "indexing_log.json"
SITEMAP_FILE       = Path(__file__).parent / "sitemap.xml"


def _get_credentials():
    """サービスアカウントの認証情報を取得"""
    import google.auth
    from google.oauth2 import service_account

    cred_json = os.environ.get("GOOGLE_INDEXING_CREDENTIALS", "")
    if not cred_json:
        raise EnvironmentError(
            "GOOGLE_INDEXING_CREDENTIALS が未設定です。\n"
            "Google Cloud Console でサービスアカウントを作成し、\n"
            "JSONキーを GitHub Secrets に登録してください。"
        )
    cred_dict = json.loads(cred_json)
    credentials = service_account.Credentials.from_service_account_info(
        cred_dict,
        scopes=["https://www.googleapis.com/auth/indexing"],
    )
    return credentials


def notify_url(url: str, notification_type: str = "URL_UPDATED") -> dict:
    """
    Google Indexing API に URL を通知する

    Args:
        url: インデックス登録を依頼するURL
        notification_type: "URL_UPDATED"（新規/更新）or "URL_DELETED"（削除）

    Returns:
        {"success": bool, "url": str, "response": dict, "error": str}
    """
    try:
        import google.auth.transport.requests
        import requests as req

        credentials = _get_credentials()

        # アクセストークン取得
        auth_request = google.auth.transport.requests.Request()
        credentials.refresh(auth_request)
        token = credentials.token

        payload = {"url": url, "type": notification_type}
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        resp = req.post(INDEXING_ENDPOINT, json=payload, headers=headers, timeout=15)
        resp_data = resp.json() if resp.content else {}

        success = resp.status_code == 200
        result = {
            "success": success,
            "url": url,
            "status_code": resp.status_code,
            "response": resp_data,
            "notified_at": datetime.now().isoformat(),
        }
        _save_log(result)
        return result

    except EnvironmentError as e:
        return {"success": False, "url": url, "error": str(e)}
    except Exception as e:
        return {"success": False, "url": url, "error": str(e)}


def notify_article(article: dict, hatena_url: str = "") -> dict:
    """
    記事dictからURLを特定してインデックス通知

    Args:
        article: pending/のJSONデータ
        hatena_url: はてなブログの投稿URL（分かれば渡す）
    """
    # URLが直接渡されている場合
    if hatena_url:
        return notify_url(hatena_url)

    # ログから検索
    url = _find_url_from_log(article.get("keyword", ""), article.get("title", ""))
    if url:
        return notify_url(url)

    return {
        "success": False,
        "url": "",
        "error": "投稿URLが特定できません。hatena_post_log.jsonにURLが記録されていることを確認してください。",
    }


def _find_url_from_log(keyword: str, title: str) -> str:
    """はてな投稿ログからURLを検索"""
    log_file = Path(__file__).parent.parent / "hatena_automation" / "hatena_post_log.json"
    if not log_file.exists():
        return ""
    try:
        entries = json.loads(log_file.read_text(encoding="utf-8"))
        # 直近20件から keyword or title で一致を探す
        for entry in reversed(entries[-20:]):
            if entry.get("url") and (
                entry.get("keyword") == keyword or
                entry.get("title") == title
            ):
                return entry["url"]
    except Exception:
        pass
    return ""


def _save_log(result: dict):
    """インデックス通知ログを保存"""
    log = []
    if LOG_FILE.exists():
        try:
            log = json.loads(LOG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    log.append(result)
    LOG_FILE.write_text(json.dumps(log[-100:], ensure_ascii=False, indent=2), encoding="utf-8")


def notify_bulk(urls: list, interval_sec: float = 1.0) -> list:
    """
    複数URLを一括通知（レートリミット: 200件/日）

    Args:
        urls: URLのリスト
        interval_sec: 通知間隔（秒）
    """
    results = []
    for i, url in enumerate(urls):
        print(f"  [{i+1}/{len(urls)}] インデックス通知: {url[:60]}")
        result = notify_url(url)
        results.append(result)
        status = "OK" if result["success"] else f"NG: {result.get('error', '')[:50]}"
        print(f"    → {status}")
        if i < len(urls) - 1:
            time.sleep(interval_sec)
    return results


def ping_google_sitemap(sitemap_url: str = None) -> dict:
    """
    Google にサイトマップURLを通知する（Indexing APIとは独立した安全な手段）
    Googlebotが自然に巡回しやすくなる二段構えの対策

    はてなブログはサイトマップを自動生成するので、URLをpingするだけでOK
    """
    sitemap_url = sitemap_url or HATENA_SITEMAP_URL
    try:
        import requests as req
        resp = req.get(GOOGLE_PING_URL, params={"sitemap": sitemap_url}, timeout=10)
        success = resp.status_code == 200
        result = {
            "type": "sitemap_ping",
            "success": success,
            "sitemap_url": sitemap_url,
            "status_code": resp.status_code,
            "notified_at": datetime.now().isoformat(),
        }
        _save_log(result)
        status = "OK" if success else f"NG({resp.status_code})"
        print(f"  🗺️ [Indexing] Sitemapping: {status} → {sitemap_url}")
        return result
    except Exception as e:
        return {"type": "sitemap_ping", "success": False, "error": str(e)}


def generate_local_sitemap(post_log_path: str = None) -> str:
    """
    投稿ログからsitemap.xmlを生成してローカルに保存する
    （はてなの自動サイトマップで十分だが、バックアップ・確認用として）

    Returns: 生成したXMLの文字列
    """
    log_path = Path(post_log_path) if post_log_path else (
        Path(__file__).parent.parent / "hatena_automation" / "hatena_post_log.json"
    )

    entries = []
    if log_path.exists():
        try:
            entries = json.loads(log_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    urls = [e["url"] for e in entries if e.get("url") and e["url"].startswith("http")]

    # ブログトップを追加
    urls = [f"https://{HATENA_BLOG_DOMAIN}/"] + urls

    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    for url in urls:
        lines.append("  <url>")
        lines.append(f"    <loc>{url}</loc>")
        lines.append(f"    <changefreq>weekly</changefreq>")
        lines.append("  </url>")
    lines.append("</urlset>")

    xml = "\n".join(lines)
    SITEMAP_FILE.write_text(xml, encoding="utf-8")
    print(f"  🗺️ [Indexing] sitemap.xml生成: {len(urls)}件のURL → {SITEMAP_FILE}")
    return xml


def run(state: dict = None) -> dict:
    """
    CEOエージェントから呼び出されるエントリポイント
    直近の投稿ログからURLを取得してインデックス通知
    """
    print("  📡 [GoogleIndexing] インデックス通知中...")

    log_file = Path(__file__).parent.parent / "hatena_automation" / "hatena_post_log.json"
    if not log_file.exists():
        print("  ⚠️ [GoogleIndexing] 投稿ログなし。スキップ。")
        return {"notified": 0}

    try:
        entries = json.loads(log_file.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  ❌ [GoogleIndexing] ログ読み込み失敗: {e}")
        return {"notified": 0}

    # URL未通知かつURLがある記事を対象に（直近5件）
    existing_log = []
    if LOG_FILE.exists():
        try:
            existing_log = json.loads(LOG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    notified_urls = {e.get("url") for e in existing_log if e.get("success")}

    targets = [
        e["url"] for e in entries[-10:]
        if e.get("url") and e["url"] not in notified_urls
    ]

    if not targets:
        print("  ℹ️ [GoogleIndexing] 通知対象URLなし（未投稿 or 既通知）")
        return {"notified": 0}

    results = notify_bulk(targets)
    ok = sum(1 for r in results if r["success"])
    print(f"  ✅ [GoogleIndexing] 完了: {ok}/{len(targets)}件 通知成功")

    # 二段構え: Indexing API と並行してサイトマップPingも実行
    ping_result = ping_google_sitemap()

    return {
        "notified": ok,
        "total": len(targets),
        "results": results,
        "sitemap_ping": ping_result.get("success", False),
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        # 直接URL指定
        url = sys.argv[1]
        print(f"インデックス通知: {url}")
        result = notify_url(url)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        # ログから自動実行
        result = run()
        print(json.dumps(result, ensure_ascii=False, indent=2))
