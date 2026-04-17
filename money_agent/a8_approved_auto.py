"""
A8.net 新着承認プログラム 完全自動処理

【フロー】
1. A8.net にログイン（requests セッション）
2. 新着承認プログラム一覧を取得
3. Supabase で未処理だけ抽出
4. 各プログラムの広告リンクページ → EPC最高テキストリンク取得
5. Gemini で記事生成（tenacity 指数バックオフリトライ）
6. はてなブログに投稿
7. 処理済みを記録
8. 失敗アイテムはスキップし、詳細をDBに記録

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

# Supabase クライアント
sys.path.insert(0, str(Path(__file__).parent.parent))
from db_client import db

# crawlers パッケージ（A8キャッシュ管理）
from crawlers.crawler_a8 import save_program as _save_to_x_cache_new

# ============================================================
# 定数
# ============================================================
A8_MEDIA_ID = os.environ.get("A8_MEDIA_ID", "")
A8_PASSWORD  = os.environ.get("A8_PASSWORD", "")
MAX_PER_RUN  = 5  # 1回の実行で処理する最大件数

BASE_URL     = "https://pub.a8.net"
LOGIN_URL    = f"{BASE_URL}/a8v2/media/loginAction.do"
NEW_LIST_URL = f"{BASE_URL}/a8v2/media/partnerProgramListAction.do?act=search&viewPage=new"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en;q=0.9",
}


# ============================================================
# 共通ヘルパー
# ============================================================
def _save_to_x_cache(program: dict, affiliate_url: str, hatena_url: str = "") -> None:
    """crawlers.crawler_a8.save_program に委譲する"""
    _save_to_x_cache_new(program, affiliate_url, hatena_url=hatena_url)


def _safe_text(element, default: str = "") -> str:
    """
    BeautifulSoup 要素から安全にテキストを取得する。
    要素が None / AttributeError / その他例外でも default を返す。
    """
    if element is None:
        return default
    try:
        return element.get_text(strip=True)
    except Exception:
        return default


def _log_error(ins_id: str, step: str, error: str) -> None:
    """スクレイピング・処理失敗をDBに記録する"""
    try:
        db.insert_post(
            platform="a8_scrape",
            post_type="approved",
            label=f"{step}:{ins_id}"[:200],
            chars=0,
            text=f"処理失敗: {step} / {ins_id}",
            success=False,
            error_message=f"[A8承認] step={step} ins_id={ins_id}: {error}",
        )
    except Exception as e:
        print(f"[A8] DBエラーログ記録失敗: {e}")


# ============================================================
# 処理済み管理（DB版）
# ============================================================
def load_seen() -> set:
    try:
        return db.get_a8_processed_ids("approved")
    except Exception as e:
        print(f"[A8] 処理済みDB読み込み失敗: {e}")
        return set()

def save_seen(seen: set):
    """後方互換のために残す（内部では mark_single を使う）"""
    pass

def mark_single(program_id: str) -> None:
    """1件を処理済みとして DB にマークする（並列安全）"""
    try:
        db.mark_a8_processed(program_id, "approved")
    except Exception as e:
        print(f"[A8] 処理済みDB書き込み失敗 ({program_id}): {e}")


# ============================================================
# A8.net ログイン → セッション返却
# ============================================================
def a8_login(max_retries: int = 3, timeout: int = 30):
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

    for attempt in range(max_retries):
        try:
            resp = session.get(LOGIN_URL, timeout=timeout)
            soup = BeautifulSoup(resp.text, "html.parser")

            payload = {
                "login":  A8_MEDIA_ID,
                "passwd": A8_PASSWORD,
                "moa":    "/a8",
            }
            for inp in soup.select("input[type=hidden]"):
                name = inp.get("name")
                val  = inp.get("value", "")
                if name and name not in payload:
                    payload[name] = val

            login_resp = session.post(LOGIN_URL, data=payload, timeout=timeout)

            if "logoutAction" in login_resp.text or "ログアウト" in login_resp.text:
                print("[A8] ログイン成功")
                return session
            else:
                print("[A8] ログイン失敗（IDまたはパスワードが違う可能性）")
                return None

        except Exception as e:
            if attempt < max_retries - 1:
                wait_sec = 10 * (attempt + 1)
                print(f"[A8] ログインエラー ({attempt + 1}/{max_retries}): {e} → {wait_sec}秒後にリトライ")
                time.sleep(wait_sec)
            else:
                err_msg = str(e)
                print(f"[A8] ログインエラー（リトライ上限）: {err_msg}")
                _log_error("login", "a8_login", err_msg)
                return None

    return None


# ============================================================
# 新着承認プログラム一覧を取得
# ============================================================
def fetch_new_approved(session) -> list:
    """
    ログイン済みセッションから新着承認プログラムを取得する。

    - プログラム単位で例外を隔離
    - AttributeError 等が出てもそのアイテムのみスキップしてDBに記録
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    try:
        resp = session.get(NEW_LIST_URL, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        err_msg = str(e)
        print(f"[A8] 一覧ページ取得エラー: {err_msg}")
        _log_error("list_page", "fetch_new_approved", err_msg)
        return []

    programs = []
    link_elements = soup.select("a[href*='linkAction.do?insId=']")

    for a in link_elements:
        ins_id = ""
        try:
            href = a.get("href", "") or ""
            ins_match = re.search(r"insId=([^&]+)", href)
            if not ins_match:
                continue
            ins_id = ins_match.group(1)

            # 同一ins_idの重複スキップ
            if any(p["ins_id"] == ins_id for p in programs):
                continue

            # 親要素を最大12階層遡り「成果報酬」「EPC」を含むコンテナを探す
            container = a
            found_container = False
            for _ in range(12):
                parent = getattr(container, "parent", None)
                if parent is None:
                    break
                container = parent
                try:
                    text = container.get_text(" ", strip=True)
                    if "成果報酬" in text or "EPC" in text:
                        found_container = True
                        break
                except Exception:
                    break

            text = ""
            if found_container or container is not None:
                try:
                    text = container.get_text(" ", strip=True)
                except Exception:
                    text = ""

            # 各フィールドを安全に抽出（正規表現で取れなければ空文字）
            name_match = re.search(r"プログラム名\s*(.+?)(?:対応デバイス|成果報酬|$)", text)
            name = name_match.group(1).strip()[:80] if name_match else ins_id

            company_match = re.search(r"広告主名\s*(.+?)(?:プログラム名|$)", text)
            company = company_match.group(1).strip()[:50] if company_match else ""

            reward_match = re.search(r"成果報酬\s*(.+?)(?:EPC|確定率|$)", text)
            reward = reward_match.group(1).strip()[:100] if reward_match else ""

            epc = 0.0
            epc_match = re.search(r"EPC\s+([\d.]+)", text)
            if epc_match:
                try:
                    epc = float(epc_match.group(1))
                except ValueError:
                    pass

            rate_match = re.search(r"確定率\s*([\d.]+)％", text)
            confirm_rate = f"{rate_match.group(1)}%" if rate_match else ""

            programs.append({
                "ins_id":       ins_id,
                "name":         name,
                "company":      company,
                "reward":       reward,
                "epc":          epc,
                "confirm_rate": confirm_rate,
            })

        except Exception as e:
            err_msg = str(e)
            print(f"[A8] アイテム解析スキップ (ins_id={ins_id or '?'}): {err_msg}")
            _log_error(ins_id or "unknown", "fetch_new_approved_item", err_msg)
            continue  # このアイテムのみスキップして次へ

    print(f"[A8] 新着承認プログラム: {len(programs)}件")
    return programs


# ============================================================
# 広告リンクページ → EPC最高のテキストリンクURLを取得
# ============================================================
def fetch_best_link(session, ins_id: str) -> str:
    """
    ins_id に対応する広告リンクページから EPC 最高のテキストリンクを返す。
    取得失敗は空文字返却 + DB記録。
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return ""

    url = f"{BASE_URL}/a8v2/media/linkAction.do?insId={ins_id}"
    try:
        resp = session.get(url, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text("\n")
    except Exception as e:
        err_msg = str(e)
        print(f"[A8] リンクページ取得エラー ({ins_id}): {err_msg}")
        _log_error(ins_id, "fetch_best_link_page", err_msg)
        return ""

    try:
        best_url = ""
        best_epc = -1.0

        lines = [l.strip() for l in text.split("\n") if l.strip()]
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
                continue  # この行の処理に失敗しても次の行へ

        # テキスト素材が見つからなければ最初の px.a8.net リンクを使用
        if not best_url:
            for line in lines:
                if line.startswith("https://px.a8.net"):
                    best_url = line
                    break

        print(f"[A8] {ins_id} → ベストリンク EPC:{best_epc} {best_url[:60]}")
        return best_url

    except Exception as e:
        err_msg = str(e)
        print(f"[A8] リンク解析エラー ({ins_id}): {err_msg}")
        _log_error(ins_id, "fetch_best_link_parse", err_msg)
        return ""


# ============================================================
# Gemini で記事生成（gemini_client 経由 → tenacity リトライ付き）
# ============================================================
def generate_article(program: dict):
    """
    A8承認プログラム情報をもとに Gemini で記事を生成する。
    gemini_client.generate() 経由で tenacity の指数バックオフリトライが有効。
    失敗時は None を返し、呼び出し元でDBに記録する。
    """
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from gemini_client import generate as gemini_generate, strip_code_block
    except ImportError:
        print("[Gemini] gemini_client 未インポート")
        return None

    year          = datetime.now().year
    name          = program.get("name", "")
    company       = program.get("company", "")
    reward        = program.get("reward", "")
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

    raw = gemini_generate(prompt, use_cache=False)
    if not raw:
        print(f"[Gemini] 記事生成失敗（全リトライ消耗）: {name}")
        return None

    try:
        text = strip_code_block(raw)
        article = json.loads(text)
        article["program_id"]   = program["ins_id"]
        article["program_name"] = name
        article["generated_at"] = datetime.now().isoformat()
        return article
    except Exception as e:
        err_msg = str(e)
        print(f"[Gemini] JSONパースエラー ({name}): {err_msg}")
        _log_error(program.get("ins_id", name), "generate_article_json", err_msg)
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
        return

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
        ins_id    = program.get("ins_id", "")
        prog_name = program.get("name", ins_id)
        print(f"\n--- {prog_name} (EPC:{program.get('epc',0)}, 報酬:{program.get('reward','')}) ---")

        try:
            # ① ベストリンク取得
            affiliate_url = fetch_best_link(session, ins_id)
            if not affiliate_url:
                print("  アフィリエイトリンク取得失敗。スキップ。")
                _log_error(ins_id, "fetch_best_link", "リンク未取得")
                continue

            try:
                from tracking import add_a8_sid
                affiliate_url = add_a8_sid(affiliate_url, "hatena")
            except Exception as e:
                print(f"  [tracking] パラメータ付与スキップ: {e}")
            program["affiliate_url"] = affiliate_url
            print(f"  計測URL: {affiliate_url[:80]}...")

            time.sleep(2)

            # ② 記事生成
            article = generate_article(program)
            if not article:
                print("  記事生成失敗。スキップ（次回リトライ対象）。")
                _log_error(ins_id, "generate_article", "Gemini応答なし")
                continue

            print(f"  タイトル: {article['title'][:70]}")
            print(f"  文字数: {len(article.get('body', ''))}文字")

            # ③ 投稿
            if dry_run:
                print(f"  [DRY RUN] 本文冒頭:\n{article.get('body','')[:300]}...")
                _save_to_x_cache(program, affiliate_url)
                mark_single(ins_id)
                posted += 1
            else:
                url = hatena_post(article)
                if url:
                    print(f"  投稿完了: {url}")
                    # X投稿用キャッシュに保存（affiliate_url + hatena記事URL）
                    _save_to_x_cache(program, affiliate_url, hatena_url=url)
                    mark_single(ins_id)
                    posted += 1
                else:
                    print("  投稿失敗。")
                    _log_error(ins_id, "hatena_post", "投稿URLが返らなかった")
                time.sleep(5)

        except Exception as e:
            err_msg = str(e)
            print(f"  [run] 予期しないエラー ({prog_name})、スキップ: {err_msg}")
            _log_error(ins_id, "run_loop", err_msg)
            continue  # このプログラムのみスキップして次へ

    print(f"\n=== 完了: {posted}件投稿 ===")


if __name__ == "__main__":
    dry_run = "dry-run" in sys.argv or "dry_run" in sys.argv
    run(dry_run=dry_run)
