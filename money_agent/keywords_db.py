"""
月10万円を狙う高商業意図キーワードDB
検索ボリューム × 単価 × 競合度 を考慮して選定
"""

# カテゴリ別キーワード（商業意図 × アフィリエイト単価が高いもの優先）
KEYWORD_CATEGORIES = {

    "ai_tools": {
        "label": "AIツール紹介",
        "commission_range": "2,000〜10,000円/件",
        "keywords": [
            {"kw": "ChatGPT 使い方 初心者", "intent": "how-to", "volume": "high"},
            {"kw": "AIツール おすすめ 2026", "intent": "commercial", "volume": "high"},
            {"kw": "Gemini 無料 使い方", "intent": "how-to", "volume": "high"},
            {"kw": "Perplexity AI 使い方 日本語", "intent": "how-to", "volume": "mid"},
            {"kw": "Claude AI 使い方", "intent": "how-to", "volume": "mid"},
            {"kw": "AI 画像生成 無料 おすすめ", "intent": "commercial", "volume": "high"},
            {"kw": "Midjourney 使い方 日本語", "intent": "how-to", "volume": "mid"},
            {"kw": "Notion AI 使い方", "intent": "how-to", "volume": "mid"},
            {"kw": "AI 文章生成 ツール 比較", "intent": "commercial", "volume": "mid"},
            {"kw": "AI 動画生成 無料", "intent": "commercial", "volume": "high"},
        ]
    },

    "side_hustle": {
        "label": "AI副業・稼ぎ方",
        "commission_range": "3,000〜50,000円/件",
        "keywords": [
            {"kw": "AI副業 始め方 初心者", "intent": "commercial", "volume": "high"},
            {"kw": "副業 月10万 現実的", "intent": "informational", "volume": "high"},
            {"kw": "在宅 副業 スマホ 稼ぐ", "intent": "commercial", "volume": "high"},
            {"kw": "AI ライティング 副業", "intent": "commercial", "volume": "mid"},
            {"kw": "クラウドワークス 始め方", "intent": "how-to", "volume": "high"},
            {"kw": "ランサーズ 初心者 稼ぎ方", "intent": "how-to", "volume": "mid"},
            {"kw": "ブログ アフィリエイト 始め方 2026", "intent": "commercial", "volume": "high"},
            {"kw": "YouTube 収益化 条件 2026", "intent": "informational", "volume": "high"},
            {"kw": "SNS運用代行 副業 やり方", "intent": "commercial", "volume": "mid"},
            {"kw": "せどり 副業 初心者 Amazon", "intent": "commercial", "volume": "mid"},
        ]
    },

    "investment_savings": {
        "label": "投資・節約（高単価）",
        "commission_range": "5,000〜30,000円/件",
        "keywords": [
            {"kw": "新NISAの始め方 証券会社 比較", "intent": "commercial", "volume": "high"},
            {"kw": "SBI証券 口座開設 方法", "intent": "how-to", "volume": "high"},
            {"kw": "楽天証券 メリット デメリット", "intent": "commercial", "volume": "high"},
            {"kw": "ポイント投資 おすすめ アプリ", "intent": "commercial", "volume": "mid"},
            {"kw": "クレジットカード おすすめ 2026 還元率", "intent": "commercial", "volume": "high"},
            {"kw": "電気代 節約 方法 一人暮らし", "intent": "commercial", "volume": "high"},
            {"kw": "格安SIM おすすめ 2026 比較", "intent": "commercial", "volume": "high"},
            {"kw": "節約 アプリ おすすめ 無料", "intent": "commercial", "volume": "mid"},
        ]
    },

    "productivity": {
        "label": "時短・生産性向上",
        "commission_range": "1,000〜5,000円/件",
        "keywords": [
            {"kw": "時短 仕事術 AI 活用", "intent": "informational", "volume": "mid"},
            {"kw": "タスク管理 アプリ おすすめ 2026", "intent": "commercial", "volume": "mid"},
            {"kw": "Notion 使い方 テンプレート", "intent": "how-to", "volume": "high"},
            {"kw": "ChatGPT 仕事 活用 具体例", "intent": "informational", "volume": "high"},
            {"kw": "自動化 ツール 無料 おすすめ", "intent": "commercial", "volume": "mid"},
        ]
    }
}

# アフィリエイトプログラム（単価が高い順）
AFFILIATE_PROGRAMS = {

    # === 高単価（5,000円以上）===
    "tossy": {
        "name": "TOSSY（DMM.com証券）",
        "commission": "15,000円/件",
        "category": "投資",
        "url": "https://px.a8.net/svt/ejp?a8mat=4AZPOR+A94RUA+1WP2+1HLNLE",
        "description": "株式・FX・暗号資産を1アプリで完結・新規登録+1回取引",
        "cta": "TOSSYで投資を始める →"
    },
    "rakuten_card": {
        "name": "楽天カード",
        "commission": "7,000〜10,000円/件",
        "category": "クレカ",
        "url": "https://rpx.a8.net/svt/ejp?a8mat=4AZMKI+BFEJSI+2HOM+BW8O1&rakuten=y&a8ejpredirect=http%3A%2F%2Fhb.afl.rakuten.co.jp%2Fhgc%2F0ea62065.34400275.0ea62066.204f04c0%2Fa26032392970_4AZMKI_BFEJSI_2HOM_BW8O1%3Fpc%3Dhttps%253A%252F%252Fcard.rakuten.co.jp%252F%26m%3Dhttps%253A%252F%252Fcard.rakuten.co.jp%252F",
        "description": "年会費永年無料・ポイント還元率1%",
        "cta": "今すぐ無料で作る →"
    },
    "sbi_securities": {
        "name": "楽天証券（NISA）",
        "commission": "3,000〜15,000円/口座",
        "category": "証券",
        "url": "https://rpx.a8.net/svt/ejp?a8mat=4AZMKI+BFEJSI+2HOM+BW8O1&rakuten=y&a8ejpredirect=http%3A%2F%2Fhb.afl.rakuten.co.jp%2Fhgc%2F0ea62065.34400275.0ea62066.204f04c0%2Fa26032392970_4AZMKI_BFEJSI_2HOM_BW8O1%3Fpc%3Dhttps%253A%252F%252Fwww.rakuten-sec.co.jp%252F%26m%3Dhttps%253A%252F%252Fwww.rakuten-sec.co.jp%252F",
        "description": "楽天ポイントで投資・新NISA完全対応",
        "cta": "楽天証券で口座開設（無料）→"
    },
    "rakuten_securities": {
        "name": "楽天証券",
        "commission": "3,000〜15,000円/口座",
        "category": "証券",
        "url": "https://rpx.a8.net/svt/ejp?a8mat=4AZMKI+BFEJSI+2HOM+BW8O1&rakuten=y&a8ejpredirect=http%3A%2F%2Fhb.afl.rakuten.co.jp%2Fhgc%2F0ea62065.34400275.0ea62066.204f04c0%2Fa26032392970_4AZMKI_BFEJSI_2HOM_BW8O1%3Fpc%3Dhttps%253A%252F%252Fwww.rakuten-sec.co.jp%252F%26m%3Dhttps%253A%252F%252Fwww.rakuten-sec.co.jp%252F",
        "description": "楽天ポイントで投資できる・新NISA対応",
        "cta": "楽天ポイントを使って投資を始める →"
    },

    # === 中単価（1,000〜5,000円）===
    "onamae_domain": {
        "name": "お名前.com",
        "commission": "110〜3,100円/件",
        "category": "ドメイン",
        "url": "https://px.a8.net/svt/ejp?a8mat=4AZMKI+BRWNHU+50+2HEG76",
        "description": "国内シェアNo.1ドメイン取得サービス・.com/.net 0円〜",
        "cta": "お名前.comでドメインを取得する →"
    },
    "crowdworks": {
        "name": "クラウドワークス",
        "commission": "2,000〜3,000円/登録",
        "category": "副業",
        "url": "https://crowdworks.jp/",
        "description": "日本最大級のクラウドソーシング",
        "cta": "無料登録して副業を始める →"
    },
    "lancers": {
        "name": "ランサーズ",
        "commission": "1,500〜2,500円/登録",
        "category": "副業",
        "url": "https://www.lancers.jp/",
        "description": "スキルを活かして在宅で稼ぐ",
        "cta": "ランサーズで仕事を探す →"
    },
    "rakuten_market": {
        "name": "楽天市場",
        "commission": "1〜3%",
        "category": "物販",
        "url": "https://rpx.a8.net/svt/ejp?a8mat=4AZMKI+BFEJSI+2HOM+BW8O1&rakuten=y&a8ejpredirect=http%3A%2F%2Fhb.afl.rakuten.co.jp%2Fhgc%2F0ea62065.34400275.0ea62066.204f04c0%2Fa26032392970_4AZMKI_BFEJSI_2HOM_BW8O1%3Fpc%3Dhttps%253A%252F%252Fwww.rakuten.co.jp%26m%3Dhttps%253A%252F%252Fwww.rakuten.co.jp",
        "description": "日本最大のネットショッピングモール",
        "cta": "楽天市場で探す →"
    },

    # === SaaS/AIツール（継続課金）===
    "canva_pro": {
        "name": "Canva Pro",
        "commission": "初回購入の36%",
        "category": "AIツール",
        "url": "https://www.canva.com/affiliates/",
        "description": "AI搭載デザインツール・月1,500円〜",
        "cta": "Canva Proを試す（30日無料）→"
    },
    "notion": {
        "name": "Notion Plus",
        "commission": "3ヶ月分の50%",
        "category": "生産性",
        "url": "https://www.notion.so/",
        "description": "オールインワン仕事術ツール",
        "cta": "Notionを無料で始める →"
    }
}

# コンテンツ × アフィリエイトのマッピング
CONTENT_AFFILIATE_MAP = {
    "ai_tools": ["canva_pro", "notion", "onamae_domain"],
    "side_hustle": ["crowdworks", "lancers", "onamae_domain"],
    "investment_savings": ["tossy", "rakuten_card", "rakuten_securities"],
    "productivity": ["notion", "onamae_domain", "canva_pro"],
}

def get_keywords_for_category(category: str) -> list:
    """カテゴリのキーワードリストを取得"""
    cat = KEYWORD_CATEGORIES.get(category, {})
    return [k["kw"] for k in cat.get("keywords", [])]

def get_affiliates_for_category(category: str) -> list:
    """カテゴリに合ったアフィリエイトを取得"""
    affiliate_ids = CONTENT_AFFILIATE_MAP.get(category, [])
    return [AFFILIATE_PROGRAMS[aid] for aid in affiliate_ids if aid in AFFILIATE_PROGRAMS]

def get_next_keyword(used_keywords: list = None) -> dict:
    """未使用の次のキーワードを選択"""
    import random
    used = used_keywords or []
    all_kws = []
    for cat_id, cat_data in KEYWORD_CATEGORIES.items():
        for kw_data in cat_data["keywords"]:
            if kw_data["kw"] not in used:
                all_kws.append({
                    "keyword": kw_data["kw"],
                    "category": cat_id,
                    "intent": kw_data["intent"],
                    "volume": kw_data["volume"]
                })
    if not all_kws:
        # 全部使い切ったらリセット
        return get_next_keyword([])

    # 商業意図 × 検索ボリュームで重み付け
    weights = []
    for kw in all_kws:
        w = 1
        if kw["intent"] == "commercial": w *= 3
        if kw["volume"] == "high": w *= 2
        weights.append(w)

    return random.choices(all_kws, weights=weights, k=1)[0]


if __name__ == "__main__":
    kw = get_next_keyword()
    print(f"次のキーワード: {kw['keyword']} ({kw['category']} / {kw['intent']})")
    affiliates = get_affiliates_for_category(kw['category'])
    print(f"推奨アフィリエイト: {[a['name'] for a in affiliates]}")
