"""
A8.net 新着承認プログラム 完全自動処理

【フロー】
1. A8.net にログイン（requests セッション）
2. 新着承認プログラム一覧を取得
3. seen_a8_approved.json で未処理だけ抽出
4. 各プログラムの広告リンクページ → EPC最高テキストリンク取得
5. Gemini で記事生成（レートリミット時は指数バックオフリトライ）
6. はてなブログに投稿
7. 処理済みを記録

【実行】
  python3 money_agent/a8_approved_auto.py          # 通常実行
  python3 money_agent/a8_approved_auto.py dry-run  # 投稿なし（確認用）
"""

import os
import sys
import json
import time
import re
from datetime import datetime
from pathlib import Path

# .env読み込み
def load_env():
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

load_env()

# ============================================================
# 定数
# ============================================================
A8_MEDIA_ID  = os.environ.get("A8_MEDIA_ID", "")
A8_PASSWORD  = os.environ.get("A8_PASSWORD", "")
SEEN_FILE    = Path(__file__).parent / "seen_a8_approved.json"
MAX_PER_RUN  = 5  # 1回の実行で処理する最大件数

BASE_URL     = "https://pub.a8.net"
LOGIN_URL    = f"{BASE_URL}/a8v2/media/loginAction.do"
NEW_LIST_URL = f"{BASE_URL}/a8v2/media/partnerProgramListAction.do?act=search&viewPage=new"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en;q=0.9",
}


# ============================================================
# 処理済み管理
# ============================================================
def load_seen() -> set:
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    return set()

def save_seen(seen: set):
    SEEN_FILE.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=2), encoding="utf-8")


# ============================================================
# A8.net ログイン → セッション返却
# ============================================================
def a8_login():
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        print("[A8] requests または beautifulsoup4 未インストール")
        return None

    if not A8_MEDIA_ID or not A8_PASSWORD:
        print("[A8] A8_MEDIA_ID / A8_PASSWORD が未設定")
        return None

    session = requests.Session()
    session.headers.update(HEADERS)

    try:
        # ログインページ取得（CSRFトークン等があれば取得）
        resp = session.get(LOGIN_URL, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")

        payload = {
            "login":  A8_MEDIA_ID,
            "passwd": A8_PASSWORD,
            "moa":    "/a8",
        }
        # hidden inputがあれば追加（CSRFトークン等）
        for inp in soup.select("input[type=hidden]"):
            name = inp.get("name")
            val  = inp.get("value", "")
            if name and name not in payload:
                payload[name] = val

        login_resp = session.post(LOGIN_URL, data=payload, timeout=15)

        # ログイン成功確認（ログアウトリンクがあれば成功）
        if "logoutAction" in login_resp.text or "ログアウト" in login_resp.text:
            print("[A8] ログイン成功")
            return session
        else:
            print("[A8] ログイン失敗（IDまたはパスワードが違う可能性）")
            return None

    except Exception as e:
        print(f"[A8] ログインエラー: {e}")
        return None


# ============================================================
# 新着承認プログラム一覧を取得
# ============================================================
def fetch_new_approved(session) -> list:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    try:
        resp = session.get(NEW_LIST_URL, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")

        programs = []
        # 広告リンクのinsIdを抽出
        for a in soup.select("a[href*='linkAction.do?insId=']"):
            href = a.get("href", "")
            ins_match = re.search(r"insId=([^&]+)", href)
            if not ins_match:
                continue
            ins_id = ins_match.group(1)

            # 同じinsIdを重複取得しない
            if any(p["ins_id"] == ins_id for p in programs):
                continue

            # 親要素からプログラム名・報酬・確定率・EPCを取得
            container = a
            for _ in range(12):
                container = container.parent
                if not container:
                    break
                text = container.get_text(" ", strip=True)
                if "成果報酬" in text or "EPC" in text:
                    break

            text = container.get_text(" ", strip=True) if container else ""

            # プログラム名
            name_match = re.search(r"プログラム名\s*(.+?)(?:対応デバイス|成果報酬|$)", text)
            name = name_match.group(1).strip()[:80] if name_match else ins_id

            # 広告主名
            company_match = re.search(r"広告主名\s*(.+?)(?:プログラム名|$)", text)
            company = company_match.group(1).strip()[:50] if company_match else ""

            # 成果報酬
            reward_match = re.search(r"成果報酬\s*(.+?)(?:EPC|確定率|$)", text)
            reward = reward_match.group(1).strip()[:100] if reward_match else ""

            # EPC（数値）
            epc = 0.0
            epc_match = re.search(r"EPC\s+([\d.]+)", text)
            if epc_match:
                try:
                    epc = float(epc_match.group(1))
                except ValueError:
                    pass

            # 確定率
            rate_match = re.search(r"確定率\s*([\d.]+)％", text)
            confirm_rate = f"{rate_match.group(1)}%" if rate_match else ""

            programs.append({
                "ins_id": ins_id,
                "name": name,
                "company": company,
                "reward": reward,
                "epc": epc,
                "confirm_rate": confirm_rate,
            })

        print(f"[A8] 新着承認プログラム: {len(programs)}件")
        return programs

    except Exception as e:
        print(f"[A8] 一覧取得エラー: {e}")
        return []


# ============================================================
# 広告リンクページ → EPC最高のテキストリンクURLを取得
# ============================================================
def fetch_best_link(session, ins_id: str) -> str:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return ""

    url = f"{BASE_URL}/a8v2/media/linkAction.do?insId={ins_id}"
    try:
        resp = session.get(url, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text("\n")

        best_url = ""
        best_epc = -1.0

        # px.a8.net のリンクとその直前のEPC値をペアで探す
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        for i, line in enumerate(lines):
            if line.startswith("https://px.a8.net"):
                # このURLの前後でEPC値を探す（最大10行前）
                context = lines[max(0, i-10):i]
                epc_val = 0.0
                for ctx in reversed(context):
                    m = re.match(r"^([\d.]+)$", ctx)
                    if m:
                        try:
                            epc_val = float(m.group(1))
                        except ValueError:
                            pass
                        break
                # テキスト素材のみ（バナー除外）→ 素材タイプ「テキスト」かメールを優先
                # URLの前20行にテキストタイプの記述があるか確認
                is_text = any("テキスト" in c or "メール" in c for c in context[-15:])
                if is_text and epc_val > best_epc:
                    best_epc = epc_val
                    best_url = line

        # テキスト素材が見つからなければ最初のpx.a8.netリンクを使用
        if not best_url:
            for line in lines:
                if line.startswith("https://px.a8.net"):
                    best_url = line
                    break

        print(f"[A8] {ins_id} → ベストリンク EPC:{best_epc} {best_url[:60]}")
        return best_url

    except Exception as e:
        print(f"[A8] リンク取得エラー ({ins_id}): {e}")
        return ""


# ============================================================
# Gemini で記事生成（レートリミット時は指数バックオフリトライ）
# ============================================================
def generate_article(program: dict, max_retries: int = 5):
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("[Gemini] GEMINI_API_KEY未設定")
        return None

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
    except ImportError:
        print("[Gemini] google-genai未インストール")
        return None

    year = datetime.now().year
    name         = program.get("name", "")
    company      = program.get("company", "")
    reward       = program.get("reward", "")
    affiliate_url = program.get("affiliate_url", "")

    prompt = f"""あなたはアフィリエイトブログの専門ライターです。
以下のサービスを紹介するSEO最適化記事を書いてください。

【サービス情報】
- サービス名: {name}
- 提供会社: {company}
- 報酬: {reward}
- アフィリエイトURL: {affiliate_url}

【記事要件】
- 文字数: 2000〜3000文字
- 対象読者: 副業・節約に興味があるサラリーマン・フリーランス・主婦
- 構成: 導入 → サービス概要 → メリット3〜5個 → こんな人におすすめ → 料金・登録方法 → まとめ
- タイトルはSEOキーワードを含む（例:「【{year}年最新】{name}の評判は？メリット・デメリットを徹底解説」）
- 自然な口調、見出しはMarkdown（## / ###）
- 記事末尾にCTAを入れる:
  <a href="{affiliate_url}" rel="nofollow">▶ {name}の公式サイトで詳細を確認する</a>
- コードブロックなし、JSONのみで返す

以下のJSON形式で返してください:
{{
  "title": "記事タイトル",
  "keyword": "SEOメインキーワード（20文字以内）",
  "category": "副業",
  "tags": ["タグ1", "タグ2", "タグ3"],
  "body": "本文（Markdown + CTAリンク含む）"
}}"""

    wait = 35
    for attempt in range(max_retries):
        try:
            resp = client.models.generate_content(
                model="gemini-2.0-flash-lite",
                contents=prompt,
            )
            text = resp.text.strip()
            if text.startswith("```"):
                text = text.split("```", 2)[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.rsplit("```", 1)[0]

            article = json.loads(text.strip())
            article["program_id"]   = program["ins_id"]
            article["program_name"] = name
            article["generated_at"] = datetime.now().isoformat()
            return article

        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                if attempt < max_retries - 1:
                    print(f"[Gemini] レートリミット。{wait}秒後にリトライ ({attempt+1}/{max_retries})...")
                    time.sleep(wait)
                    wait = min(wait * 2, 120)
                else:
                    print(f"[Gemini] リトライ上限到達: {err[:150]}")
                    return None
            else:
                print(f"[Gemini] 記事生成エラー: {err[:200]}")
                return None

    return None


# ============================================================
# メイン処理
# ============================================================
def run(dry_run: bool = False):
    print(f"\n=== A8新着承認プログラム 自動処理 {'[DRY RUN]' if dry_run else ''} ===")
    print(f"実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # ログイン
    session = a8_login()
    if not session:
        print("ログイン失敗。終了。")
        sys.exit(1)

    # 新着承認一覧取得
    programs = fetch_new_approved(session)
    if not programs:
        print("新着承認プログラムなし。終了。")
        return

    # 未処理フィルタ
    seen = load_seen()
    new_programs = [p for p in programs if p["ins_id"] not in seen]
    print(f"未処理: {len(new_programs)}件 / 全{len(programs)}件")

    if not new_programs:
        print("全件処理済み。終了。")
        return

    # EPC降順でソート
    new_programs.sort(key=lambda x: x["epc"], reverse=True)

    sys.path.insert(0, str(Path(__file__).parent))
    from hatena_atomapi import post as hatena_post

    posted = 0
    for program in new_programs[:MAX_PER_RUN]:
        print(f"\n--- {program['name']} (EPC:{program['epc']}, 報酬:{program['reward']}) ---")

        # ベストリンク取得
        affiliate_url = fetch_best_link(session, program["ins_id"])
        if not affiliate_url:
            print("  アフィリエイトリンク取得失敗。スキップ。")
            continue
        program["affiliate_url"] = affiliate_url

        time.sleep(2)  # A8へのリクエスト間隔

        # 記事生成
        article = generate_article(program)
        if not article:
            print("  記事生成失敗。スキップ（次回リトライ対象）。")
            continue

        print(f"  タイトル: {article['title'][:70]}")
        print(f"  文字数: {len(article.get('body', ''))}文字")

        if dry_run:
            print(f"  [DRY RUN] 本文冒頭:\n{article.get('body','')[:300]}...")
            seen.add(program["ins_id"])
            posted += 1
        else:
            url = hatena_post(article)
            if url:
                print(f"  投稿完了: {url}")
                seen.add(program["ins_id"])
                posted += 1
            else:
                print("  投稿失敗。")
            time.sleep(5)

    save_seen(seen)
    print(f"\n=== 完了: {posted}件投稿 ===")


if __name__ == "__main__":
    dry_run = "dry-run" in sys.argv or "dry_run" in sys.argv
    run(dry_run=dry_run)
