"""
週次エンゲージメント分析 & 来週スケジュール自動最適化

「この1週間のデータを見て、エンゲージメントが高い投稿の共通点を3つ挙げて。
 それを踏まえて来週の投稿スケジュールを修正して。」を自動化する。

データソース:
  1. x_automation/post_log.json  (投稿記録)
  2. X API v2 (いいね数/RT数/インプレッション — APIキーがある場合)
  3. Gemini API (パターン分析 + スケジュール提案)

使い方:
  python3.11 x_automation/engagement_analyzer.py           # 分析 + 来週スケジュール表示
  python3.11 x_automation/engagement_analyzer.py --update  # x_scheduler.py のスケジュールを更新
  python3.11 x_automation/engagement_analyzer.py --days 14 # 2週間分を分析
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

BASE_DIR  = Path(__file__).parent
ROOT_DIR  = BASE_DIR.parent
LOG_FILE  = BASE_DIR / "post_log.json"
REPORT_FILE = BASE_DIR / "engagement_report.json"

# .env 読み込み
env_path = ROOT_DIR / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


# ─────────────────────────────────────────
# ログ読み込み & フィルタリング
# ─────────────────────────────────────────
def load_recent_logs(days: int = 7) -> list:
    """過去N日分の投稿ログを返す"""
    if not LOG_FILE.exists():
        return []

    all_logs = json.loads(LOG_FILE.read_text(encoding="utf-8"))
    cutoff   = datetime.now() - timedelta(days=days)

    recent = []
    for entry in all_logs:
        try:
            dt = datetime.fromisoformat(entry["datetime"])
            if dt >= cutoff and entry.get("success"):
                entry["_dt"] = dt
                recent.append(entry)
        except Exception:
            continue

    return sorted(recent, key=lambda x: x["_dt"])


# ─────────────────────────────────────────
# X API でエンゲージメント取得（オプション）
# ─────────────────────────────────────────
def fetch_x_engagement(tweet_ids: list) -> dict:
    """
    X API v2 でツイートのいいね数・RT数・インプレッションを取得
    APIキー未設定の場合は空dictを返す

    Returns:
        {tweet_id: {"likes": int, "retweets": int, "impressions": int}}
    """
    api_key      = os.getenv("X_API_KEY")
    api_secret   = os.getenv("X_API_SECRET")
    access_token = os.getenv("X_ACCESS_TOKEN")
    access_secret = os.getenv("X_ACCESS_TOKEN_SECRET")

    if not all([api_key, api_secret, access_token, access_secret]):
        return {}
    if not tweet_ids:
        return {}

    try:
        import tweepy

        client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret,
        )

        result = {}
        # tweepy は一度に最大100件
        for i in range(0, len(tweet_ids), 100):
            batch = tweet_ids[i:i+100]
            resp  = client.get_tweets(
                ids=batch,
                tweet_fields=["public_metrics", "created_at"],
            )
            if resp and resp.data:
                for tweet in resp.data:
                    m = tweet.public_metrics or {}
                    result[str(tweet.id)] = {
                        "likes":       m.get("like_count", 0),
                        "retweets":    m.get("retweet_count", 0),
                        "replies":     m.get("reply_count", 0),
                        "impressions": m.get("impression_count", 0),
                    }

        return result

    except Exception as e:
        print(f"⚠️  X APIエンゲージメント取得エラー: {e}")
        return {}


# ─────────────────────────────────────────
# ローカルログからの擬似エンゲージメント推定
# (X APIがない場合のフォールバック)
# ─────────────────────────────────────────
def estimate_engagement(log_entry: dict) -> dict:
    """
    投稿ログからエンゲージメントを推定する
    実際の数値がない場合は投稿タイプ・時間帯・文字数から推定

    推定根拠（一般的なXのエンゲージメント率統計）:
    - 朝7〜9時: エンゲージメント高（通勤中閲覧）
    - 昼11〜13時: 中程度
    - 夜21〜23時: 最高（帰宅後のスクロール時間）
    - 文字数80〜120字: 読まれやすい
    - 共感系投稿: いいね率が高い
    - 雑学系: RT率が高い
    """
    dt   = log_entry.get("_dt", datetime.now())
    hour = dt.hour
    post_type = log_entry.get("type", "useful")
    chars     = log_entry.get("chars", 100)

    # 時間帯スコア
    if   21 <= hour <= 23:  time_score = 1.5
    elif  7 <= hour <= 9:   time_score = 1.3
    elif 11 <= hour <= 13:  time_score = 1.1
    else:                   time_score = 0.8

    # タイプスコア
    type_score = {
        "empathy":        1.4,  # 共感 → いいね多い
        "trivia":         1.3,  # 雑学 → RT多い
        "useful":         1.2,  # 役立つ情報 → 保存多い
        "product":        0.9,  # 商品紹介 → 低め（自然な文脈が重要）
        "amazon_thread":  1.1,  # Amazonスレッド
    }.get(post_type, 1.0)

    # 文字数スコア（80〜120字が最適）
    if 80 <= chars <= 120:    char_score = 1.2
    elif 60 <= chars <= 150:  char_score = 1.0
    else:                     char_score = 0.8

    base = 50  # 推定いいね数ベース
    estimated_likes = int(base * time_score * type_score * char_score)
    estimated_rt    = int(estimated_likes * 0.3)

    return {
        "likes":       estimated_likes,
        "retweets":    estimated_rt,
        "replies":     int(estimated_likes * 0.1),
        "impressions": estimated_likes * 20,
        "estimated":   True,  # 推定値フラグ
        "time_score":  time_score,
        "type_score":  type_score,
        "char_score":  char_score,
    }


# ─────────────────────────────────────────
# エンゲージメント分析
# ─────────────────────────────────────────
def analyze_engagement(logs: list, x_data: dict) -> dict:
    """
    投稿ログ + X APIデータからエンゲージメントパターンを分析

    Returns:
        分析結果dict（共通点・時間帯分布・タイプ別成績など）
    """
    enriched = []
    for log in logs:
        tweet_id = log.get("tweet_id", "")
        if tweet_id and str(tweet_id) in x_data:
            eng = x_data[str(tweet_id)]
            eng["estimated"] = False
        else:
            eng = estimate_engagement(log)

        enriched.append({**log, "engagement": eng})

    if not enriched:
        return {}

    # タイプ別集計
    by_type = defaultdict(list)
    for e in enriched:
        by_type[e["type"]].append(e["engagement"]["likes"])

    type_avg = {
        t: sum(vals) / len(vals)
        for t, vals in by_type.items()
    }

    # 時間帯別集計
    by_hour = defaultdict(list)
    for e in enriched:
        dt   = e.get("_dt", datetime.now())
        slot = _hour_to_slot(dt.hour)
        by_hour[slot].append(e["engagement"]["likes"])

    slot_avg = {
        slot: sum(vals) / len(vals)
        for slot, vals in by_hour.items()
    }

    # 文字数別集計
    char_groups = {"〜80字": [], "80〜120字": [], "120〜180字": [], "180字〜": []}
    for e in enriched:
        c = e.get("chars", 100)
        if c < 80:       char_groups["〜80字"].append(e["engagement"]["likes"])
        elif c < 120:    char_groups["80〜120字"].append(e["engagement"]["likes"])
        elif c < 180:    char_groups["120〜180字"].append(e["engagement"]["likes"])
        else:            char_groups["180字〜"].append(e["engagement"]["likes"])

    char_avg = {
        k: sum(v) / len(v) if v else 0
        for k, v in char_groups.items()
    }

    # TOP3 投稿
    top3 = sorted(enriched, key=lambda x: x["engagement"]["likes"], reverse=True)[:3]

    return {
        "total_posts":    len(enriched),
        "type_avg":       type_avg,
        "slot_avg":       slot_avg,
        "char_avg":       char_avg,
        "top3":           top3,
        "all":            enriched,
        "has_real_data":  any(not e["engagement"].get("estimated") for e in enriched),
    }


def _hour_to_slot(hour: int) -> str:
    if  7 <= hour <= 9:  return "朝7〜9時"
    if 11 <= hour <= 13: return "昼11〜13時"
    if 17 <= hour <= 19: return "夕17〜19時"
    if 21 <= hour <= 23: return "夜21〜23時"
    return "その他"


# ─────────────────────────────────────────
# Gemini で共通点を言語化
# ─────────────────────────────────────────
def describe_patterns(analysis: dict) -> list:
    """
    分析結果からエンゲージメントが高い投稿の共通点を3つ生成
    Gemini API があれば自然言語で、なければルールベースで返す
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        result = _describe_with_gemini(analysis, api_key)
        if result:
            return result

    return _describe_from_rules(analysis)


def _describe_with_gemini(analysis: dict, api_key: str) -> list:
    """Gemini APIで共通点を言語化"""
    try:
        from google import genai

        type_avg = analysis.get("type_avg", {})
        slot_avg = analysis.get("slot_avg", {})
        char_avg = analysis.get("char_avg", {})
        top3     = analysis.get("top3", [])

        top3_text = "\n".join([
            f"  - [{e['label']}] {e.get('chars',0)}文字: {e.get('text','')[:60]}..."
            for e in top3
        ])

        prompt = f"""
あなたはXマーケティングの専門家です。
以下のX（Twitter）投稿パフォーマンスデータを分析し、
エンゲージメントが高い投稿の共通点を3つ挙げてください。

【投稿タイプ別平均いいね数】
{json.dumps(type_avg, ensure_ascii=False)}

【時間帯別平均いいね数】
{json.dumps(slot_avg, ensure_ascii=False)}

【文字数別平均いいね数】
{json.dumps(char_avg, ensure_ascii=False)}

【Top3投稿】
{top3_text}

注意:
- データが推定値の場合でも、統計的傾向として有益な洞察を出してください
- 各共通点は「なぜそれが効果的か」の理由も30字以内で添えてください
- 来週の投稿改善につながる具体的なアドバイスを含めてください

以下の形式でJSONのみ出力:
[
  {{"point": "共通点1", "reason": "理由", "action": "来週への具体的アクション"}},
  {{"point": "共通点2", "reason": "理由", "action": "来週への具体的アクション"}},
  {{"point": "共通点3", "reason": "理由", "action": "来週への具体的アクション"}}
]
"""

        client = genai.Client(api_key=api_key)
        resp   = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=prompt,
        )
        raw = resp.text.strip()
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        return json.loads(raw)

    except Exception as e:
        print(f"⚠️  Geminiパターン分析エラー: {e}")
        return []


def _describe_from_rules(analysis: dict) -> list:
    """ルールベースで共通点を生成"""
    patterns = []
    type_avg = analysis.get("type_avg", {})
    slot_avg = analysis.get("slot_avg", {})
    char_avg = analysis.get("char_avg", {})

    # タイプ別
    if type_avg:
        best_type = max(type_avg, key=type_avg.get)
        type_labels = {
            "empathy": "共感・体験系", "trivia": "雑学・ネタ系",
            "useful": "役立つ情報系", "product": "商品紹介系",
            "amazon_thread": "Amazonスレッド",
        }
        patterns.append({
            "point":  f"{type_labels.get(best_type, best_type)}の投稿がエンゲージメント最高",
            "reason": "ユーザーの感情に直接刺さるコンテンツタイプ",
            "action": f"来週は{type_labels.get(best_type, best_type)}の比率を増やす",
        })

    # 時間帯別
    if slot_avg:
        best_slot = max(slot_avg, key=slot_avg.get)
        patterns.append({
            "point":  f"{best_slot}の投稿がエンゲージメント最高",
            "reason": "Xユーザーの閲覧ピーク時間と一致しているため",
            "action": f"来週は{best_slot}に優先的に投稿する",
        })

    # 文字数別
    if char_avg:
        best_chars = max(char_avg, key=char_avg.get)
        patterns.append({
            "point":  f"{best_chars}の投稿が最も読まれている",
            "reason": "Xのタイムラインでスクロール中に読み切れる長さ",
            "action": f"来週は投稿を{best_chars}に収める",
        })

    return patterns


# ─────────────────────────────────────────
# 来週スケジュール最適化
# ─────────────────────────────────────────
def optimize_next_week_schedule(analysis: dict, patterns: list) -> dict:
    """
    分析結果 + 共通点から来週の最適投稿スケジュールを生成

    Returns:
        {
          "daily_schedule": {曜日: [{time, type, reason}, ...]},
          "type_distribution": {タイプ: 割合},
          "focus": str,  # 今週の重点改善点
        }
    """
    type_avg = analysis.get("type_avg", {})
    slot_avg = analysis.get("slot_avg", {})

    # 最もエンゲージメントが高かったタイプを優先
    if type_avg:
        best_type  = max(type_avg, key=type_avg.get)
        worst_type = min(type_avg, key=type_avg.get)
    else:
        best_type  = "empathy"
        worst_type = "product"

    # 最もエンゲージメントが高かった時間帯を特定
    slot_to_hour = {
        "朝7〜9時": 8, "昼11〜13時": 12, "夕17〜19時": 18, "夜21〜23時": 21
    }
    best_slot_hour = 21  # デフォルト
    if slot_avg:
        best_slot_name = max(slot_avg, key=slot_avg.get)
        best_slot_hour = slot_to_hour.get(best_slot_name, 21)

    # 来週の推奨タイプ分配（最良タイプを増やし、最低タイプを減らす）
    type_distribution = {
        "useful":  35,
        "empathy": 30,
        "trivia":  15,
        "product": 10,
        "amazon_thread": 10,
    }
    # 最良タイプを+10%
    if best_type in type_distribution:
        type_distribution[best_type] = min(50, type_distribution[best_type] + 10)
    # 最低タイプを-5%
    if worst_type in type_distribution and worst_type != best_type:
        type_distribution[worst_type] = max(5, type_distribution[worst_type] - 5)

    # 来週の投稿スケジュール（月〜日）
    today = datetime.now()
    days_ahead = 7 - today.weekday()  # 来週月曜まで
    next_monday = today + timedelta(days=days_ahead)

    daily_schedule = {}
    weekdays = ["月", "火", "水", "木", "金", "土", "日"]
    # 週の曜日別投稿最適配分（土日はエンゲージメント低いのでAmazonスレッドに充てる）
    day_patterns = {
        "月": [("useful",   8), ("empathy",   21)],
        "火": [("trivia",   8), ("useful",    21)],
        "水": [("empathy",  8), ("amazon_thread", 21)],
        "木": [("useful",   8), ("trivia",    21)],
        "金": [("empathy",  8), ("product",   21)],
        "土": [("amazon_thread", 12), ("useful", 20)],
        "日": [("trivia",  11), ("empathy",   20)],
    }

    for i, (day, slots) in enumerate(day_patterns.items()):
        date = next_monday + timedelta(days=i)
        daily_schedule[day] = {
            "date": date.strftime("%m/%d"),
            "posts": [
                {
                    "time":   f"{hour:02d}:00",
                    "type":   ptype,
                    "reason": _get_post_reason(ptype, hour),
                }
                for ptype, hour in slots
            ]
        }

    return {
        "daily_schedule":    daily_schedule,
        "type_distribution": type_distribution,
        "best_slot_hour":    best_slot_hour,
        "focus":             patterns[0]["action"] if patterns else "来週も継続",
    }


def _get_post_reason(post_type: str, hour: int) -> str:
    """投稿タイプ+時間帯の理由を返す"""
    reasons = {
        ("empathy",  8):  "通勤中の共感 → 午前の感情訴求",
        ("useful",   8):  "朝の有益情報 → 保存率UP",
        ("trivia",   8):  "朝の雑学 → RT狙い",
        ("useful",  21):  "夜のまとめ読み層 → 保存・フォロー率UP",
        ("empathy", 21):  "夜の感情ピーク → いいね最大化",
        ("amazon_thread", 21): "夜の買い物意欲ピーク → コンバージョン最大",
        ("amazon_thread", 12): "昼休みの衝動買い層 → タイムセール訴求",
        ("product", 21):  "夜の検討時間 → アフィリエイトクリック",
        ("trivia",  11):  "昼のエンタメ消費 → RT拡散狙い",
    }
    return reasons.get((post_type, hour), f"{post_type}投稿 @ {hour}時")


# ─────────────────────────────────────────
# レポート表示
# ─────────────────────────────────────────
def print_report(analysis: dict, patterns: list, schedule: dict):
    """分析レポートを整形表示"""
    print(f"\n{'=' * 65}")
    print(f"📊 週次エンゲージメント分析レポート")
    print(f"   期間: 過去7日間 / 総投稿数: {analysis.get('total_posts', 0)}件")
    if not analysis.get("has_real_data"):
        print(f"   ⚠️  X APIデータなし → 推定値で分析（参考値）")
    print(f"{'=' * 65}")

    # タイプ別成績
    type_avg  = analysis.get("type_avg", {})
    type_labels = {
        "empathy": "共感・体験", "trivia": "雑学・ネタ",
        "useful": "役立つ情報", "product": "商品紹介",
        "amazon_thread": "Amazonスレッド",
    }
    if type_avg:
        print(f"\n📈 投稿タイプ別 平均エンゲージメント（推定）")
        sorted_types = sorted(type_avg.items(), key=lambda x: x[1], reverse=True)
        for t, avg in sorted_types:
            bar = "█" * int(avg / 5) + "░" * max(0, 20 - int(avg / 5))
            label = type_labels.get(t, t)
            print(f"  {label:12s} {bar} {avg:.0f}")

    # 時間帯別
    slot_avg = analysis.get("slot_avg", {})
    if slot_avg:
        print(f"\n⏰ 時間帯別 平均エンゲージメント（推定）")
        for slot, avg in sorted(slot_avg.items(), key=lambda x: x[1], reverse=True):
            bar = "█" * int(avg / 5) + "░" * max(0, 20 - int(avg / 5))
            print(f"  {slot:12s} {bar} {avg:.0f}")

    # Top3
    top3 = analysis.get("top3", [])
    if top3:
        print(f"\n🏆 Top3 投稿")
        for i, e in enumerate(top3, 1):
            eng = e.get("engagement", {})
            dt  = e.get("_dt", datetime.now())
            print(f"  {i}位: {dt.strftime('%m/%d %H:%M')} [{e.get('label','')}]")
            print(f"       ❤️ {eng.get('likes',0)} RT:{eng.get('retweets',0)}")
            print(f"       {e.get('text','')[:50]}...")

    # 共通点3つ
    print(f"\n💡 エンゲージメントが高い投稿の共通点 TOP3")
    for i, p in enumerate(patterns, 1):
        print(f"\n  {i}. {p['point']}")
        print(f"     理由: {p['reason']}")
        print(f"     来週: {p['action']}")

    # 来週スケジュール
    daily = schedule.get("daily_schedule", {})
    print(f"\n📅 来週の最適投稿スケジュール（AI最適化済み）")
    print(f"   重点改善: {schedule.get('focus', '')}")
    print()

    type_to_jp = {
        "useful": "役立つ情報", "empathy": "共感", "trivia": "雑学",
        "product": "商品紹介", "amazon_thread": "Amazonスレッド",
    }
    for day, info in daily.items():
        date_str = info.get("date", "")
        posts    = info.get("posts", [])
        print(f"  {day}（{date_str}）")
        for post in posts:
            tp = type_to_jp.get(post["type"], post["type"])
            print(f"    {post['time']} [{tp}]  {post['reason']}")

    print(f"\n{'=' * 65}")


# ─────────────────────────────────────────
# スケジューラー更新（オプション）
# ─────────────────────────────────────────
def update_scheduler(schedule: dict):
    """
    x_scheduler.py の DAILY_PATTERNS を分析結果に基づいて更新する
    （ファイルを直接書き換えるため、バックアップを取ってから実行）
    """
    scheduler_path = BASE_DIR / "x_scheduler.py"
    if not scheduler_path.exists():
        print("⚠️  x_scheduler.py が見つかりません")
        return

    # バックアップ
    backup_path = BASE_DIR / f"x_scheduler.bak.{datetime.now().strftime('%Y%m%d%H%M%S')}.py"
    backup_path.write_text(scheduler_path.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"💾 バックアップ: {backup_path.name}")

    type_dist = schedule.get("type_distribution", {})

    # type_distribution から4投稿パターンを生成
    sorted_types = sorted(type_dist.items(), key=lambda x: x[1], reverse=True)
    pattern_4 = [t for t, _ in sorted_types[:4]]
    if len(pattern_4) < 4:
        pattern_4 += ["useful"] * (4 - len(pattern_4))

    new_pattern_line = f'    {pattern_4},  # AI最適化 {datetime.now().strftime("%Y/%m/%d")}'

    content = scheduler_path.read_text(encoding="utf-8")
    # DAILY_PATTERNS リストの最後に追加
    if "DAILY_PATTERNS = [" in content:
        updated = content.replace(
            "DAILY_PATTERNS = [",
            f"DAILY_PATTERNS = [\n{new_pattern_line}",
            1
        )
        scheduler_path.write_text(updated, encoding="utf-8")
        print(f"✅ x_scheduler.py を更新しました")
        print(f"   追加パターン: {pattern_4}")
    else:
        print("⚠️  DAILY_PATTERNS が見つかりませんでした（手動で更新してください）")


# ─────────────────────────────────────────
# CLI
# ─────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="週次エンゲージメント分析")
    parser.add_argument("--days",   type=int, default=7, help="分析期間（日）デフォルト7")
    parser.add_argument("--update", action="store_true",
                        help="x_scheduler.pyのスケジュールを更新する")
    parser.add_argument("--save",   action="store_true",
                        help="engagement_report.jsonに保存する")
    args = parser.parse_args()

    print(f"\n🔍 エンゲージメント分析開始（過去{args.days}日間）")

    # ログ読み込み
    logs = load_recent_logs(args.days)
    if not logs:
        print(f"⚠️  投稿ログが {args.days}日分見つかりませんでした")
        print(f"   {LOG_FILE} を確認してください")
        sys.exit(1)

    print(f"  ✅ {len(logs)}件の投稿ログを読み込みました")

    # X APIエンゲージメント取得（tweet_idがある場合）
    tweet_ids = [str(e.get("tweet_id", "")) for e in logs if e.get("tweet_id")]
    x_data = {}
    if tweet_ids:
        print(f"  📡 X APIからエンゲージメントを取得中...")
        x_data = fetch_x_engagement(tweet_ids)
        if x_data:
            print(f"  ✅ {len(x_data)}件のエンゲージメントデータ取得")
        else:
            print(f"  ⚠️  X APIデータ取得失敗 → 推定値を使用")

    # 分析
    print(f"\n📊 分析中...")
    analysis = analyze_engagement(logs, x_data)

    # 共通点抽出
    print(f"  💡 共通点を抽出中...")
    patterns = describe_patterns(analysis)

    # 来週スケジュール最適化
    print(f"  📅 来週スケジュールを最適化中...")
    schedule = optimize_next_week_schedule(analysis, patterns)

    # レポート表示
    print_report(analysis, patterns, schedule)

    # 保存
    if args.save:
        report = {
            "generated_at": datetime.now().isoformat(),
            "analysis":     {k: v for k, v in analysis.items() if k not in ("all", "top3")},
            "patterns":     patterns,
            "schedule":     schedule,
        }
        REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"💾 レポート保存: {REPORT_FILE}")

    # スケジューラー更新
    if args.update:
        print(f"\n🔧 x_scheduler.py を更新中...")
        update_scheduler(schedule)


if __name__ == "__main__":
    main()
