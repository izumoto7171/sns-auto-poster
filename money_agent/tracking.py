"""
アフィリエイトリンク計測ユーティリティ

各プラットフォームごとに計測パラメータを付与して
「どこからのクリックで成約したか」をA8/Amazon/はてなのレポートで追跡する。

使い方:
    from tracking import tag_affiliate_link, add_utm

    # A8リンク → a8sid付与（A8レポートのサブID列で確認可能）
    url = tag_affiliate_link("https://px.a8.net/svt/ejp?a8mat=XXX", "hatena")
    # → https://px.a8.net/svt/ejp?a8mat=XXX&a8sid=htn_20260411

    # Amazonリンク → sub1付与
    url = tag_affiliate_link("https://www.amazon.co.jp/dp/B0C4?tag=xxx-22", "x")
    # → https://www.amazon.co.jp/dp/B0C4?tag=xxx-22&sub1=x_20260411

    # ブログURLをSNSに貼る → UTM付与
    url = add_utm("https://smart-earn-life.hateblo.jp/entry/xxx", "x")
    # → https://smart-earn-life.hateblo.jp/entry/xxx?utm_source=x&utm_medium=social&utm_campaign=20260411_auto
"""
from datetime import datetime


# プラットフォーム識別子（A8レポートで見やすい短縮形）
PLATFORM_IDS = {
    "x":       "x",
    "twitter": "x",
    "bluesky": "bsky",
    "hatena":  "htn",
    "note":    "note",
    "rakuten": "rktn",
    "amazon":  "amzn",
}


def _today() -> str:
    return datetime.now().strftime("%Y%m%d")


def add_a8_sid(url: str, platform: str) -> str:
    """
    A8.netトラッキングURLにa8sidサブIDを付与する。
    A8管理画面のレポート → 「サブID」列で platform_YYYYMMDD ごとの成約数が見える。
    例: &a8sid=htn_20260411
    """
    if not url:
        return url
    pid = PLATFORM_IDS.get(platform, platform)
    sid = f"{pid}_{_today()}"
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}a8sid={sid}"


def add_amazon_sub(url: str, platform: str) -> str:
    """
    AmazonアソシエイトURLにsub1パラメータを付与する。
    Amazonアソシエイトは複数タグ作成が必要なため、
    sub1で補助的な計測を行う（一部サードパーティ分析ツールが対応）。
    例: &sub1=x_20260411
    """
    if not url:
        return url
    pid = PLATFORM_IDS.get(platform, platform)
    sub = f"{pid}_{_today()}"
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}sub1={sub}"


def add_utm(url: str, platform: str, campaign: str = "auto") -> str:
    """
    はてなブログ/note等の記事URLをSNS投稿に貼るときUTMパラメータを付与する。
    Googleアナリティクス（はてなブログのアクセス解析）で流入元を分離できる。
    例: ?utm_source=x&utm_medium=social&utm_campaign=20260411_auto
    """
    if not url:
        return url
    pid = PLATFORM_IDS.get(platform, platform)
    date = _today()
    params = f"utm_source={pid}&utm_medium=social&utm_campaign={date}_{campaign}"
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}{params}"


def tag_affiliate_link(url: str, platform: str) -> str:
    """
    URLの種類を自動判別してトラッキングパラメータを付与するメイン関数。

    - px.a8.net → a8sid付与（A8レポートで計測）
    - amazon.co.jp / amazon.com → sub1付与
    - その他（ブログURL等）→ UTM付与
    """
    if not url:
        return url
    if "px.a8.net" in url or ("a8.net" in url and "a8mat" in url):
        return add_a8_sid(url, platform)
    if "amazon.co.jp" in url or "amazon.com" in url or "amzn" in url:
        return add_amazon_sub(url, platform)
    return add_utm(url, platform)
