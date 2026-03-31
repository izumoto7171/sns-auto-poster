"""
バズってる商品紹介 YouTube Shorts 自動探索
動画の手法: 「バズってる動画を探す → その商品をコピー」

使い方:
  python3 viral_shorts_finder.py                        # デフォルトキーワードで検索
  python3 viral_shorts_finder.py -k "掃除グッズ"        # キーワード指定
  python3 viral_shorts_finder.py -k "キッチン 便利" -n 10  # 10件取得
  python3 viral_shorts_finder.py --open                  # 結果をブラウザで確認
"""
import subprocess
import json
import argparse
import sys
import os
import webbrowser
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent

# ─────────────────────────────────────────────
# 商品系バズりキーワード一覧（動画の手法に沿う）
# ─────────────────────────────────────────────
DEFAULT_KEYWORDS = [
    "便利グッズ 紹介",
    "キッチン 便利アイテム",
    "掃除グッズ おすすめ",
    "収納グッズ 100均",
    "文房具 おすすめ",
    "ガジェット レビュー",
    "美容グッズ おすすめ",
    "日本 お菓子 紹介",
    "アニメ グッズ",
    "スキンケア おすすめ",
]

# ─────────────────────────────────────────────
# yt-dlp で YouTube Shorts を検索
# ─────────────────────────────────────────────
def search_youtube_shorts(keyword: str, max_results: int = 10) -> list:
    """
    YouTube Shorts をキーワード検索して動画情報リストを返す。
    25秒以内・再生数順でフィルタリング。
    """
    print(f"\n🔍 検索中: 「{keyword}」 (最大{max_results}件)")

    # yt-dlp で YouTube Shorts 検索
    search_query = f"ytsearch{max_results * 3}:{keyword} shorts"

    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--dump-json",
        "--no-download",
        "--flat-playlist",
        "--no-warnings",
        search_query,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            print(f"⚠️  検索エラー: {result.stderr[:200]}")
            return []

        videos = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                videos.append(data)
            except json.JSONDecodeError:
                continue

        return videos

    except subprocess.TimeoutExpired:
        print("⚠️  タイムアウト（30秒）")
        return []
    except Exception as e:
        print(f"⚠️  エラー: {e}")
        return []


def get_video_details(video_id: str) -> dict:
    """個別動画の詳細情報（長さ・再生数）を取得"""
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--dump-json",
        "--no-download",
        "--no-warnings",
        f"https://www.youtube.com/shorts/{video_id}",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            return json.loads(result.stdout.strip())
    except Exception:
        pass
    return {}


# ─────────────────────────────────────────────
# フィルタリング（25秒以内・再生数が多い順）
# ─────────────────────────────────────────────
def filter_shorts(videos: list, max_duration: int = 25) -> list:
    """25秒以内の動画のみ残して再生数降順で返す"""
    filtered = []
    for v in videos:
        duration = v.get("duration")
        view_count = v.get("view_count") or 0
        url = v.get("url") or v.get("webpage_url") or ""
        video_id = v.get("id") or v.get("display_id") or ""

        # duration が None の場合はとりあえず含める（後でチェック）
        if duration is not None and duration > max_duration:
            continue

        # Shorts URL に変換
        if video_id and "shorts" not in url:
            url = f"https://www.youtube.com/shorts/{video_id}"

        filtered.append({
            "id":          video_id,
            "title":       v.get("title", ""),
            "url":         url,
            "view_count":  view_count,
            "duration":    duration,
            "channel":     v.get("channel") or v.get("uploader", ""),
            "thumbnail":   v.get("thumbnail", ""),
            "description": (v.get("description") or "")[:100],
        })

    # 再生数降順
    filtered.sort(key=lambda x: x["view_count"], reverse=True)
    return filtered


# ─────────────────────────────────────────────
# 結果表示
# ─────────────────────────────────────────────
def print_results(videos: list, keyword: str):
    print(f"\n{'='*60}")
    print(f"🔥 バズってる商品紹介 Shorts: 「{keyword}」")
    print(f"{'='*60}")

    if not videos:
        print("  結果なし")
        return

    for i, v in enumerate(videos, 1):
        view_str = f"{v['view_count']:,}" if v['view_count'] else "不明"
        dur_str  = f"{v['duration']}秒" if v['duration'] else "不明"
        print(f"\n  [{i}] {v['title'][:45]}")
        print(f"      再生数: {view_str}  |  長さ: {dur_str}")
        print(f"      CH: {v['channel'][:30]}")
        print(f"      URL: {v['url']}")


# ─────────────────────────────────────────────
# 結果をJSON保存
# ─────────────────────────────────────────────
def save_results(results: dict) -> str:
    out_dir = BASE_DIR / "output" / "viral_shorts"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"viral_{ts}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n💾 結果保存: {out_path}")
    return str(out_path)


# ─────────────────────────────────────────────
# HTML レポート生成（ブラウザで確認用）
# ─────────────────────────────────────────────
def generate_html_report(results: dict) -> str:
    """見やすいHTMLレポートを生成してブラウザで開く"""
    out_dir = BASE_DIR / "output" / "viral_shorts"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "report.html"

    cards = ""
    for keyword, videos in results.items():
        if not videos:
            continue
        cards += f'<h2 class="kw">🔍 {keyword}</h2><div class="grid">'
        for v in videos:
            view_str = f"{v['view_count']:,}" if v['view_count'] else "?"
            dur_str  = f"{v['duration']}秒" if v['duration'] else "?"
            thumb    = v.get("thumbnail", "")
            title    = v["title"][:40]
            ch       = v["channel"][:25]
            url      = v["url"]
            cards += f"""
            <a class="card" href="{url}" target="_blank">
              {('<img src="' + thumb + '" onerror="this.style.display=none">') if thumb else '<div class="no-img">📱</div>'}
              <div class="info">
                <div class="title">{title}</div>
                <div class="meta">👁 {view_str}  ⏱ {dur_str}</div>
                <div class="ch">📺 {ch}</div>
              </div>
            </a>"""
        cards += "</div>"

    now = datetime.now().strftime("%Y/%m/%d %H:%M")
    html = f"""<!DOCTYPE html>
<html lang="ja"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>バズり Shorts レポート</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,sans-serif;background:#f5f5f5;padding:20px}}
h1{{font-size:22px;margin-bottom:20px;color:#111}}
.kw{{font-size:18px;margin:28px 0 12px;color:#333;border-left:4px solid #ff4444;padding-left:10px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:14px;margin-bottom:10px}}
.card{{display:flex;flex-direction:column;background:#fff;border-radius:10px;overflow:hidden;text-decoration:none;color:#333;box-shadow:0 2px 8px rgba(0,0,0,.08);transition:transform .2s}}
.card:hover{{transform:translateY(-3px)}}
.card img{{width:100%;aspect-ratio:9/16;object-fit:cover;background:#eee}}
.no-img{{width:100%;aspect-ratio:9/16;display:flex;align-items:center;justify-content:center;font-size:40px;background:#f0f0f0}}
.info{{padding:10px}}
.title{{font-size:13px;font-weight:600;margin-bottom:6px;line-height:1.4}}
.meta{{font-size:12px;color:#e47911;margin-bottom:4px}}
.ch{{font-size:11px;color:#888}}
footer{{text-align:center;color:#bbb;font-size:12px;margin-top:30px}}
</style></head><body>
<h1>🔥 バズってる商品紹介 Shorts レポート</h1>
{cards}
<footer>生成: {now}</footer>
</body></html>"""

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return str(out_path)


# ─────────────────────────────────────────────
# メイン
# ─────────────────────────────────────────────
def run(keywords: list, max_results: int = 8, open_browser: bool = False) -> dict:
    all_results = {}

    for keyword in keywords:
        raw = search_youtube_shorts(keyword, max_results=max_results * 3)
        filtered = filter_shorts(raw, max_duration=25)[:max_results]
        all_results[keyword] = filtered
        print_results(filtered, keyword)

    save_results(all_results)

    if open_browser:
        report_path = generate_html_report(all_results)
        print(f"🌐 ブラウザで開く: {report_path}")
        webbrowser.open(f"file://{report_path}")

    return all_results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="バズってる商品紹介 Shorts を探す")
    parser.add_argument("--keyword", "-k", default=None,
                        help="検索キーワード（省略時はランダム3キーワード）")
    parser.add_argument("--num", "-n", type=int, default=5,
                        help="キーワードあたりの取得件数（デフォルト: 5）")
    parser.add_argument("--open", action="store_true",
                        help="結果をHTMLレポートとしてブラウザで開く")
    parser.add_argument("--all", action="store_true",
                        help="全キーワードで検索")
    args = parser.parse_args()

    import random
    if args.keyword:
        keywords = [args.keyword]
    elif args.all:
        keywords = DEFAULT_KEYWORDS
    else:
        keywords = random.sample(DEFAULT_KEYWORDS, 3)

    run(keywords, max_results=args.num, open_browser=args.open)
