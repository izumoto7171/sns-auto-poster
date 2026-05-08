"""
週次トレンドハンター — 毎週月曜 GitHub Actions から実行

フロー:
  1. pytrends で日本のリアルタイムトレンドキーワードを取得（失敗時は月別季節キーワードで代替）
  2. Gemini で各キーワードを「SNS×アフィリエイト向き度」でスコアリング
  3. スコア閾値以上の候補プログラムを生成
  4. program_portfolio.json に未登録のものを status="candidate" で追加
  5. affiliate_url が設定されたものは a8_programs_cache / history にも投入（即座に投稿候補へ）
  6. 結果サマリーを標準出力

deal_selector.py との連携:
  新規登録案件の name/hashtags が _A8_SEASONAL のキーワードにマッチすれば
  自動的に季節ブーストスコアが乗る。追加コード不要。

実行:
  python3 crawlers/weekly_trend_hunter.py          # 通常実行
  python3 crawlers/weekly_trend_hunter.py --dry-run # 書き込みなし・確認のみ
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "money_agent"))

PORTFOLIO_PATH        = ROOT_DIR / "money_agent" / "config" / "program_portfolio.json"
AMAZON_KEYWORDS_PATH  = ROOT_DIR / "x_automation" / "weekly_amazon_keywords.json"
RAKUTEN_KEYWORDS_PATH = ROOT_DIR / "x_automation" / "weekly_rakuten_keywords.json"
CACHE_PATH     = ROOT_DIR / "money_agent" / "a8_programs_cache.json"
HISTORY_PATH   = ROOT_DIR / "money_agent" / "a8_programs_history.json"

SNS_SCORE_THRESHOLD = 6   # このスコア以上をポートフォリオ候補にする
MAX_NEW_PROGRAMS    = 15  # 1回の実行で追加する上限件数（多ジャンル対応）
MIN_CACHE_TARGET    = 30  # a8_programs_history.json の目標最低件数

# ── 月別季節キーワード（pytrends 失敗時のフォールバック） ──────────────
_MONTHLY_KEYWORDS: dict[int, list[str]] = {
    1:  ["確定申告", "iDeCo", "新NISA", "節税", "ふるさと納税"],
    2:  ["確定申告", "クラウド会計", "副業収入", "フリーランス", "節税"],
    3:  ["確定申告", "新生活", "転職", "クレジットカード", "引越し"],
    4:  ["新社会人", "クレジットカード", "資産運用", "副業", "保険"],
    5:  ["副業", "在宅ワーク", "サイドFIRE", "AI副業", "ブログ収入"],
    6:  ["ボーナス 運用", "証券口座 開設", "新NISA", "つみたてNISA", "投資初心者"],
    7:  ["夏のボーナス 投資", "副業", "FIRE", "楽天証券", "SBI証券"],
    8:  ["お盆 副業", "AI 稼ぐ", "在宅ワーク", "ブログ アフィリエイト", "節約"],
    9:  ["転職", "副業 秋", "資産運用", "iDeCo 節税", "フリーランス"],
    10: ["年末調整", "医療保険", "生命保険", "iDeCo", "ふるさと納税"],
    11: ["ふるさと納税 駆け込み", "クレジットカード 年末", "ポイ活", "楽天カード", "節税"],
    12: ["ふるさと納税 締め切り", "確定申告 準備", "クラウド会計", "副業 年収", "節約"],
}

# テーマキーワードマッピング（Gemini レスポンス → portfolio themes）
_KEYWORD_TO_THEMES: dict[str, list[str]] = {
    "確定申告": ["tax", "freelance", "side_hustle"],
    "クラウド会計": ["accounting", "freelance", "side_hustle"],
    "副業": ["side_hustle", "freelance"],
    "在宅ワーク": ["side_hustle", "productivity"],
    "新NISA": ["nisa", "investment_savings"],
    "iDeCo": ["nisa", "investment_savings", "tax"],
    "投資": ["investment_savings"],
    "証券口座": ["investment_savings", "nisa"],
    "フリーランス": ["freelance", "side_hustle"],
    "AI": ["ai_tools", "side_hustle"],
    "ブログ": ["blog", "side_hustle"],
    "節税": ["tax", "accounting"],
    "節約": ["lifestyle", "investment_savings"],
    "クレジットカード": ["lifestyle", "investment_savings"],
    "保険": ["lifestyle"],
    "起業": ["startup", "freelance"],
    "転職": ["side_hustle", "freelance"],
}


# ── pytrends でトレンドキーワード取得 ───────────────────────────

def _fetch_trends_pytrends(limit: int = 10) -> list[str]:
    """
    Google Trends（pytrends）で日本のリアルタイムトレンドを取得する。
    realtime_trending_searches → trending_searches の順で試みる。
    pytrends 未インストール・ネットワークエラー時は空リストを返す。
    """
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl="ja-JP", tz=540, timeout=(10, 30))

        # 方法1: リアルタイムトレンド（新しい API）
        try:
            df = pt.realtime_trending_searches(pn="JP")
            if df is not None and not df.empty:
                keywords = df["title"].tolist()[:limit]
                print(f"[TrendHunter] pytrends(realtime) 取得: {keywords[:3]}...")
                return keywords
        except Exception:
            pass

        # 方法2: デイリートレンド（旧 API フォールバック）
        df = pt.trending_searches(pn="japan")
        keywords = df[0].tolist()[:limit]
        print(f"[TrendHunter] pytrends(daily) 取得: {keywords[:3]}...")
        return keywords

    except ImportError:
        print("[TrendHunter] pytrends 未インストール → 季節キーワードで代替")
        return []
    except Exception as e:
        print(f"[TrendHunter] pytrends 失敗: {e} → 季節キーワードで代替")
        return []


def _get_trend_keywords() -> list[str]:
    """
    pytrends → 月別季節キーワードの優先順でトレンドキーワードを取得する。
    """
    keywords = _fetch_trends_pytrends()
    if not keywords:
        month = datetime.now().month
        keywords = _MONTHLY_KEYWORDS.get(month, ["副業", "節約", "投資"])
        print(f"[TrendHunter] 月別キーワード使用 ({month}月): {keywords}")
    return keywords


# ── Gemini でプログラム候補を生成・スコアリング ───────────────────

def _evaluate_and_suggest(keywords: list[str], existing_names: set[str]) -> list[dict]:
    """
    Gemini にトレンドキーワードを渡し、アフィリエイトプログラム候補を提案させる。
    既存プログラム名は除外する。

    Returns:
        [
          {
            "name": "freee人事労務",
            "company": "freee株式会社",
            "category": "accounting",
            "themes": ["freelance", "side_hustle"],
            "reward": "推定1,000〜3,000円/件",
            "description": "...",
            "hashtags": ["#フリーランス", "#給与計算"],
            "affiliate_url": "",
            "sns_score": 8,
            "reason": "副業フリーランス増加でニーズ急増"
          },
          ...
        ]
    """
    try:
        from gemini_client import generate as gemini_generate
    except ImportError:
        print("[TrendHunter] gemini_client インポート失敗")
        return []

    existing_list = "\n".join(f"- {n}" for n in sorted(existing_names)) or "（なし）"
    keywords_str  = "、".join(keywords[:10])
    month         = datetime.now().month
    year          = datetime.now().year

    prompt = f"""あなたはアフィリエイトマーケターです。
現在のトレンドキーワードと季節に合わせて、SNS投稿×アフィリエイトに適したプログラムを提案してください。

【現在の日時】{year}年{month}月
【トレンドキーワード】{keywords_str}

【既にポートフォリオに登録済み（重複不要）】
{existing_list}

【多ジャンル化の要件（特定ジャンルに偏らないこと）】
以下のジャンルからバランスよく選んでください（1ジャンルにつき最大3件まで）:
- 金融・副業: クラウド会計、証券口座、クレジットカード、副業ツール
- VOD・エンタメ: 動画配信サービス（Netflix、U-NEXT、Hulu等）、電子書籍
- 美容・健康: スキンケア、サプリメント、フィットネス、ダイエット食品
- ガジェット・家電: スマホアクセサリー、モバイルバッテリー、スマートホーム
- 生活サービス: 食材宅配、家事代行、引越し、ウォーターサーバー
- 学習・スキルアップ: オンライン英会話、プログラミングスクール、資格通信

【共通要件】
- A8.net / afb / バリューコマース など日本の主要 ASP で扱われている実在のプログラム
- 報酬単価が高い（1件500円以上）か、CVRが高い（認知度が高いブランド）もの
- SNSで自然に紹介でき、ターゲット（20〜40代・一人暮らし）に刺さる案件

以下の JSON 配列を返してください（コードブロック不要、配列だけ）:
[
  {{
    "name": "サービス名（正式名称）",
    "company": "運営会社名",
    "category": "accounting|investment|insurance|tools|lifestyle|beauty|entertainment|gadget|education|food|other のどれか",
    "themes": ["side_hustle", "tax", "freelance", "nisa", "investment_savings", "productivity", "ai_tools", "blog", "startup", "lifestyle", "beauty", "entertainment", "gadget", "education" から複数],
    "reward": "推定報酬（例: 1,500円/件）",
    "description": "30文字以内の説明",
    "hashtags": ["#タグ1", "#タグ2", "#タグ3"],
    "affiliate_url": "",
    "sns_score": 0から10の整数（SNS投稿で成果が出やすい度合い）,
    "reason": "スコアの根拠（1文）"
  }}
]

{MAX_NEW_PROGRAMS}件まで提案してください。ジャンルが多様になるよう意識し、sns_score が高い順で返してください。"""

    raw = gemini_generate(prompt, use_cache=False)
    if not raw:
        print("[TrendHunter] Gemini からレスポンスなし")
        return []

    # JSON 配列を抽出
    m = re.search(r'\[[\s\S]*\]', raw)
    if not m:
        print(f"[TrendHunter] JSON パース失敗:\n{raw[:200]}")
        return []

    try:
        candidates = json.loads(m.group())
    except json.JSONDecodeError as e:
        print(f"[TrendHunter] JSON デコード失敗: {e}")
        return []

    # 既存名と重複するものを除外
    result = []
    for c in candidates:
        if not isinstance(c, dict):
            continue
        name = c.get("name", "").strip()
        if not name or name in existing_names:
            print(f"[TrendHunter] スキップ（既存 or 名前なし）: {name}")
            continue
        score = c.get("sns_score", 0)
        if score < SNS_SCORE_THRESHOLD:
            print(f"[TrendHunter] スキップ（スコア低い {score}）: {name}")
            continue
        result.append(c)

    return result[:MAX_NEW_PROGRAMS]


# ── ポートフォリオへの追加 ────────────────────────────────────────

def _add_to_portfolio(candidate: dict, dry_run: bool) -> dict:
    """
    candidate を program_portfolio.json に追加する。
    affiliate_url が空なら status="candidate"、あれば status="active"。

    Returns: 追加されたポートフォリオエントリ
    """
    data = json.loads(PORTFOLIO_PATH.read_text(encoding="utf-8"))
    programs = data.get("programs", [])
    existing_ids = {p["id"] for p in programs}

    # ID 生成: 英小文字+数字 のスラッグ + 年
    raw_id = re.sub(r'[^\w]', '_', candidate["name"].lower())
    raw_id = re.sub(r'_+', '_', raw_id).strip('_')
    year   = datetime.now().year
    new_id = f"{raw_id[:20]}_{year}"
    # 重複した場合はサフィックスを付ける
    if new_id in existing_ids:
        new_id = f"{new_id}_b"

    affiliate_url = candidate.get("affiliate_url", "").strip()
    status        = "active" if affiliate_url else "candidate"

    entry = {
        "id":            new_id,
        "name":          candidate["name"],
        "company":       candidate.get("company", ""),
        "category":      candidate.get("category", "other"),
        "themes":        candidate.get("themes", ["side_hustle"]),
        "reward":        candidate.get("reward", ""),
        "epc":           0.0,
        "confirm_rate":  "不明",
        "affiliate_url": affiliate_url,
        "description":   candidate.get("description", ""),
        "priority":      1,          # 新規は最高優先度
        "status":        status,
        "last_used_at":  None,
        "added_by":      "weekly_trend_hunter",
        "sns_score":     candidate.get("sns_score", 0),
        "added_at":      datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    if dry_run:
        print(f"  [DryRun] ポートフォリオ追加予定: {entry['name']} (status={status}, score={entry['sns_score']})")
        return entry

    programs.append(entry)
    data["programs"] = programs
    PORTFOLIO_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  [Portfolio] 追加: {entry['name']} (id={new_id}, status={status})")
    return entry


# ── キャッシュ・履歴への投入 ──────────────────────────────────────

def _add_to_cache(portfolio_entry: dict, hashtags: list[str], dry_run: bool) -> None:
    """
    affiliate_url が設定済みの案件をキャッシュ・履歴に投入する。
    posted_count=0 なので weighted_choice で最高重みになる。
    """
    affiliate_url = portfolio_entry.get("affiliate_url", "").strip()
    if not affiliate_url:
        print(f"  [Cache] スキップ（URL未設定）: {portfolio_entry['name']}")
        return

    entry = {
        "ins_id":        portfolio_entry["id"],
        "name":          portfolio_entry["name"],
        "company":       portfolio_entry.get("company", ""),
        "reward":        portfolio_entry.get("reward", ""),
        "affiliate_url": affiliate_url,
        "hatena_url":    "",
        "hashtags":      hashtags,
        "posted_count":  0,
        "description":   portfolio_entry.get("description", ""),
        "added_at":      portfolio_entry.get("added_at", ""),
    }

    if dry_run:
        print(f"  [DryRun] キャッシュ追加予定: {entry['name']}")
        return

    for path, label in [(CACHE_PATH, "キュー"), (HISTORY_PATH, "履歴")]:
        try:
            records = json.loads(path.read_text(encoding="utf-8"))
            ids = {r.get("ins_id") for r in records}
            if entry["ins_id"] not in ids:
                records.append(entry)
                path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"  [Cache] {label}追加: {entry['name']}")
            else:
                print(f"  [Cache] {label}スキップ（既存）: {entry['name']}")
        except Exception as e:
            print(f"  [Cache] {label}書き込み失敗: {e}")


# ── Amazon / Rakuten トレンドキーワードリサーチ ─────────────────

def _research_amazon_keywords(trend_keywords: list[str], dry_run: bool) -> list[dict]:
    """
    Gemini に今週のAmazon商品キーワードを5件生成させ、
    AMAZON_KEYWORDS_PATH に保存する（dry_run=False 時のみ書き込み）。
    """
    try:
        from gemini_client import generate as gemini_generate
    except ImportError:
        print("[TrendHunter/Amazon] gemini_client インポート失敗")
        return []

    now          = datetime.now()
    year         = now.year
    month        = now.month
    keywords_str = "、".join(trend_keywords[:10])
    week_of      = now.strftime("%G-W%V")

    prompt = f"""{year}年{month}月のトレンドキーワード: {keywords_str}

これらを踏まえて、アフィリエイト収益を上げやすいAmazon商品検索キーワードを5件提案してください。

【条件】
- 価格帯: 2,000〜20,000円
- ターゲット: 20〜40代男性
- SNSでバズりやすい商品カテゴリ

以下のJSON配列を返してください（コードブロック不要、配列だけ）:
[{{"keyword": "商品検索キーワード", "title": "40文字以内の投稿タイトル", "reason": "30文字以内の選定理由"}}]"""

    try:
        raw = gemini_generate(prompt, use_cache=False)
    except Exception as e:
        print(f"[TrendHunter/Amazon] Gemini 呼び出し失敗: {e}")
        return []

    if not raw:
        print("[TrendHunter/Amazon] Gemini からレスポンスなし")
        return []

    m = re.search(r'\[[\s\S]*\]', raw)
    if not m:
        print(f"[TrendHunter/Amazon] JSON パース失敗:\n{raw[:200]}")
        return []

    try:
        items = json.loads(m.group())
    except json.JSONDecodeError as e:
        print(f"[TrendHunter/Amazon] JSON デコード失敗: {e}")
        return []

    # keyword キーがあるもののみ最大5件
    keywords = [item for item in items if isinstance(item, dict) and "keyword" in item][:5]

    if not dry_run:
        payload = {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "week_of":      week_of,
            "keywords":     keywords,
        }
        AMAZON_KEYWORDS_PATH.parent.mkdir(parents=True, exist_ok=True)
        AMAZON_KEYWORDS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[TrendHunter/Amazon] {len(keywords)}件生成")
    return keywords


def _research_rakuten_keywords(trend_keywords: list[str], dry_run: bool) -> list[dict]:
    """
    Gemini に今週の楽天商品キーワードを5件生成させ、
    RAKUTEN_KEYWORDS_PATH に保存する（dry_run=False 時のみ書き込み）。
    """
    try:
        from gemini_client import generate as gemini_generate
    except ImportError:
        print("[TrendHunter/Rakuten] gemini_client インポート失敗")
        return []

    now          = datetime.now()
    year         = now.year
    month        = now.month
    keywords_str = "、".join(trend_keywords[:10])
    week_of      = now.strftime("%G-W%V")

    prompt = f"""{year}年{month}月のトレンドキーワード: {keywords_str}

これらを踏まえて、楽天市場での商品紹介に適した検索キーワードを5件提案してください。

【条件】
- テーマ: 一人暮らし・副業・節約・生活改善
- 楽天市場で実際に購入できる商品であること

以下のJSON配列を返してください（コードブロック不要、配列だけ）:
[{{"keyword": "楽天検索キーワード", "category": "食品/家電/日用品/ファッション/美容/スポーツのどれか", "reason": "30文字以内の選定理由"}}]"""

    try:
        raw = gemini_generate(prompt, use_cache=False)
    except Exception as e:
        print(f"[TrendHunter/Rakuten] Gemini 呼び出し失敗: {e}")
        return []

    if not raw:
        print("[TrendHunter/Rakuten] Gemini からレスポンスなし")
        return []

    m = re.search(r'\[[\s\S]*\]', raw)
    if not m:
        print(f"[TrendHunter/Rakuten] JSON パース失敗:\n{raw[:200]}")
        return []

    try:
        items = json.loads(m.group())
    except json.JSONDecodeError as e:
        print(f"[TrendHunter/Rakuten] JSON デコード失敗: {e}")
        return []

    # keyword キーがあるもののみ最大5件
    search_terms = [item for item in items if isinstance(item, dict) and "keyword" in item][:5]

    if not dry_run:
        payload = {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "week_of":      week_of,
            "search_terms": search_terms,
        }
        RAKUTEN_KEYWORDS_PATH.parent.mkdir(parents=True, exist_ok=True)
        RAKUTEN_KEYWORDS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[TrendHunter/Rakuten] {len(search_terms)}件生成")
    return search_terms


# ── メイン ──────────────────────────────────────────────────────

def run(dry_run: bool = False) -> None:
    print(f"\n{'='*60}")
    print(f"[TrendHunter] 開始 {datetime.now().strftime('%Y-%m-%d %H:%M')}  dry_run={dry_run}")
    print('='*60)

    # 既存ポートフォリオの名前セットを取得
    portfolio_data  = json.loads(PORTFOLIO_PATH.read_text(encoding="utf-8"))
    existing_names  = {p["name"] for p in portfolio_data.get("programs", [])}
    print(f"[TrendHunter] 既存ポートフォリオ: {len(existing_names)}件")

    # 現在の履歴件数を確認（母数が少ない場合は積極追加モード）
    try:
        current_history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        current_cache_count = len(current_history)
    except Exception:
        current_cache_count = 0
    print(f"[TrendHunter] 現在のA8履歴件数: {current_cache_count}/{MIN_CACHE_TARGET}件")

    # トレンドキーワード取得
    keywords = _get_trend_keywords()
    print(f"[TrendHunter] 使用キーワード: {keywords[:5]}")

    # Gemini で候補生成（履歴が少ない場合は積極モードのキーワードも追加）
    search_keywords = keywords
    if current_cache_count < MIN_CACHE_TARGET:
        # 多ジャンルカバーのための補完キーワードを追加
        supplement = ["VOD 動画配信", "美容 スキンケア", "ガジェット 家電", "食材宅配 生活", "英会話 学習"]
        search_keywords = list(set(keywords + supplement))
        print(f"[TrendHunter] 履歴不足（{current_cache_count}件）→ 補完キーワード追加: {supplement}")

    candidates = _evaluate_and_suggest(search_keywords, existing_names)
    if not candidates:
        print("[TrendHunter] 候補なし → 終了")
        return

    print(f"\n[TrendHunter] 候補 {len(candidates)}件:\n")
    added_count = 0
    for c in candidates:
        score = c.get("sns_score", 0)
        print(f"  [{score}/10] {c.get('name','?')} — {c.get('reason','')}")

        portfolio_entry = _add_to_portfolio(c, dry_run)

        hashtags = c.get("hashtags", ["#副業"])
        _add_to_cache(portfolio_entry, hashtags, dry_run)
        added_count += 1

    print(f"\n[TrendHunter] 完了: {added_count}件追加{'（DryRun）' if dry_run else ''}")
    print("  ※ affiliate_url が空の案件は status=candidate です。")
    print("  ※ A8.net で承認後、portfolio.json の affiliate_url と status を更新してください。")

    # Amazon & Rakuten トレンドキーワードリサーチ
    print(f"\n[TrendHunter] Amazon商品キーワードリサーチ中...")
    amazon_kws = _research_amazon_keywords(keywords, dry_run)
    print(f"\n[TrendHunter] Rakuten商品キーワードリサーチ中...")
    rakuten_kws = _research_rakuten_keywords(keywords, dry_run)
    print(f"[TrendHunter] Amazon {len(amazon_kws)}件 / Rakuten {len(rakuten_kws)}件 キーワード更新")

    print('='*60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="書き込みなしで確認のみ")
    args = parser.parse_args()

    # .env 読み込み
    env_path = ROOT_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    run(dry_run=args.dry_run)
