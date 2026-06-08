"""
Amazon URL 生成テスト

urllib.parse を使ったURL構築が正しく動作するかを確認する。
- クエリパラメータが壊れていないか
- 商品IDベース・検索キーワードベースの両方を出力して目視確認

使い方:
    python3.11 x_automation/test_amazon_url.py
"""
import os
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

BASE_DIR = Path(__file__).parent
ROOT_DIR = BASE_DIR.parent

# .env 読み込み
env_path = ROOT_DIR / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

ASSOCIATE_TAG = os.getenv("AMAZON_ASSOCIATE_TAG", "smartearn22-22")


def make_dp_url(asin: str, tag: str = ASSOCIATE_TAG) -> str:
    """ASIN ベースの商品直リンクURLを安全に生成"""
    query = urlencode({"tag": tag})
    return urlunparse(("https", "www.amazon.co.jp", f"/dp/{asin}", "", query, ""))


def make_search_url(keyword: str, tag: str = ASSOCIATE_TAG) -> str:
    """検索キーワードベースのURLを安全に生成"""
    query = urlencode({"k": keyword, "tag": tag})
    return urlunparse(("https", "www.amazon.co.jp", "/s", "", query, ""))


def add_sub1(url: str, platform: str = "x") -> str:
    """sub1 パラメータを urllib.parse で安全に追加"""
    from urllib.parse import parse_qsl
    from datetime import datetime
    sub = f"{platform}_{datetime.now().strftime('%Y%m%d')}"
    parsed = urlparse(url)
    params = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
              if k != "sub1"]
    params.append(("sub1", sub))
    return urlunparse(parsed._replace(query=urlencode(params)))


def validate_url(url: str) -> dict:
    """URLが正しく構築されているか検証"""
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    issues = []

    if not parsed.scheme.startswith("http"):
        issues.append("スキームが不正")
    if "amazon.co.jp" not in parsed.netloc:
        issues.append("ホストが不正")
    if "tag" not in params:
        issues.append("tag パラメータなし")
    # クエリ文字列が二重エンコードされていないか確認（%25 が含まれる場合は異常）
    if "%25" in parsed.query:
        issues.append("二重エンコード検出")
    # スペースが残っていないか
    if " " in url:
        issues.append("スペースが残っている")

    return {
        "url":    url,
        "scheme": parsed.scheme,
        "host":   parsed.netloc,
        "path":   parsed.path,
        "params": params,
        "ok":     len(issues) == 0,
        "issues": issues,
    }


def print_result(label: str, result: dict):
    status = "✅ OK" if result["ok"] else "❌ NG"
    print(f"\n{status} [{label}]")
    print(f"  URL   : {result['url']}")
    print(f"  path  : {result['path']}")
    print(f"  params: {result['params']}")
    if result["issues"]:
        for issue in result["issues"]:
            print(f"  ⚠️  {issue}")


def main():
    print("=" * 65)
    print("Amazon URL 構築テスト")
    print(f"アソシエイトタグ: {ASSOCIATE_TAG}")
    print("=" * 65)

    # ── 1. 商品IDベース ──────────────────────────────────────────
    test_cases_dp = [
        ("通常ASIN",               "B09W2PNZQQ"),
        ("AnkerモバイルバッテリーASIN", "B08N5WRWNW"),
    ]

    print("\n■ 商品IDベースのリンク (/dp/ASIN)")
    for label, asin in test_cases_dp:
        url    = make_dp_url(asin)
        result = validate_url(url)
        print_result(label, result)

    # ── 2. 検索キーワードベース ──────────────────────────────────
    test_cases_search = [
        ("日本語キーワード（スペースあり）", "ワイヤレスイヤホン ノイズキャンセリング"),
        ("英数字+記号",                     "Anker USB-C 65W GaN"),
        ("日本語のみ",                       "電気圧力鍋"),
        ("特殊文字（&を含む）",              "USB & HDMI ハブ"),
    ]

    print("\n■ 検索キーワードベースのリンク (/s?k=...)")
    for label, kw in test_cases_search:
        url    = make_search_url(kw)
        result = validate_url(url)
        print_result(label, result)

    # ── 3. sub1 パラメータ追加（tracking.py の動作確認）────────
    print("\n■ sub1 パラメータ追加（tracking.py 互換確認）")
    base_dp     = make_dp_url("B09W2PNZQQ")
    base_search = make_search_url("ワイヤレスイヤホン")

    for label, base in [("商品IDベース + sub1", base_dp), ("検索URLベース + sub1", base_search)]:
        url    = add_sub1(base)
        result = validate_url(url)
        # sub1 が付いているか確認
        if "sub1" not in result["params"]:
            result["ok"] = False
            result["issues"].append("sub1 パラメータが付与されていない")
        print_result(label, result)

    # ── 4. tracking.py の実際の関数で確認 ───────────────────────
    print("\n■ tracking.py の add_amazon_sub() 動作確認")
    sys.path.insert(0, str(ROOT_DIR / "money_agent"))
    try:
        from tracking import add_amazon_sub
        base   = make_dp_url("B08N5WRWNW")
        result = validate_url(add_amazon_sub(base, "x"))
        if "sub1" not in result["params"]:
            result["ok"] = False
            result["issues"].append("sub1 パラメータが付与されていない")
        print_result("add_amazon_sub('x')", result)
    except Exception as e:
        print(f"  ❌ tracking.py のインポート失敗: {e}")

    print("\n" + "=" * 65)
    print("テスト完了")
    print("=" * 65)


if __name__ == "__main__":
    main()
