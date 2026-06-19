"""
トレンドデータ収集モジュール

requests + HTMLParserでAIニュース・副業トレンド・人気商品・
アフィリエイト案件を収集し、dynamic_keywords.json に保存する。
（OpenCrawlはPostgreSQL+Kafka必須のため、軽量実装を採用）

収集ソース:
  - Gigazine             : 最新AIニュース
  - はてなブックマーク    : 話題キーワード（テクノロジー/副業）
  - 楽天ランキング        : 人気商品カテゴリ
  - ITmedia AI+          : AI業界トレンド
"""
import os
import sys
import json
import asyncio
import re
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

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

DYNAMIC_KW_FILE = Path(__file__).parent / "data" / "dynamic_keywords.json"


async def _fetch_with_requests(url: str) -> str:
    """requestsでページを取得してテキストを返す（opencrawlのフォールバック）"""
    import requests
    from html.parser import HTMLParser

    class _StripTags(HTMLParser):
        def __init__(self):
            super().__init__()
            self._texts = []
            self._skip = False
        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style"):
                self._skip = True
        def handle_endtag(self, tag):
            if tag in ("script", "style"):
                self._skip = False
        def handle_data(self, data):
            if not self._skip:
                stripped = data.strip()
                if stripped:
                    self._texts.append(stripped)
        def get_text(self):
            return "\n".join(self._texts)

    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1)"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.encoding = resp.apparent_encoding
        parser = _StripTags()
        parser.feed(resp.text)
        return parser.get_text()[:8000]
    except Exception as e:
        print(f"  fetch失敗 {url}: {e}")
        return ""


# ============================================================
# Geminiでキーワード抽出
# ============================================================

def _extract_keywords_with_gemini(raw_text: str, category: str, n: int = 5, _retry: int = 0) -> list[dict]:
    """生テキストからSEOキーワードをGeminiで抽出"""
    try:
        from google import genai
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        prompt = f"""以下のウェブコンテンツから、日本語のSEOキーワードを{n}個抽出してください。
カテゴリ: {category}
条件:
- 検索意図が「commercial（商品比較・購入検討）」または「how-to（使い方・やり方）」のもの優先
- 2026年現在のトレンドに合ったもの
- 検索ボリュームが見込めるもの（具体的なツール名・サービス名を含む）

JSON配列で出力（他の文字列不要）:
[
  {{"kw": "キーワード文字列", "intent": "commercial|how-to|informational", "volume": "high|mid|low"}},
  ...
]

コンテンツ:
{raw_text[:4000]}
"""
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        text = response.text.strip()
        # JSONブロックを抽出
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        err = str(e)
        # レート制限は待機してリトライ（最大2回）
        if "429" in err and _retry < 2:
            import time
            wait = 15 * (_retry + 1)
            print(f"  Geminiレート制限、{wait}秒待機してリトライ...")
            time.sleep(wait)
            return _extract_keywords_with_gemini(raw_text, category, n, _retry + 1)
        print(f"  Geminiキーワード抽出エラー: {err[:120]}")
    return []


# ============================================================
# 収集ソース定義
# ============================================================

CRAWL_SOURCES = [
    {
        "url": "https://gigazine.net/",
        "category": "ai_tools",
        "label": "Gigazineニュース",
    },
    {
        "url": "https://b.hatena.ne.jp/hotentry/it",
        "category": "ai_tools",
        "label": "はてブ IT",
    },
    {
        "url": "https://b.hatena.ne.jp/hotentry/economics",
        "category": "side_hustle",
        "label": "はてブ 副業・経済",
    },
    {
        "url": "https://ranking.rakuten.co.jp/",
        "category": "investment_savings",
        "label": "楽天ランキング",
    },
    {
        "url": "https://www.itmedia.co.jp/aiplus/",
        "category": "ai_tools",
        "label": "ITmedia AI+",
    },
]


# ============================================================
# メイン収集処理
# ============================================================

async def collect_async() -> dict:
    """非同期でトレンドを収集し dynamic_keywords.json を更新する"""
    collected: dict[str, list] = {
        "ai_tools": [],
        "side_hustle": [],
        "investment_savings": [],
        "productivity": [],
    }

    for source in CRAWL_SOURCES:
        print(f"\n📡 収集中: {source['label']} ({source['url'][:50]}...)")
        try:
            text = await _fetch_with_requests(source["url"])

            if not text:
                print("  テキスト取得失敗")
                continue

            kws = _extract_keywords_with_gemini(text, source["label"], n=5)
            cat = source["category"]
            collected[cat].extend(kws)
            print(f"  取得キーワード: {[k['kw'] for k in kws]}")

        except Exception as e:
            print(f"  エラー: {e}")

    # 既存データとマージ（重複排除）
    existing = _load_dynamic()
    for cat, kws in collected.items():
        existing_kws = {k["kw"] for k in existing.get(cat, [])}
        for kw in kws:
            if kw.get("kw") and kw["kw"] not in existing_kws:
                existing.setdefault(cat, []).append(kw)
                existing_kws.add(kw["kw"])

    existing["updated_at"] = datetime.now().isoformat()
    _save_dynamic(existing)

    total = sum(len(v) for k, v in existing.items() if k != "updated_at")
    print(f"\n✅ 収集完了: 総キーワード数 {total}件 → {DYNAMIC_KW_FILE}")
    return existing


def collect():
    """同期ラッパー"""
    return asyncio.run(collect_async())


# ============================================================
# dynamic_keywords.json 読み書き
# ============================================================

def _load_dynamic() -> dict:
    if DYNAMIC_KW_FILE.exists():
        try:
            with open(DYNAMIC_KW_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_dynamic(data: dict):
    with open(DYNAMIC_KW_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_dynamic_keywords(category: str) -> list[dict]:
    """収集済み動的キーワードをカテゴリ別に取得"""
    data = _load_dynamic()
    return data.get(category, [])


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "collect"

    if cmd == "collect":
        result = collect()
        print("\n📊 カテゴリ別件数:")
        for k, v in result.items():
            if k != "updated_at":
                print(f"  {k}: {len(v)}件")

    elif cmd == "show":
        data = _load_dynamic()
        for cat, kws in data.items():
            if cat == "updated_at":
                continue
            print(f"\n[{cat}]")
            for kw in kws[:5]:
                print(f"  {kw.get('kw')} ({kw.get('intent')}/{kw.get('volume')})")
