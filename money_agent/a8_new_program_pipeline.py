"""
A8.net 新着案件 → 記事自動生成 → はてなブログ投稿パイプライン

【フロー】
1. A8.net 公開ページから新着案件を取得（スクレイピング）
2. 未処理の案件をフィルタリング（seen_programs.json で重複排除）
3. Gemini API で紹介記事を自動生成（2000〜3000文字）
4. はてなブログ AtomPub API で投稿（Playwright不要）
5. 処理済み案件を記録

【実行方法】
  python3 money_agent/a8_new_program_pipeline.py          # 通常実行（最大3件投稿）
  python3 money_agent/a8_new_program_pipeline.py dry-run  # 記事生成のみ（投稿なし）
  python3 money_agent/a8_new_program_pipeline.py status   # 処理済み案件数を表示
"""

import os
import sys
import json
import time
import requests
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
SEEN_FILE = Path(__file__).parent / "seen_a8_programs.json"
MAX_POSTS_PER_RUN = 3  # 1実行あたりの最大投稿数
HATENA_ID = os.environ.get("HATENA_ID", "pi-natu-butter")
HATENA_BLOG_ID = os.environ.get("HATENA_BLOG_ID", "smart-earn-life.hateblo.jp")
HATENA_API_KEY = os.environ.get("HATENA_API_KEY", "")

A8_SEARCH_URL = "https://www.a8.net/a8a/search_program.do"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en;q=0.9",
}

# ============================================================
# 見込み高単価ジャンル（優先的に取得・記事化）
# Search Console の実績から「DX・クラウド会計・バックオフィス」を上位に昇格
# ============================================================
TARGET_GENRES = [
    # ── 優先1: Search Console で伸びているジャンル（実績あり）──────────
    {"genre": "クラウド会計",       "min_reward": 3000, "kw": "クラウド会計 比較 中小企業",   "priority": 10},
    {"genre": "DX・業務効率化",     "min_reward": 5000, "kw": "DX ツール おすすめ 中小企業", "priority": 10},
    {"genre": "バックオフィスSaaS", "min_reward": 5000, "kw": "バックオフィス 効率化 ツール", "priority": 10},
    # ── 優先2: 高単価ジャンル ─────────────────────────────────────────
    {"genre": "証券・FX",           "min_reward": 5000, "kw": "証券口座 開設 おすすめ",       "priority": 8},
    {"genre": "プログラミングスクール", "min_reward": 8000, "kw": "プログラミングスクール 比較", "priority": 8},
    {"genre": "転職",               "min_reward": 5000, "kw": "転職エージェント おすすめ",     "priority": 7},
    # ── 優先3: 安定ジャンル ───────────────────────────────────────────
    {"genre": "クレジットカード",   "min_reward": 3000, "kw": "クレジットカード おすすめ",     "priority": 5},
    {"genre": "英会話",             "min_reward": 3000, "kw": "英会話オンライン おすすめ",     "priority": 5},
    {"genre": "動画配信",           "min_reward": 1000, "kw": "VOD 動画配信 比較",             "priority": 3},
    {"genre": "電力",               "min_reward": 2000, "kw": "電力会社 乗り換え",             "priority": 3},
]

# ============================================================
# Search Console の好調クエリ（記事生成プロンプトに動的注入）
# ============================================================
def _load_sc_top_keywords(max_kw: int = 5) -> list[str]:
    """
    search_console_analysis.json からクリック数上位のクエリを取得。
    記事生成時のプロンプトに差し込んで、検索需要のある表現を使わせる。
    """
    sc_path = Path(__file__).parent / "search_console_analysis.json"
    if not sc_path.exists():
        return []
    try:
        data = json.loads(sc_path.read_text(encoding="utf-8"))
        queries = data.get("top_queries", [])
        # クリック数降順で上位 max_kw 件
        sorted_q = sorted(queries, key=lambda x: x.get("clicks", 0), reverse=True)
        return [q["query"] for q in sorted_q[:max_kw]]
    except Exception:
        return []


# ============================================================
# 既読管理
# ============================================================
def load_seen() -> set:
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    return set()

def save_seen(seen: set):
    SEEN_FILE.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=2), encoding="utf-8")


# ============================================================
# A8.net 公開プログラム検索（スクレイピング）
# ============================================================
def fetch_a8_new_programs(genre: str, limit: int = 10):
    """
    A8.net のプログラム検索ページから案件を取得する。
    公開情報のみ（ログイン不要）。
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("[A8] BeautifulSoup4 未インストール。スキップ。")
        return []

    programs = []
    try:
        params = {
            "genre": genre,
            "sort": "new",
            "p": 1,
        }
        resp = requests.get(A8_SEARCH_URL, params=params, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"[A8] HTTPエラー {resp.status_code} ジャンル={genre}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        # A8.netのプログラム一覧セレクタ（構造変更時は更新）
        items = soup.select(".program-list-item, .prg-item, li.item")

        for item in items[:limit]:
            name_el = item.select_one(".program-name, .prg-name, h3, h4")
            reward_el = item.select_one(".reward, .commission, .fee")
            desc_el = item.select_one(".description, .desc, p")
            link_el = item.select_one("a[href]")

            if not name_el:
                continue

            name = name_el.get_text(strip=True)
            reward = reward_el.get_text(strip=True) if reward_el else ""
            desc = desc_el.get_text(strip=True)[:200] if desc_el else ""
            link = link_el.get("href", "") if link_el else ""

            prog_id = f"a8_{genre}_{name[:20]}"
            programs.append({
                "id": prog_id,
                "name": name,
                "genre": genre,
                "reward": reward,
                "description": desc,
                "link": link,
            })

    except Exception as e:
        print(f"[A8] スクレイピングエラー ({genre}): {e}")

    return programs


def fetch_programs_via_ddg(limit: int = 15):
    """
    DuckDuckGoで新着A8案件を検索（スクレイピングが取れない場合のフォールバック）
    """
    try:
        from ddgs import DDGS
    except ImportError:
        return []

    seen = load_seen()
    programs = []
    queries = [
        "A8.net 新着プログラム 2026 高単価 アフィリエイト",
        "A8.net 新規プログラム クレジットカード 証券 2026",
        "A8.net プログラム プログラミングスクール 英会話 転職 2026",
    ]

    ddgs = DDGS()
    for query in queries:
        try:
            results = list(ddgs.text(query, region="jp-jp", max_results=8))
            for r in results:
                link = r.get("href", r.get("url", ""))
                title = r.get("title", "")
                body = r.get("body", r.get("snippet", ""))[:300]
                prog_id = f"ddg_{link[:80]}"
                if prog_id in seen or not title:
                    continue
                # A8関連フィルタ
                if not any(kw in (title + body).lower() for kw in ["a8", "アフィリエイト", "報酬"]):
                    continue
                programs.append({
                    "id": prog_id,
                    "name": title,
                    "genre": "未分類",
                    "reward": "",
                    "description": body,
                    "link": link,
                })
                if len(programs) >= limit:
                    break
        except Exception as e:
            print(f"[DDG] エラー: {e}")
        time.sleep(1)

    return programs


# ============================================================
# Gemini API で紹介記事を生成
# ============================================================
def generate_program_article(program: dict):
    """A8.net案件情報をもとにGeminiで紹介記事を生成（SC キーワード動的注入）"""
    try:
        from money_agent.gemini_client import generate as gemini_generate, strip_code_block
    except ImportError:
        # パスが通っていない環境用フォールバック
        _sys.path.insert(0, str(Path(__file__).parent))
        try:
            from gemini_client import generate as gemini_generate, strip_code_block
        except ImportError:
            print("[Gemini] gemini_client未インポート")
            return None

    genre  = program.get("genre", "")
    name   = program.get("name", "")
    reward = program.get("reward", "")
    desc   = program.get("description", "")
    year   = datetime.now().year

    # Search Console 上位クエリを動的に注入（SEO 親和性を高める）
    sc_keywords = _load_sc_top_keywords(max_kw=5)
    sc_kw_section = ""
    if sc_keywords:
        kw_list = "\n".join(f"  - {kw}" for kw in sc_keywords)
        sc_kw_section = f"""
【Search Console で検索需要が実証されているキーワード（記事中に自然な形で使用すること）】
{kw_list}
"""

    prompt = f"""あなたはアフィリエイトブログの専門ライターです。
以下のA8.net新着プログラムを紹介するSEO最適化記事を書いてください。

【案件情報】
- サービス名: {name}
- ジャンル: {genre}
- 報酬: {reward}
- 概要: {desc}
{sc_kw_section}
【記事要件】
- 文字数: 2000〜3000文字
- 対象読者: 副業・節約に興味があるサラリーマン・主婦
- 構成: 導入 → サービス概要 → メリット3〜5個 → こんな人におすすめ → 登録方法 → まとめ
- タイトルはSEOキーワードを含む（例: 「【{year}年】{name}の評判は？メリット・デメリットを徹底解説」）
- 自然な口調で読みやすく
- アフィリエイト感を出しすぎない（第三者的な視点）
- 見出しはMarkdown（## / ###）を使用
- 最後にCTA（公式サイトで詳細を確認する）を入れる

以下のJSON形式で返してください（コードブロック不要）:
{{
  "title": "記事タイトル",
  "keyword": "SEOメインキーワード（20文字以内）",
  "category": "カテゴリ（副業/投資/節約/ビジネスツールのいずれか）",
  "tags": ["タグ1", "タグ2", "タグ3"],
  "body": "本文（Markdown）"
}}"""

    # 記事は毎回新鮮な内容（キャッシュなし）、バックオフ込み
    raw = gemini_generate(prompt, use_cache=False)
    if not raw:
        print(f"[Gemini] 記事生成失敗 ({name})")
        return None

    try:
        text = strip_code_block(raw)
        article = json.loads(text)
        article["program_id"]   = program["id"]
        article["program_name"] = name
        article["generated_at"] = datetime.now().isoformat()
        return article
    except Exception as e:
        print(f"[Gemini] JSONパースエラー ({name}): {e}")
        return None


import sys as _sys
import re as _re
_sys.path.insert(0, str(Path(__file__).parent))
from hatena_atomapi import post as _hatena_post

def post_to_hatena(article: dict, draft: bool = False):
    return _hatena_post(article, draft=draft)


# ============================================================
# 案件スコアリング（高単価・高成約 + Search Console実績ジャンルを優先）
# ============================================================
# Search Console で伸びているジャンル（最優先）
_SC_WINNING_GENRES = ["クラウド会計", "DX", "バックオフィス", "SaaS", "業務効率", "freee", "マネーフォワード", "Chatwork"]
# 高単価ジャンル
_HIGH_VALUE_GENRES = ["証券", "FX", "プログラミング", "転職", "保険"]
# 中単価ジャンル
_MID_VALUE_GENRES  = ["英会話", "会計", "電力", "クラウド", "クレジット"]

def _parse_reward(reward_str: str) -> int:
    """報酬文字列から数値を抽出（例: '3,000円' → 3000）"""
    if not reward_str:
        return 0
    nums = _re.findall(r'\d+', reward_str.replace(",", ""))
    if not nums:
        return 0
    return max(int(n) for n in nums)

def score_program(program: dict) -> int:
    """
    案件をスコアリングして優先順位を返す（高いほど優先）

    スコア構成:
      - 報酬単価:             最大50点
      - SC実績ジャンル:       +40点（freee/マネーフォワード/DX系 = 検索需要が実証済み）
      - 高単価ジャンル:       +30点
      - 中単価ジャンル:       +15点
      - ジャンル優先度:       最大+10点（TARGET_GENRES の priority 値）
    """
    score = 0
    reward_num = _parse_reward(program.get("reward", ""))
    genre      = program.get("genre", "")
    name       = program.get("name", "")
    combined   = genre + name  # ジャンル名と案件名の両方で判定

    # 報酬スコア
    if reward_num >= 10000:
        score += 50
    elif reward_num >= 5000:
        score += 35
    elif reward_num >= 3000:
        score += 25
    elif reward_num >= 1000:
        score += 15
    elif reward_num > 0:
        score += 5

    # ジャンルスコア（Search Console 実績優先）
    if any(g in combined for g in _SC_WINNING_GENRES):
        score += 40  # SC で伸びているジャンルを最優先
    elif any(g in combined for g in _HIGH_VALUE_GENRES):
        score += 30
    elif any(g in combined for g in _MID_VALUE_GENRES):
        score += 15

    # TARGET_GENRES の priority 値を加算
    for tg in TARGET_GENRES:
        if tg["genre"] in combined:
            score += tg.get("priority", 0)
            break

    return score


# ============================================================
# メインパイプライン
# ============================================================
def run_pipeline(dry_run: bool = False):
    """新着A8案件を取得 → 記事生成 → はてな投稿"""
    print(f"\n=== A8新着案件パイプライン開始 {'[DRY RUN]' if dry_run else ''} ===")
    print(f"実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    seen = load_seen()
    print(f"処理済み案件数: {len(seen)}")

    # 案件取得
    all_programs = []

    # ① A8.net スクレイピング（priority 降順で上位4ジャンルを処理）
    sorted_genres = sorted(TARGET_GENRES, key=lambda x: x.get("priority", 0), reverse=True)
    for genre_info in sorted_genres[:4]:  # 1実行4ジャンルまで
        programs = fetch_a8_new_programs(genre_info["genre"], limit=5)
        all_programs.extend(programs)
        time.sleep(2)  # リクエスト間隔

    # ② スクレイピングで取れなかった場合はDDG検索
    if not all_programs:
        print("[Pipeline] スクレイピング失敗 → DuckDuckGo検索にフォールバック")
        all_programs = fetch_programs_via_ddg()

    # 未処理のみフィルタ
    new_programs = [p for p in all_programs if p["id"] not in seen]
    print(f"新着案件数: {len(new_programs)} (全{len(all_programs)}件中)")

    if not new_programs:
        print("新着案件なし。終了。")
        return

    # スコアリングで高単価・高成約ジャンルを優先
    for p in new_programs:
        p["_score"] = score_program(p)
    new_programs.sort(key=lambda p: p["_score"], reverse=True)
    print("案件優先順位（スコア降順）:")
    for p in new_programs[:MAX_POSTS_PER_RUN]:
        print(f"  [{p['_score']:3d}点] {p['name'][:30]} ({p['genre']}) 報酬:{p.get('reward','不明')}")

    # 最大MAX_POSTS_PER_RUN件処理
    processed = 0
    for program in new_programs[:MAX_POSTS_PER_RUN]:
        print(f"\n--- 案件処理: {program['name']} ({program['genre']}) ---")

        # 記事生成
        article = generate_program_article(program)
        if not article:
            seen.add(program["id"])
            continue

        print(f"  タイトル: {article['title'][:60]}")
        print(f"  キーワード: {article.get('keyword', '')}")
        print(f"  文字数: {len(article.get('body', ''))}文字")

        if not dry_run:
            url = post_to_hatena(article)
            if url:
                processed += 1
                seen.add(program["id"])
            time.sleep(3)  # 投稿間隔
        else:
            # dry-run: 本文の冒頭を表示
            print(f"  本文冒頭: {article.get('body', '')[:200]}...")
            seen.add(program["id"])
            processed += 1

    save_seen(seen)
    print(f"\n=== パイプライン完了: {processed}件投稿 ===")


def show_status():
    seen = load_seen()
    print(f"処理済み案件数: {len(seen)}")
    for prog_id in sorted(seen)[-10:]:
        print(f"  {prog_id}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "status" in args:
        show_status()
    elif "dry-run" in args or "dry_run" in args:
        run_pipeline(dry_run=True)
    else:
        run_pipeline(dry_run=False)
