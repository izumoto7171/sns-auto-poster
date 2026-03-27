#!/usr/bin/env python3
"""
LINE Bot Webhook サーバー
- 新規登録ユーザーのウェルカムメッセージ送信
- ユーザー情報をSQLiteで管理
- ステップ配信スケジューラーと連携
"""

import os
import json
import sqlite3
from datetime import datetime
from flask import Flask, request, abort

# LINE SDK v3
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    ReplyMessageRequest, PushMessageRequest,
    TextMessage as TextMsg
)
from linebot.v3.webhooks import (
    MessageEvent, TextMessageContent,
    FollowEvent, UnfollowEvent
)

# ローカルモジュール
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from line_automation.line_message_generator import generate_welcome_message, STEP_TEMPLATES

app = Flask(__name__)

# 環境変数
def load_env():
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

load_env()

CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")

if CHANNEL_ACCESS_TOKEN and CHANNEL_SECRET:
    configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
    handler = WebhookHandler(CHANNEL_SECRET)
else:
    configuration = None
    handler = None

def get_messaging_api():
    if configuration:
        return MessagingApi(ApiClient(configuration))
    return None

# ============================
# SQLite DB管理
# ============================

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "line_users.db")

def init_db():
    """DBを初期化"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            registered_at TEXT,
            current_step INTEGER DEFAULT 1,
            last_sent_at TEXT,
            is_active INTEGER DEFAULT 1
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS message_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            step INTEGER,
            sent_at TEXT,
            success INTEGER DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()
    print("✅ DB初期化完了")

def register_user(user_id):
    """新規ユーザーを登録"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute("""
        INSERT OR REPLACE INTO users (user_id, registered_at, current_step, last_sent_at, is_active)
        VALUES (?, ?, 1, ?, 1)
    """, (user_id, now, now))
    conn.commit()
    conn.close()

def unregister_user(user_id):
    """ユーザーをブロック（非アクティブに）"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET is_active = 0 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_user(user_id):
    """ユーザー情報を取得"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "user_id": row[0],
            "registered_at": row[1],
            "current_step": row[2],
            "last_sent_at": row[3],
            "is_active": row[4]
        }
    return None

def get_users_for_today():
    """今日ステップメッセージを送るユーザーを取得"""
    from datetime import date, timedelta
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id, registered_at, current_step FROM users WHERE is_active = 1 AND current_step <= 5")
    rows = c.fetchall()
    conn.close()

    today = date.today()
    targets = []
    for user_id, registered_at, current_step in rows:
        reg_date = datetime.fromisoformat(registered_at).date()
        days_since = (today - reg_date).days
        # 登録日から current_step 日目にメッセージを送る
        if days_since == current_step:
            targets.append({
                "user_id": user_id,
                "step": current_step
            })
    return targets

def mark_step_sent(user_id, step):
    """ステップ送信済みを記録"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute("UPDATE users SET current_step = ?, last_sent_at = ? WHERE user_id = ?",
              (step + 1, now, user_id))
    c.execute("INSERT INTO message_log (user_id, step, sent_at) VALUES (?, ?, ?)",
              (user_id, step, now))
    conn.commit()
    conn.close()

# ============================
# LINE APIヘルパー
# ============================

def send_messages(user_id, messages):
    """ユーザーに複数メッセージをpush送信"""
    api = get_messaging_api()
    if not api:
        print(f"[DRY-RUN] {user_id}: {messages[0][:50]}...")
        return True

    try:
        line_messages = [TextMsg(type="text", text=msg) for msg in messages[:5]]
        api.push_message(PushMessageRequest(to=user_id, messages=line_messages))
        print(f"✅ 送信成功: {user_id}")
        return True
    except Exception as e:
        print(f"❌ 送信失敗 ({user_id}): {e}")
        return False

def reply_message(reply_token, text):
    """Webhookへの返信（無料）"""
    api = get_messaging_api()
    if not api:
        return
    try:
        api.reply_message(ReplyMessageRequest(
            reply_token=reply_token,
            messages=[TextMsg(type="text", text=text)]
        ))
    except Exception as e:
        print(f"❌ 返信失敗: {e}")

def send_welcome(user_id):
    """ウェルカムメッセージ + Day1の1通目を送信"""
    welcome = generate_welcome_message()
    day1_first = STEP_TEMPLATES[1]["messages"][0]
    send_messages(user_id, [welcome, day1_first])

# ============================
# Webhook ハンドラ
# ============================

@app.route("/callback", methods=["POST"])
def callback():
    if not handler:
        return "LINE not configured", 500

    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"

@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

@app.route("/users", methods=["GET"])
def list_users():
    """登録ユーザー一覧（管理用）"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id, registered_at, current_step, is_active FROM users ORDER BY registered_at DESC")
    rows = c.fetchall()
    conn.close()
    return {"users": [{"id": r[0][:10]+"...", "registered": r[1][:10], "step": r[2], "active": r[3]} for r in rows]}

if handler:
    @handler.add(FollowEvent)
    def handle_follow(event):
        """友だち登録イベント"""
        user_id = event.source.user_id
        print(f"🆕 新規登録: {user_id}")
        register_user(user_id)
        send_welcome(user_id)

    @handler.add(UnfollowEvent)
    def handle_unfollow(event):
        """ブロックイベント"""
        user_id = event.source.user_id
        print(f"👋 ブロック: {user_id}")
        unregister_user(user_id)

    @handler.add(MessageEvent, message=TextMessageContent)
    def handle_message(event):
        """テキストメッセージへの返信"""
        user_id = event.source.user_id
        text = event.message.text.lower()

        if any(word in text for word in ["質問", "教えて", "?", "？"]):
            msg = """ご質問ありがとうございます🙏

よくある質問はこちら👇

Q. どのくらい稼げますか？
A. 初月は0〜1万円、慣れると3〜10万円が目安です

Q. 何から始めればいいですか？
A. まずChatGPTに無料登録してみてください

Q. 副業禁止でもできますか？
A. 確定申告が必要な収入（20万超）は報告必要です

他に気になることがあれば
何でも聞いてください😊"""
        else:
            msg = """メッセージありがとうございます😊

毎日役立つAI副業情報をお届けしています✨

ステップ配信は毎日1通ずつ届きます
楽しみにしていてくださいね！"""

        reply_message(event.reply_token, msg)

# ============================
# ステップ配信スケジューラー
# ============================

def run_step_delivery():
    """今日のステップ配信を実行（cron用）"""
    print(f"\n=== ステップ配信 {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")
    targets = get_users_for_today()
    print(f"対象ユーザー: {len(targets)}人")

    for target in targets:
        user_id = target["user_id"]
        step = target["step"]
        step_data = STEP_TEMPLATES.get(step, {})
        messages = step_data.get("messages", [])

        if messages:
            print(f"📨 Day{step} → {user_id[:10]}...")
            success = send_messages(user_id, messages)
            if success:
                mark_step_sent(user_id, step)

    print(f"✅ 配信完了")

# ============================
# メイン
# ============================

if __name__ == "__main__":
    import sys

    init_db()

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "step":
            run_step_delivery()
        elif cmd == "test-welcome":
            # テスト用（実際には送信しない）
            test_id = sys.argv[2] if len(sys.argv) > 2 else "TEST_USER_001"
            register_user(test_id)
            print(f"✅ テストユーザー登録: {test_id}")
            print("\n=== ウェルカムメッセージ（プレビュー）===")
            print(generate_welcome_message())
        elif cmd == "users":
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT * FROM users")
            rows = c.fetchall()
            conn.close()
            print(f"登録ユーザー: {len(rows)}人")
            for row in rows:
                print(f"  {row[0][:15]}... | Day{row[2]} | {row[1][:10]} | {'有効' if row[4] else 'ブロック'}")
        elif cmd == "server":
            port = int(os.getenv("PORT", 8080))
            print(f"🚀 LINE Bot サーバー起動: http://localhost:{port}")
            app.run(host="0.0.0.0", port=port, debug=False)
    else:
        print("使い方:")
        print("  python3 line_bot_server.py server          # Webサーバー起動")
        print("  python3 line_bot_server.py step            # ステップ配信実行")
        print("  python3 line_bot_server.py test-welcome    # テストユーザー登録")
        print("  python3 line_bot_server.py users           # ユーザー一覧")
