"""
Google Trendsからライフハック系のトレンドキーワードを取得
"""
from pytrends.request import TrendReq
import random

# ライフハック関連のベースキーワード
LIFEHACK_KEYWORDS = [
    "時短術", "節約術", "掃除 裏技", "睡眠 改善",
    "集中力 上げる", "料理 時短", "洗濯 裏技", "仕事 効率",
    "健康 習慣", "ダイエット 簡単"
]

def get_trending_keywords(top_n=5):
    """Google Trendsからトレンドキーワードを取得"""
    try:
        pytrends = TrendReq(hl='ja-JP', tz=540)

        # ランダムに3つのキーワードで検索
        sample_keywords = random.sample(LIFEHACK_KEYWORDS, min(3, len(LIFEHACK_KEYWORDS)))
        pytrends.build_payload(sample_keywords, cat=0, timeframe='now 7-d', geo='JP')

        # 関連クエリを取得
        related = pytrends.related_queries()
        trending = []

        for kw in sample_keywords:
            try:
                top_df = related[kw]['top']
                if top_df is not None and not top_df.empty:
                    for _, row in top_df.head(2).iterrows():
                        trending.append(row['query'])
            except Exception:
                pass

        # トレンドが取れなければベースキーワードを返す
        if not trending:
            trending = random.sample(LIFEHACK_KEYWORDS, top_n)

        print(f"✅ トレンドキーワード取得: {trending[:top_n]}")
        return trending[:top_n]

    except Exception as e:
        print(f"⚠️ Google Trends取得失敗、デフォルトキーワードを使用: {e}")
        return random.sample(LIFEHACK_KEYWORDS, top_n)


if __name__ == "__main__":
    keywords = get_trending_keywords()
    print("取得したキーワード:", keywords)
