"""
ランキング・比較記事 自動生成エンジン

【機能】
特定ジャンル（VOD・英会話・プログラミングスクール等）のアフィリエイト
プログラムを横並びで比較するSEOランキング記事をGeminiで自動生成し、
はてなブログに AtomPub API で投稿する。

【対応ジャンル】
  vod / eikaiwa / programming / credit_card / fx / insurance /転職 / 電力

【実行方法】
  # ジャンル指定して記事生成・投稿
  python3 money_agent/ranking_article_generator.py vod
  python3 money_agent/ranking_article_generator.py eikaiwa dry-run

  # 全ジャンルを順番に生成（1実行1ジャンル、ローテーション）
  python3 money_agent/ranking_article_generator.py auto

  # 生成済みジャンルの確認
  python3 money_agent/ranking_article_generator.py status
"""

import os
import sys
import json
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
HATENA_ID      = os.environ.get("HATENA_ID", "")
HATENA_BLOG_ID = os.environ.get("HATENA_BLOG_ID", "")
HATENA_API_KEY = os.environ.get("HATENA_API_KEY", "")
GENERATED_FILE = Path(__file__).parent / "ranking_generated.json"

# ============================================================
# ジャンル定義（SEOキーワード・対象サービス・アフィリエイト情報）
# ============================================================
RANKING_GENRES = {
    "vod": {
        "label": "VOD（動画配信）",
        "seo_keyword": "動画配信サービス おすすめ 比較",
        "target_audience": "映画・ドラマ・アニメ好きの20〜40代",
        "services": [
            {"name": "Netflix", "price": "990円〜/月", "trial": "なし", "content": "洋画・海外ドラマ豊富・オリジナル作品多数", "best_for": "海外ドラマ好き"},
            {"name": "Amazonプライムビデオ", "price": "600円/月", "trial": "30日間無料", "content": "映画・ドラマ・アニメ・Amazonオリジナル", "best_for": "コスパ重視"},
            {"name": "Disney+", "price": "990円/月", "trial": "なし", "content": "ディズニー・マーベル・スターウォーズ・ピクサー", "best_for": "家族・マーベルファン"},
            {"name": "U-NEXT", "price": "2,189円/月", "trial": "31日間無料", "content": "最大級13万本・雑誌読み放題・ポイント付与", "best_for": "幅広いジャンルを見たい人"},
            {"name": "Hulu", "price": "1,026円/月", "trial": "2週間無料", "content": "海外ドラマ・日本テレビ番組・アニメ", "best_for": "日本のテレビ番組をよく見る人"},
        ],
        "affiliate_note": "各サービスの無料トライアルへの申込を推奨",
        "tags": ["VOD", "動画配信", "Netflix", "アマゾンプライム", "U-NEXT"],
    },
    "eikaiwa": {
        "label": "オンライン英会話",
        "seo_keyword": "オンライン英会話 おすすめ 比較",
        "target_audience": "英語を学びたい社会人・学生",
        "services": [
            {"name": "ネイティブキャンプ", "price": "6,480円/月（月額・回数無制限）", "trial": "7日間無料体験", "content": "24時間365日・ネイティブ講師・グループレッスンあり", "best_for": "毎日レッスンしたい人"},
            {"name": "DMM英会話", "price": "6,480円〜/月（1回/日）", "trial": "無料体験1回", "content": "世界130カ国・10,000人以上の講師・初心者向け", "best_for": "費用を抑えたい初心者"},
            {"name": "レアジョブ英会話", "price": "6,380円〜/月（週2回）", "trial": "2回無料", "content": "フィリピン人講師・ビジネス英語強め・TOEIC対策", "best_for": "ビジネス英語を鍛えたい"},
            {"name": "Cambly", "price": "8,900円〜/月", "trial": "15分無料", "content": "ネイティブ限定・いつでも即接続・アメリカ英語", "best_for": "ネイティブとだけ話したい"},
            {"name": "スタディサプリENGLISH", "price": "3,278円/月", "trial": "7日間無料", "content": "AIコーチング・シャドーイング・ビジネス/日常コース", "best_for": "隙間時間に勉強したい"},
        ],
        "affiliate_note": "各スクールの無料体験申込・入会を推奨",
        "tags": ["オンライン英会話", "英会話", "語学学習", "英語"],
    },
    "programming": {
        "label": "プログラミングスクール",
        "seo_keyword": "プログラミングスクール おすすめ 比較",
        "target_audience": "IT転職・副業を目指す20〜30代",
        "services": [
            {"name": "テックキャンプ", "price": "547,800円（短期集中）", "trial": "無料体験あり", "content": "3ヶ月で転職保証・マンツーマンサポート・転職成功率98%", "best_for": "最短でエンジニアになりたい人"},
            {"name": "RUNTEQ", "price": "437,800円", "trial": "無料説明会あり", "content": "Webエンジニア特化・1,000時間カリキュラム・就職サポート", "best_for": "本格的にWebエンジニアを目指す人"},
            {"name": "ポテパンキャンプ", "price": "238,000円", "trial": "無料相談あり", "content": "実践的なRuby/Rails・転職サポート・週2回以上受講可", "best_for": "コストを抑えたい人"},
            {"name": "ProgateOne", "price": "月額2,480円〜", "trial": "7日間無料", "content": "AI学習・Progate基礎→実践・ポートフォリオ支援", "best_for": "独学から一歩進めたい人"},
            {"name": "忍者CODE", "price": "68,000円〜（Web制作）", "trial": "無料相談あり", "content": "副業特化・Web制作/動画/SNS運用・実績を作りながら稼ぐ", "best_for": "副業で月5万円稼ぎたい人"},
        ],
        "affiliate_note": "無料体験・説明会申込を推奨（高単価8,000〜50,000円/件）",
        "tags": ["プログラミングスクール", "エンジニア転職", "IT転職", "プログラミング"],
    },
    "credit_card": {
        "label": "クレジットカード",
        "seo_keyword": "クレジットカード おすすめ 比較 2026",
        "target_audience": "ポイ活・節約に興味ある20〜50代",
        "services": [
            {"name": "楽天カード", "price": "年会費無料", "trial": "新規入会ポイントあり", "content": "ポイント還元率1%・楽天市場で3倍・楽天経済圏と相性最高", "best_for": "楽天ユーザー"},
            {"name": "三井住友カード(NL)", "price": "年会費無料", "trial": "ナンバーレス・即日発行", "content": "コンビニ・マック最大7%還元・セキュリティ高い", "best_for": "コンビニをよく使う人"},
            {"name": "PayPayカード", "price": "年会費無料", "trial": "新規特典あり", "content": "PayPayチャージ可・Yahoo!ショッピング3倍・最大1.5%還元", "best_for": "PayPayユーザー"},
            {"name": "JCBカードW", "price": "年会費無料（39歳以下申込）", "trial": "オンライン申込OK", "content": "スタバ・Amazon最大10.5%還元・国際ブランドJCB", "best_for": "スタバ・Amazon好き39歳以下"},
            {"name": "エポスカード", "price": "年会費無料", "trial": "マルイで即日発行", "content": "海外旅行保険自動付帯・全国10,000店舗で優待", "best_for": "海外旅行によく行く人"},
        ],
        "affiliate_note": "カード発行・利用で高単価（3,000〜10,000円/件）",
        "tags": ["クレジットカード", "ポイ活", "節約", "キャッシュレス"],
    },
    "fx": {
        "label": "FX・証券口座",
        "seo_keyword": "FX 口座開設 おすすめ 比較",
        "target_audience": "投資・副業に興味ある20〜40代",
        "services": [
            {"name": "GMOクリック証券", "price": "口座開設無料", "trial": "デモトレードあり", "content": "国内FX口座数No.1・取引ツール充実・スプレッド狭い", "best_for": "FX初心者〜中級者"},
            {"name": "DMM FX", "price": "口座開設無料", "trial": "初心者サポート充実", "content": "スプレッド業界最狭水準・取引ツールシンプル・サポート24時間", "best_for": "シンプルに始めたい初心者"},
            {"name": "SBI FXトレード", "price": "口座開設無料", "trial": "1通貨から取引可能", "content": "1通貨単位で取引・少額から始められる・低スプレッド", "best_for": "少額でリスクを抑えたい"},
            {"name": "外為どっとコム", "price": "口座開設無料", "trial": "情報ツール充実", "content": "情報コンテンツ豊富・セミナー多数・FXメディア運営", "best_for": "学びながら始めたい"},
            {"name": "楽天証券", "price": "口座開設無料", "trial": "楽天との連携あり", "content": "株・FX・投信を一元管理・楽天ポイント投資可能", "best_for": "楽天ユーザー・株もやりたい"},
        ],
        "affiliate_note": "口座開設・入金で高単価（5,000〜30,000円/件）",
        "tags": ["FX", "証券口座", "投資", "副業投資"],
    },
    "denryoku": {
        "label": "電力会社乗り換え",
        "seo_keyword": "電力会社 乗り換え おすすめ 比較",
        "target_audience": "電気代を節約したい家庭",
        "services": [
            {"name": "楽天でんき", "price": "基本料金0円", "trial": "切り替え簡単", "content": "基本料金無料・楽天ポイント貯まる・Web手続き完結", "best_for": "楽天ユーザー"},
            {"name": "エルピオでんき", "price": "市場連動型", "trial": "切り替えサポートあり", "content": "市場価格連動・安い時間帯に節約・シンプル料金", "best_for": "日中外出が多い家庭"},
            {"name": "auでんき", "price": "au/UQ mobile割引あり", "trial": "切り替え手続きWeb", "content": "auユーザー向け割引・Pontaポイント還元・安心サポート", "best_for": "auスマホユーザー"},
            {"name": "東京ガスの電気", "price": "ガスとセット割", "trial": "見積もり無料", "content": "ガス・電気まとめて割引・東京電力エリア限定", "best_for": "東京ガスユーザー"},
            {"name": "シン・エナジー", "price": "従量電灯より安い", "trial": "切り替え無料", "content": "時間帯別料金・太陽光発電の余剰電力買取・SDGs", "best_for": "環境意識が高い家庭"},
        ],
        "affiliate_note": "切り替え申込で2,000〜5,000円/件",
        "tags": ["電力会社", "電気代節約", "乗り換え", "節電"],
    },
}

# ============================================================
# 既生成管理
# ============================================================
def load_generated() -> dict:
    if GENERATED_FILE.exists():
        return json.loads(GENERATED_FILE.read_text(encoding="utf-8"))
    return {}

def save_generated(data: dict):
    GENERATED_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def get_next_genre():
    """最も長く生成されていないジャンルを返す（ローテーション）"""
    generated = load_generated()
    genres = list(RANKING_GENRES.keys())
    # 未生成のジャンルを優先
    for g in genres:
        if g not in generated:
            return g
    # 全生成済みなら最も古いものを選択
    return min(generated.keys(), key=lambda k: generated[k].get("generated_at", ""))


# ============================================================
# Gemini API でランキング記事を生成
# ============================================================
def generate_ranking_article(genre_key: str):
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("[Gemini] GEMINI_API_KEY未設定")
        return None

    genre_info = RANKING_GENRES.get(genre_key)
    if not genre_info:
        print(f"[Ranking] 未対応ジャンル: {genre_key}")
        return None

    year = datetime.now().year
    services_text = "\n".join([
        f"- {s['name']}: {s['price']} / 特徴: {s['content']} / おすすめ: {s['best_for']}"
        for s in genre_info["services"]
    ])

    try:
        from google import genai
        client = genai.Client(api_key=api_key)

        prompt = f"""あなたはアフィリエイトブログの専門ライターです。
以下の情報をもとに、SEO最適化されたランキング記事を作成してください。

【ジャンル】{genre_info["label"]}
【SEOキーワード】{genre_info["seo_keyword"]}
【対象読者】{genre_info["target_audience"]}
【比較サービス】
{services_text}

【記事要件】
- タイトル: 「【{year}年最新】{genre_info["seo_keyword"]}｜徹底比較ランキングTOP5」
- 文字数: 3000〜4000文字
- 構成:
  1. 導入（読者の悩みに共感・この記事で解決できることを明示）
  2. 選び方のポイント（3〜4点）
  3. ランキングTOP5（各サービスを詳しく解説 + メリット/デメリット）
  4. 比較表（サービス名・価格・無料期間・特徴を一覧）
  5. こんな人にはこれがおすすめ（3パターン）
  6. まとめ + CTA（「まずは無料で試してみよう」）
- 見出しはMarkdown（## / ###）
- 自然な口調で信頼感のある文章
- 比較表はMarkdownテーブル形式

以下のJSON形式で返してください（コードブロック不要）:
{{
  "title": "記事タイトル",
  "keyword": "SEOメインキーワード",
  "category": "エンタメ/教育/副業/投資/節約のいずれか",
  "tags": {json.dumps(genre_info["tags"], ensure_ascii=False)},
  "body": "本文（Markdown形式・3000文字以上）"
}}"""

        resp = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt,
        )
        text = resp.text.strip()
        if text.startswith("```"):
            text = text.split("```", 2)[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.rsplit("```", 1)[0]

        article = json.loads(text.strip())
        article["genre_key"] = genre_key
        article["generated_at"] = datetime.now().isoformat()
        return article

    except Exception as e:
        print(f"[Gemini] ランキング記事生成エラー ({genre_key}): {e}")
        return None


import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent))
from hatena_atomapi import post as _hatena_post

def post_to_hatena(article: dict, draft: bool = False):
    return _hatena_post(article, draft=draft)


# ============================================================
# メイン
# ============================================================
def run(genre_key: str, dry_run: bool = False):
    print(f"\n=== ランキング記事生成: {genre_key} {'[DRY RUN]' if dry_run else ''} ===")

    if genre_key not in RANKING_GENRES:
        print(f"対応ジャンル: {list(RANKING_GENRES.keys())}")
        return

    article = generate_ranking_article(genre_key)
    if not article:
        return

    print(f"タイトル: {article['title']}")
    print(f"文字数: {len(article.get('body', ''))}文字")
    print(f"タグ: {article.get('tags', [])}")

    if dry_run:
        print(f"\n本文冒頭:\n{article.get('body', '')[:500]}")
        return

    url = post_to_hatena(article)
    if url:
        # 生成済みに記録
        generated = load_generated()
        generated[genre_key] = {
            "title": article["title"],
            "url": url,
            "generated_at": article["generated_at"],
        }
        save_generated(generated)
        print(f"記録: {genre_key} → {url}")


def run_auto(dry_run: bool = False):
    """次のジャンルを自動選択して実行"""
    genre_key = get_next_genre()
    if not genre_key:
        print("全ジャンル生成済み")
        return
    print(f"[Auto] 次のジャンル: {genre_key}")
    run(genre_key, dry_run=dry_run)


def show_status():
    generated = load_generated()
    print(f"\n=== ランキング記事 生成状況 ===")
    for genre_key, info in generated.items():
        label = RANKING_GENRES.get(genre_key, {}).get("label", genre_key)
        print(f"  ✅ {label}: {info.get('generated_at', '')[:10]} → {info.get('url', '')}")
    pending = [k for k in RANKING_GENRES if k not in generated]
    for genre_key in pending:
        label = RANKING_GENRES[genre_key]["label"]
        print(f"  ⏳ {label}: 未生成")


if __name__ == "__main__":
    args = sys.argv[1:]
    dry_run = "dry-run" in args or "dry_run" in args
    # argsからdry-runを除いたもの
    genre_args = [a for a in args if a not in ("dry-run", "dry_run")]

    if not genre_args or genre_args[0] == "status":
        show_status()
    elif genre_args[0] == "auto":
        run_auto(dry_run=dry_run)
    elif genre_args[0] in RANKING_GENRES:
        run(genre_args[0], dry_run=dry_run)
    else:
        print(f"使い方: python3 ranking_article_generator.py [ジャンル|auto|status] [dry-run]")
        print(f"対応ジャンル: {list(RANKING_GENRES.keys())}")
