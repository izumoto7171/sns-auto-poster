"""
Discord Webhook 通知モジュール

「静かな失敗」（ワークフローが緑でも内部で発生したエラー）をリアルタイムで通知する。
DISCORD_WEBHOOK_URL が未設定の場合は何もしない（本番・ローカル両対応）。

使い方:
    from utils.notifier import notify

    notify("x_automation/x_poster.py", "全投稿手段が失敗", "tweepy / twikit / Playwright すべて失敗")
"""

import os
import json
from datetime import datetime


def notify(file_name: str, summary: str, detail: str = "") -> None:
    """
    Discord Webhook にエラー通知を送信する。

    Parameters
    ----------
    file_name : エラーが発生したファイル名（例: "x_automation/x_poster.py"）
    summary   : エラーの概要（1行で伝わる内容）
    detail    : 追加のエラー詳細（省略可）
    """
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not webhook_url:
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M JST")
    lines = [
        f"**[自動通知] 静かな失敗を検知**",
        f"```",
        f"ファイル : {file_name}",
        f"発生時刻 : {now}",
        f"概要     : {summary}",
    ]
    if detail:
        # 長すぎる場合は切り捨て（Discord の1メッセージ上限 2000 文字対策）
        detail_trimmed = detail[:400] + ("..." if len(detail) > 400 else "")
        lines.append(f"詳細     : {detail_trimmed}")
    lines.append("```")

    content = "\n".join(lines)

    try:
        import urllib.request
        data = json.dumps({"content": content}).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status not in (200, 204):
                print(f"[Discord通知] 送信失敗: status={resp.status}")
    except Exception as e:
        # 通知失敗でメイン処理を止めない
        print(f"[Discord通知] 送信エラー: {e}")


def _send_raw(content: str) -> None:
    """Discord Webhook にメッセージを直接送信する内部ヘルパー"""
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not webhook_url:
        return
    try:
        import urllib.request
        data = json.dumps({"content": content}).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status not in (200, 204):
                print(f"[Discord通知] 送信失敗: status={resp.status}")
    except Exception as e:
        print(f"[Discord通知] 送信エラー: {e}")


def notify_info(file_name: str, summary: str, detail: str = "") -> None:
    """
    Discord Webhook に情報通知（成功・修復など）を送信する。

    エラー通知ではなく「システムが自動で対処した」実績を報告するために使用する。

    Parameters
    ----------
    file_name : 通知元のファイル名（例: "x_automation/fetch_amazon_deals.py"）
    summary   : 通知の概要（1行）
    detail    : 追加の詳細情報（省略可）
    """
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not webhook_url:
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M JST")
    lines = [
        f"**[自動対処] システム自律動作の記録**",
        f"```",
        f"ファイル : {file_name}",
        f"発生時刻 : {now}",
        f"内容     : {summary}",
    ]
    if detail:
        detail_trimmed = detail[:400] + ("..." if len(detail) > 400 else "")
        lines.append(f"詳細     : {detail_trimmed}")
    lines.append("```")

    _send_raw("\n".join(lines))
