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
            # volume=high は競合が多い。パイロット期は mid/low + commercial を優先
            {"kw": "ChatGPT 使い方 初心者", "intent": "how-to", "volume": "high", "competition": "high"},
            {"kw": "AIツール おすすめ 2026", "intent": "commercial", "volume": "high", "competition": "high"},
            {"kw": "Gemini 無料 使い方", "intent": "how-to", "volume": "high", "competition": "high"},
            {"kw": "Perplexity AI 使い方 日本語", "intent": "how-to", "volume": "mid", "competition": "mid"},
            {"kw": "Claude AI 使い方", "intent": "how-to", "volume": "mid", "competition": "mid"},
            {"kw": "AI 画像生成 無料 おすすめ", "intent": "commercial", "volume": "high", "competition": "high"},
            {"kw": "Midjourney 使い方 日本語", "intent": "how-to", "volume": "mid", "competition": "mid"},
            {"kw": "Notion AI 使い方", "intent": "how-to", "volume": "mid", "competition": "mid"},
            {"kw": "AI 文章生成 ツール 比較", "intent": "commercial", "volume": "mid", "competition": "mid"},
            {"kw": "AI 動画生成 無料", "intent": "commercial", "volume": "high", "competition": "high"},
        ]
    },

    "side_hustle": {
        "label": "AI副業・稼ぎ方",
        "commission_range": "3,000〜50,000円/件",
        "keywords": [
            {"kw": "AI副業 始め方 初心者", "intent": "commercial", "volume": "high", "competition": "high"},
            {"kw": "副業 月10万 現実的", "intent": "informational", "volume": "high", "competition": "high"},
            {"kw": "在宅 副業 スマホ 稼ぐ", "intent": "commercial", "volume": "high", "competition": "high"},
            {"kw": "AI ライティング 副業", "intent": "commercial", "volume": "mid", "competition": "mid"},
            {"kw": "クラウドワークス 始め方", "intent": "how-to", "volume": "high", "competition": "high"},
            {"kw": "ランサーズ 初心者 稼ぎ方", "intent": "how-to", "volume": "mid", "competition": "mid"},
            {"kw": "ブログ アフィリエイト 始め方 2026", "intent": "commercial", "volume": "high", "competition": "high"},
            {"kw": "YouTube 収益化 条件 2026", "intent": "informational", "volume": "high", "competition": "high"},
            {"kw": "SNS運用代行 副業 やり方", "intent": "commercial", "volume": "mid", "competition": "mid"},
            {"kw": "せどり 副業 初心者 Amazon", "intent": "commercial", "volume": "mid", "competition": "mid"},
        ]
    },

    "investment_savings": {
        "label": "投資・資産形成（高単価）",
        "commission_range": "5,000〜30,000円/件",
        "keywords": [
            {"kw": "新NISAの始め方 証券会社 比較", "intent": "commercial", "volume": "high", "competition": "high"},
            {"kw": "SBI証券 口座開設 方法", "intent": "how-to", "volume": "high", "competition": "high"},
            {"kw": "楽天証券 メリット デメリット", "intent": "commercial", "volume": "high", "competition": "high"},
            {"kw": "ポイント投資 おすすめ アプリ", "intent": "commercial", "volume": "mid", "competition": "mid"},
            {"kw": "iDeCo おすすめ 証券会社 2026", "intent": "commercial", "volume": "high", "competition": "high"},
            {"kw": "iDeCo 松井証券 メリット", "intent": "commercial", "volume": "mid", "competition": "mid"},
            {"kw": "iDeCo 始め方 会社員 節税", "intent": "how-to", "volume": "high", "competition": "high"},
            {"kw": "iDeCo 手数料 無料 比較", "intent": "commercial", "volume": "mid", "competition": "mid"},
            {"kw": "新NISA 口座開設 おすすめ 2026", "intent": "commercial", "volume": "high", "competition": "high"},
            {"kw": "楽天証券 SBI証券 比較 2026", "intent": "commercial", "volume": "high", "competition": "mid"},
        ]
    },

    "savings_lifestyle": {
        "label": "節約・生活費削減",
        "commission_range": "2,000〜10,000円/件",
        "keywords": [
            {"kw": "クレジットカード おすすめ 2026 還元率", "intent": "commercial", "volume": "high", "competition": "high"},
            {"kw": "電気代 節約 方法 一人暮らし", "intent": "commercial", "volume": "high", "competition": "high"},
            {"kw": "格安SIM おすすめ 2026 比較", "intent": "commercial", "volume": "high", "competition": "high"},
            {"kw": "節約 アプリ おすすめ 無料", "intent": "commercial", "volume": "mid", "competition": "mid"},
            {"kw": "電力会社 乗り換え おすすめ 2026", "intent": "commercial", "volume": "mid", "competition": "mid"},
            {"kw": "家計 見直し 固定費 削減", "intent": "informational", "volume": "mid", "competition": "low"},
        ]
    },

    "high_value": {
        "label": "高単価案件（プログラミング・転職）",
        "commission_range": "8,000〜50,000円/件",
        "keywords": [
            {"kw": "プログラミングスクール おすすめ 2026", "intent": "commercial", "volume": "high", "competition": "high"},
            {"kw": "未経験 エンジニア転職 スクール 比較", "intent": "commercial", "volume": "mid", "competition": "mid"},
            {"kw": "副業 プログラミング 稼ぐ方法", "intent": "commercial", "volume": "mid", "competition": "mid"},
            {"kw": "転職エージェント おすすめ 2026", "intent": "commercial", "volume": "high", "competition": "high"},
            {"kw": "FX 口座開設 おすすめ 初心者", "intent": "commercial", "volume": "mid", "competition": "high"},
            {"kw": "確定申告 クラウド会計 おすすめ", "intent": "commercial", "volume": "mid", "competition": "mid"},
        ]
    },

    "productivity": {
        "label": "時短・生産性向上",
        "commission_range": "1,000〜5,000円/件",
        "keywords": [
            {"kw": "時短 仕事術 AI 活用", "intent": "informational", "volume": "mid", "competition": "mid"},
            {"kw": "タスク管理 アプリ おすすめ 2026", "intent": "commercial", "volume": "mid", "competition": "mid"},
            {"kw": "Notion 使い方 テンプレート", "intent": "how-to", "volume": "high", "competition": "high"},
            {"kw": "ChatGPT 仕事 活用 具体例", "intent": "informational", "volume": "high", "competition": "high"},
            {"kw": "自動化 ツール 無料 おすすめ", "intent": "commercial", "volume": "mid", "competition": "mid"},
        ]
    },

    "dx_tools": {
        "label": "DX・業務効率化ツール（中小企業向け）",
        "commission_range": "1,500〜3,000円/件",
        "keywords": [
            {"kw": "freee 中小企業 クラウド会計", "intent": "commercial", "volume": "mid", "competition": "mid"},
            {"kw": "freee 会計 使い方 経営者", "intent": "how-to", "volume": "mid", "competition": "low"},
            {"kw": "マネーフォワード クラウド 中小企業", "intent": "commercial", "volume": "mid", "competition": "mid"},
            {"kw": "マネーフォワード 使い方 経営者", "intent": "how-to", "volume": "mid", "competition": "low"},
            {"kw": "Chatwork 社内チャット 中小企業", "intent": "commercial", "volume": "mid", "competition": "mid"},
            {"kw": "Chatwork 使い方 社内連絡 効率化", "intent": "how-to", "volume": "mid", "competition": "low"},
            {"kw": "中小企業 DX ツール おすすめ 2026", "intent": "commercial", "volume": "high", "competition": "high"},
            {"kw": "クラウド会計 比較 中小企業", "intent": "commercial", "volume": "mid", "competition": "mid"},
            {"kw": "業務効率化 ツール 無料 中小企業", "intent": "commercial", "volume": "mid", "competition": "mid"},
            {"kw": "チャットツール 社内 おすすめ 中小企業", "intent": "commercial", "volume": "mid", "competition": "mid"},
        ]
    }
}

# ============================================================
# パイロット検証用「低難易度×高意図」キーワード
# ニッチで具体的な悩みを含む長尾クエリ
# 検索ボリュームは少ないが、AI検索に引用されたときのCVRが高い
# ============================================================
PILOT_KEYWORDS = {
    "ai_saas": [
        {"kw": "ChatGPT Plus 仕事 月2000円 元が取れるか", "intent": "commercial", "volume": "low", "competition": "low"},
        {"kw": "Notion AI 議事録 自動生成 やり方 設定", "intent": "how-to", "volume": "low", "competition": "low"},
        {"kw": "Canva Pro 中小企業 デザイナーなし 代替", "intent": "commercial", "volume": "low", "competition": "low"},
        {"kw": "ChatGPT 見積書 作成 テンプレート 経営者", "intent": "how-to", "volume": "low", "competition": "low"},
        {"kw": "Notion vs Backlog どちら 中小企業 プロジェクト管理", "intent": "commercial", "volume": "low", "competition": "low"},
    ],
    "dx_tools": [
        {"kw": "個人事業主 確定申告ソフト 比較 freee マネーフォワード", "intent": "commercial", "volume": "low", "competition": "low"},
        {"kw": "freee 青色申告 初めて 設定 つまずきポイント", "intent": "how-to", "volume": "low", "competition": "low"},
        {"kw": "マネーフォワード 給与計算 社員3人 費用対効果", "intent": "commercial", "volume": "low", "competition": "low"},
        {"kw": "Chatwork Slack どちら 5人以下 会社 比較", "intent": "commercial", "volume": "low", "competition": "low"},
        {"kw": "インボイス制度 対応 クラウド請求書 比較 個人事業主", "intent": "commercial", "volume": "low", "competition": "low"},
    ],
    "investment_savings": [
        {"kw": "iDeCo 会社員 年収400万 節税効果 実際の金額", "intent": "informational", "volume": "low", "competition": "low"},
        {"kw": "新NISA 積立 月3万 10年後 シミュレーション", "intent": "informational", "volume": "low", "competition": "low"},
        {"kw": "SBI証券 楽天証券 どちら 2026 乗り換え 手数料", "intent": "commercial", "volume": "low", "competition": "low"},
        {"kw": "格安SIM IIJmio vs 楽天モバイル 一人暮らし データ通信量", "intent": "commercial", "volume": "low", "competition": "low"},
        {"kw": "電気代 年間5万削減 実績 電力会社 切り替え", "intent": "commercial", "volume": "low", "competition": "low"},
    ],
    "side_hustle": [
        {"kw": "クラウドワークス 文字単価1円 最初の1件 取り方", "intent": "how-to", "volume": "low", "competition": "low"},
        {"kw": "AIライティング 副業 月3万 実際の作業時間 本音", "intent": "informational", "volume": "low", "competition": "low"},
        {"kw": "Lancers 初心者 評価ゼロ 受注 コツ", "intent": "how-to", "volume": "low", "competition": "low"},
        {"kw": "副業 会社にバレない 住民税 確定申告 対策", "intent": "informational", "volume": "low", "competition": "low"},
        {"kw": "note 有料記事 最初の1件 売れた 体験談", "intent": "informational", "volume": "low", "competition": "low"},
    ],
    "ai_tools": [
        {"kw": "Perplexity vs ChatGPT 調べ物 どちら 使い分け", "intent": "commercial", "volume": "low", "competition": "low"},
        {"kw": "Midjourney 商用利用 アフィリエイト画像 規約 確認", "intent": "how-to", "volume": "low", "competition": "low"},
        {"kw": "Claude 無料プラン 上限 毎日使える 実際の文字数", "intent": "informational", "volume": "low", "competition": "low"},
        {"kw": "Gemini Advanced 2000円 ChatGPT Plus 比較 仕事用", "intent": "commercial", "volume": "low", "competition": "low"},
        {"kw": "AI文章生成 オリジナリティ GoogleSEO ペナルティ 対策", "intent": "informational", "volume": "low", "competition": "low"},
    ],
}

def _load_affiliate_urls() -> dict:
    """
    money_agent/config/affiliate_links.json からURLを動的に読み込む
    提携URLが更新されたときに、このファイルだけ書き換えればOK
    """
    import os
    config_file = os.path.join(os.path.dirname(__file__), "data", "affiliate_links.json")
    try:
        import json
        with open(config_file, encoding="utf-8") as f:
            data = json.load(f)
        # _で始まるメタキーを除外してURL辞書を返す
        return {k: v.get("url", "") for k, v in data.items() if not k.startswith("_") and v.get("url")}
    except Exception:
        return {}

# 外部設定ファイルからURLを取得（なければfallbackURLを使う）
_AFFILIATE_URLS = _load_affiliate_urls()


def _url(program_id: str, fallback: str) -> str:
    """config/affiliate_links.json のURLを優先。なければfallback"""
    return _AFFILIATE_URLS.get(program_id, fallback)


# アフィリエイトプログラム（単価が高い順）
AFFILIATE_PROGRAMS = {

    # === 高単価（5,000円以上）===
    "tossy": {
        "name": "TOSSY（DMM.com証券）",
        "commission": "15,000円/件",
        "category": "投資",
        "url": _url("tossy", "https://px.a8.net/svt/ejp?a8mat=4AZPOR+A94RUA+1WP2+1HLNLE"),
        "description": "株式・FX・暗号資産を1アプリで完結・新規登録+1回取引",
        "cta": "TOSSYで投資を始める →"
    },
    "rakuten_card": {
        "name": "楽天カード",
        "commission": "7,000〜10,000円/件",
        "category": "クレカ",
        "url": _url("rakuten_card", "https://rpx.a8.net/svt/ejp?a8mat=4AZMKI+BFEJSI+2HOM+BW8O1&rakuten=y&a8ejpredirect=http%3A%2F%2Fhb.afl.rakuten.co.jp%2Fhgc%2F0ea62065.34400275.0ea62066.204f04c0%2Fa26032392970_4AZMKI_BFEJSI_2HOM_BW8O1%3Fpc%3Dhttps%253A%252F%252Fcard.rakuten.co.jp%252F%26m%3Dhttps%253A%252F%252Fcard.rakuten.co.jp%252F"),
        "description": "年会費永年無料・ポイント還元率1%",
        "cta": "今すぐ無料で作る →"
    },
    "sbi_securities": {
        "name": "楽天証券（NISA）",
        "commission": "3,000〜15,000円/口座",
        "category": "証券",
        "url": _url("sbi_securities", "https://rpx.a8.net/svt/ejp?a8mat=4AZMKI+BFEJSI+2HOM+BW8O1&rakuten=y&a8ejpredirect=http%3A%2F%2Fhb.afl.rakuten.co.jp%2Fhgc%2F0ea62065.34400275.0ea62066.204f04c0%2Fa26032392970_4AZMKI_BFEJSI_2HOM_BW8O1%3Fpc%3Dhttps%253A%252F%252Fwww.rakuten-sec.co.jp%252F%26m%3Dhttps%253A%252F%252Fwww.rakuten-sec.co.jp%252F"),
        "description": "楽天ポイントで投資・新NISA完全対応",
        "cta": "楽天証券で口座開設（無料）→"
    },
    "rakuten_securities": {
        "name": "楽天証券",
        "commission": "3,000〜15,000円/口座",
        "category": "証券",
        "url": _url("rakuten_securities", "https://rpx.a8.net/svt/ejp?a8mat=4AZMKI+BFEJSI+2HOM+BW8O1&rakuten=y&a8ejpredirect=http%3A%2F%2Fhb.afl.rakuten.co.jp%2Fhgc%2F0ea62065.34400275.0ea62066.204f04c0%2Fa26032392970_4AZMKI_BFEJSI_2HOM_BW8O1%3Fpc%3Dhttps%253A%252F%252Fwww.rakuten-sec.co.jp%252F%26m%3Dhttps%253A%252F%252Fwww.rakuten-sec.co.jp%252F"),
        "description": "楽天ポイントで投資できる・新NISA対応",
        "cta": "楽天ポイントを使って投資を始める →"
    },

    # === 中単価（1,000〜5,000円）===
    "onamae_domain": {
        "name": "お名前.com",
        "commission": "1,150〜5,100円/件",
        "category": "ドメイン",
        "url": _url("onamae_domain", "https://px.a8.net/svt/ejp?a8mat=4AZMKI+BRWNHU+50+2HEG76"),
        "description": "国内シェアNo.1ドメイン取得サービス・ドメインカテゴリNO.1報酬！レンタルサーバー同時申請なら5,100円",
        "cta": "お名前.comでドメインを取得する →"
    },
    "crowdworks": {
        "name": "クラウドワークス",
        "commission": "2,000〜3,000円/登録",
        "category": "副業",
        "url": _url("crowdworks", "https://crowdworks.jp/"),
        "description": "日本最大級のクラウドソーシング",
        "cta": "無料登録して副業を始める →"
    },
    "lancers": {
        "name": "ランサーズ",
        "commission": "1,500〜2,500円/登録",
        "category": "副業",
        "url": _url("lancers", "https://www.lancers.jp/"),
        "description": "スキルを活かして在宅で稼ぐ",
        "cta": "ランサーズで仕事を探す →"
    },
    "rakuten_market": {
        "name": "楽天市場",
        "commission": "1〜3%",
        "category": "物販",
        "url": _url("rakuten_market", "https://rpx.a8.net/svt/ejp?a8mat=4AZMKI+BFEJSI+2HOM+BW8O1&rakuten=y&a8ejpredirect=http%3A%2F%2Fhb.afl.rakuten.co.jp%2Fhgc%2F0ea62065.34400275.0ea62066.204f04c0%2Fa26032392970_4AZMKI_BFEJSI_2HOM_BW8O1%3Fpc%3Dhttps%253A%252F%252Fwww.rakuten.co.jp%26m%3Dhttps%253A%252F%252Fwww.rakuten.co.jp"),
        "description": "日本最大のネットショッピングモール",
        "cta": "楽天市場で探す →"
    },

    # === iDeCo（節税×老後対策・中高単価）===
    "matsui_ideco": {
        "name": "松井証券 iDeCo",
        "commission": "500円/新規口座開設申込",
        "category": "iDeCo",
        "url": _url("matsui_ideco", "https://px.a8.net/svt/ejp?a8mat=4AZPOR+8OKLDE+3XCC+BXIYQ"),
        "description": "運用管理手数料ずっと無料・100円から積立可能・老後資金を節税しながら積み立て",
        "cta": "松井証券でiDeCoを始める（無料）→",
    },

    # === DX・業務効率化ツール（config/affiliate_links.jsonで管理）===
    "freee_accounting": {
        "name": "freee会計",
        "commission": "2,000円/無料トライアル登録",
        "category": "DXツール",
        "url": _url("freee_accounting", "https://px.a8.net/svt/ejp?a8mat=3Z1234+FREEE1+0000+0000A"),
        "description": "中小企業・個人事業主向けクラウド会計ソフト。確定申告・帳簿づけをAIが自動化",
        "cta": "freeeを無料で試してみる（30日間）→",
    },
    "moneyforward_cloud": {
        "name": "マネーフォワード クラウド",
        "commission": "1,500円/無料登録",
        "category": "DXツール",
        "url": _url("moneyforward_cloud", "https://px.a8.net/svt/ejp?a8mat=3Z1234+MFWD01+0000+0000A"),
        "description": "給与計算・経費精算・請求書をまとめて自動化。連携サービス5,000以上",
        "cta": "マネーフォワード クラウドを無料で試す →",
    },
    "chatwork": {
        "name": "Chatwork",
        "commission": "3,000円/有料プラン契約",
        "category": "DXツール",
        "url": _url("chatwork", "https://px.a8.net/svt/ejp?a8mat=3Z1234+CWORK1+0000+0000A"),
        "description": "国内利用者数No.1のビジネスチャット。メール・電話を減らして社内連絡を効率化",
        "cta": "Chatworkを無料で始める →",
    },

    # === SaaS/AIツール（継続課金）===
    "canva_pro": {
        "name": "Canva Pro",
        "commission": "初回購入の36%",
        "category": "AIツール",
        "url": _url("canva_pro", "https://www.canva.com/affiliates/"),
        "description": "AI搭載デザインツール・月1,500円〜",
        "cta": "Canva Proを試す（30日無料）→"
    },
    "notion": {
        "name": "Notion Plus",
        "commission": "3ヶ月分の50%",
        "category": "生産性",
        "url": _url("notion", "https://www.notion.so/"),
        "description": "オールインワン仕事術ツール",
        "cta": "Notionを無料で始める →"
    },

    # === Amazonアソシエイト（もしもアフィリエイト経由 or 直接）===
    # AMAZON_ASSOCIATE_TAG を .env に設定（例: yourtag-22）
    "amazon_kindle": {
        "name": "Kindle Unlimited",
        "commission": "販売価格の3〜10%",
        "category": "副業",
        "url": "https://www.amazon.co.jp/kindle-dbs/hz/subscribe/ku?tag={AMAZON_TAG}",
        "description": "200万冊以上読み放題・月980円・30日無料体験あり",
        "cta": "Kindle Unlimitedを30日無料で試す →",
        "_tag_required": True,
    },
    "amazon_audible": {
        "name": "Audible（オーディブル）",
        "commission": "新規登録1件 500円〜",
        "category": "副業",
        "url": "https://www.amazon.co.jp/b?node=5816607051&tag={AMAZON_TAG}",
        "description": "本をながら聴き・月1,500円・最初の30日無料",
        "cta": "Audibleを無料で始める →",
        "_tag_required": True,
    },
    "amazon_prime": {
        "name": "Amazonプライム",
        "commission": "新規登録1件 200〜400円",
        "category": "副業",
        "url": "https://www.amazon.co.jp/prime?tag={AMAZON_TAG}",
        "description": "配送無料・Prime Video・月600円（年4,900円）",
        "cta": "30日間無料体験を始める →",
        "_tag_required": True,
    },
}

# コンテンツ × アフィリエイトのマッピング
CONTENT_AFFILIATE_MAP = {
    "ai_tools": ["canva_pro", "notion", "onamae_domain"],
    "side_hustle": ["crowdworks", "lancers", "onamae_domain"],
    "investment_savings": ["tossy", "rakuten_card", "rakuten_securities", "matsui_ideco"],
    "savings_lifestyle": ["rakuten_card", "tossy", "matsui_ideco"],
    "high_value": ["freee_accounting", "moneyforward_cloud", "onamae_domain", "tossy"],
    "productivity": ["notion", "onamae_domain", "canva_pro"],
    "dx_tools": ["freee_accounting", "moneyforward_cloud", "chatwork"],
}

def _resolve_affiliate_url(program: dict) -> dict:
    """AmazonアソシエイトタグなどをURLに埋め込む"""
    import os
    if "{AMAZON_TAG}" in program.get("url", ""):
        tag = os.environ.get("AMAZON_ASSOCIATE_TAG", "")
        if tag:
            program = program.copy()
            program["url"] = program["url"].replace("{AMAZON_TAG}", tag)
        else:
            # タグ未設定ならもしもアフィリエイト経由のURLに差し替え
            program = program.copy()
            program["url"] = "https://af.moshimo.com/af/c/click?a_id=XXXX"  # 要設定
            program["description"] = "(要設定) " + program.get("description", "")
    return program

def get_keywords_for_category(category: str) -> list:
    """カテゴリのキーワードリストを取得"""
    cat = KEYWORD_CATEGORIES.get(category, {})
    return [k["kw"] for k in cat.get("keywords", [])]

def get_affiliates_for_category(category: str) -> list:
    """カテゴリに合ったアフィリエイトを取得"""
    affiliate_ids = CONTENT_AFFILIATE_MAP.get(category, [])
    return [_resolve_affiliate_url(AFFILIATE_PROGRAMS[aid]) for aid in affiliate_ids if aid in AFFILIATE_PROGRAMS]

def _get_dynamic_keywords() -> list:
    """data_collectorが収集した動的キーワードを取得"""
    try:
        from money_agent.data_collector import get_dynamic_keywords
        dynamic = []
        for cat_id in KEYWORD_CATEGORIES:
            for kw in get_dynamic_keywords(cat_id):
                if kw.get("kw"):
                    dynamic.append({
                        "keyword": kw["kw"],
                        "category": cat_id,
                        "intent": kw.get("intent", "commercial"),
                        "volume": kw.get("volume", "mid"),
                        "source": "dynamic",
                    })
        return dynamic
    except Exception:
        return []


def _load_active_categories() -> list:
    """genre_strategy.json からアクティブカテゴリを読み込む"""
    import os
    strategy_file = os.path.join(os.path.dirname(__file__), "data", "genre_strategy.json")
    try:
        with open(strategy_file, encoding="utf-8") as f:
            data = json.load(f)
        active = data.get("active_categories", [])
        if active:
            return active
    except Exception:
        pass
    return []  # 空リスト = 全カテゴリ有効


def get_next_keyword(
    used_keywords: list = None,
    _depth: int = 0,
    preferred_category: str = None,
    pilot_mode: bool = False,
) -> dict:
    """未使用の次のキーワードを選択

    pilot_mode=True: パイロット検証期間用。PILOT_KEYWORDS から「低競合×高意図」を優先選択。
    preferred_category: SNS分析から推奨されたカテゴリ（重みを3倍にする）

    genre_strategy.json にアクティブカテゴリが設定されていれば、そのカテゴリのみから選択する。
    """
    import random
    used = used_keywords or []
    all_kws = []

    # アクティブカテゴリの制約
    active_cats = _load_active_categories()

    if pilot_mode:
        # パイロット期: PILOT_KEYWORDS を優先（なければ通常のlow/midボリュームにフォールバック）
        for cat_id, kw_list in PILOT_KEYWORDS.items():
            if active_cats and cat_id not in active_cats:
                continue
            for kw_data in kw_list:
                if kw_data["kw"] not in used:
                    all_kws.append({
                        "keyword": kw_data["kw"],
                        "category": cat_id,
                        "intent": kw_data["intent"],
                        "volume": kw_data["volume"],
                        "competition": kw_data.get("competition", "low"),
                        "is_pilot": True,
                    })

        if all_kws:
            # パイロット期の重み: commercial intent > informational > how-to
            # competition=low を優先（同競合度なら preferredカテゴリを重視）
            weights = []
            for kw in all_kws:
                w = 2  # パイロットキーワードベース重み
                if kw["intent"] == "commercial": w *= 3
                elif kw["intent"] == "informational": w *= 2
                if kw.get("competition") == "low": w *= 2
                if preferred_category and kw["category"] == preferred_category: w *= 3
                weights.append(w)
            return random.choices(all_kws, weights=weights, k=1)[0]
        # パイロットKW使い切り → 通常モードにフォールバック

    # 通常モード: 静的キーワード（アクティブカテゴリのみ）
    for cat_id, cat_data in KEYWORD_CATEGORIES.items():
        if active_cats and cat_id not in active_cats:
            continue
        for kw_data in cat_data["keywords"]:
            if kw_data["kw"] not in used:
                all_kws.append({
                    "keyword": kw_data["kw"],
                    "category": cat_id,
                    "intent": kw_data["intent"],
                    "volume": kw_data["volume"],
                    "competition": kw_data.get("competition", "mid"),
                    "is_pilot": False,
                })
    # 動的キーワード（トレンド収集分）を追加
    for kw_data in _get_dynamic_keywords():
        if kw_data["keyword"] not in used:
            all_kws.append(kw_data)

    if not all_kws:
        if _depth >= 1:
            all_kws = [
                {"keyword": kw_data["kw"], "category": cat_id,
                 "intent": kw_data["intent"], "volume": kw_data["volume"],
                 "competition": kw_data.get("competition", "mid")}
                for cat_id, cat_data in KEYWORD_CATEGORIES.items()
                for kw_data in cat_data["keywords"]
            ]
            return random.choice(all_kws) if all_kws else {
                "keyword": "副業", "category": "side_hustle",
                "intent": "commercial", "volume": "high", "competition": "high"
            }
        return get_next_keyword([], _depth=_depth + 1,
                                preferred_category=preferred_category,
                                pilot_mode=pilot_mode)

    # 商業意図 × 競合度逆数 × SNS推奨カテゴリで重み付け
    weights = []
    for kw in all_kws:
        w = 1
        if kw["intent"] == "commercial": w *= 3
        if kw["volume"] == "high": w *= 2
        comp = kw.get("competition", "mid")
        if comp == "low": w *= 2    # 低競合を優遇
        elif comp == "high": w *= 1  # 高競合は等倍（ペナルティなし）
        if preferred_category and kw["category"] == preferred_category: w *= 3
        weights.append(w)

    return random.choices(all_kws, weights=weights, k=1)[0]


if __name__ == "__main__":
    kw = get_next_keyword()
    print(f"次のキーワード: {kw['keyword']} ({kw['category']} / {kw['intent']})")
    affiliates = get_affiliates_for_category(kw['category'])
    print(f"推奨アフィリエイト: {[a['name'] for a in affiliates]}")
