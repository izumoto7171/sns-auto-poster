"""
Amazonアソシエイト商品プール（マスターデータ）

PA-APIへの移行や content_selector.py などとの連携用に
ASIN を主軸とした簡潔なデータ構造で定義する。
"""

import os
from pathlib import Path

_ROOT_DIR = Path(__file__).parent.parent
_env_path = _ROOT_DIR / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

_TAG = os.getenv("AMAZON_ASSOCIATE_TAG", "smartearn22-22")

PRODUCT_POOL = [
    {
        "asin": "B0B96T9CBY",
        "name": "Anker 電源タップ 延長コード USB-C 6口 雷ガード",
        "url": f"https://www.amazon.co.jp/dp/B0B96T9CBY/?tag={_TAG}",
        "keywords": ["電源タップ", "デスク周り", "便利ガジェット", "テレワーク"],
    },
    {
        "asin": "B09V7C9V8B",
        "name": "衣類圧縮袋 掃除機不要 トラベル 収納 10枚",
        "url": f"https://www.amazon.co.jp/dp/B09V7C9V8B/?tag={_TAG}",
        "keywords": ["旅行グッズ", "便利グッズ", "衣類圧縮袋", "収納"],
    },
    {
        "asin": "B0B247R68G",
        "name": "TP-Link スマートプラグ Wi-Fi Alexa 節電",
        "url": f"https://www.amazon.co.jp/dp/B0B247R68G/?tag={_TAG}",
        "keywords": ["スマートホーム", "節電", "ガジェット", "Alexa"],
    },
    {
        "asin": "B0C1Z8R7Y2",
        "name": "Anker Soundcore Liberty 4 NC ワイヤレスイヤホン",
        "url": f"https://www.amazon.co.jp/dp/B0C1Z8R7Y2/?tag={_TAG}",
        "keywords": ["イヤホン", "オーディオ", "Anker", "ノイズキャンセリング"],
    },
    {
        "asin": "B0C2V5Y6K9",
        "name": "Baseus GaN 67W USB-C 急速充電器",
        "url": f"https://www.amazon.co.jp/dp/B0C2V5Y6K9/?tag={_TAG}",
        "keywords": ["充電器", "スマホアクセサリー", "ガジェット", "時短"],
    },
    {
        "asin": "B0B566Y7N4",
        "name": "CIO NovaPort TRIO 65W 3ポート GaN充電器",
        "url": f"https://www.amazon.co.jp/dp/B0B566Y7N4/?tag={_TAG}",
        "keywords": ["充電器", "GaN", "USB-C", "デスク周り"],
    },
    {
        "asin": "B0BY8S8G7R",
        "name": "山崎実業 マグネット ケーブルホルダー",
        "url": f"https://www.amazon.co.jp/dp/B0BY8S8G7R/?tag={_TAG}",
        "keywords": ["デスク周り", "ケーブル整理", "収納", "テレワーク"],
    },
    {
        "asin": "B07W59K48K",
        "name": "ロジクール Pebble M350 ワイヤレスマウス",
        "url": f"https://www.amazon.co.jp/dp/B07W59K48K/?tag={_TAG}",
        "keywords": ["マウス", "ワイヤレス", "テレワーク", "PC周辺機器"],
    },
    {
        "asin": "B099DN8ZKK",
        "name": "エレコム 電源タップ タワー型 8個口",
        "url": f"https://www.amazon.co.jp/dp/B099DN8ZKK/?tag={_TAG}",
        "keywords": ["電源タップ", "デスク周り", "テレワーク", "便利グッズ"],
    },
    {
        "asin": "B08Y8M78F2",
        "name": "Anker Magnetic Cable Holder マグネット式ケーブルホルダー",
        "url": f"https://www.amazon.co.jp/dp/B08Y8M78F2/?tag={_TAG}",
        "keywords": ["デスク周り", "ケーブル整理", "Anker", "テレワーク"],
    },
    {
        "asin": "B0C5D2S476",
        "name": "バッファロー 外付けSSD 1TB 小型",
        "url": f"https://www.amazon.co.jp/dp/B0C5D2S476/?tag={_TAG}",
        "keywords": ["SSD", "外付けSSD", "PC周辺機器", "テレワーク"],
    },
    {
        "asin": "B085698Z8H",
        "name": "イトーキ サリダ YL9 オフィスチェア",
        "url": f"https://www.amazon.co.jp/dp/B085698Z8H/?tag={_TAG}",
        "keywords": ["オフィスチェア", "テレワーク", "腰痛対策", "デスク環境"],
    },
    {
        "asin": "B005UIF2D4",
        "name": "キングジム デスクマット レザフェス",
        "url": f"https://www.amazon.co.jp/dp/B005UIF2D4/?tag={_TAG}",
        "keywords": ["デスクマット", "デスク周り", "テレワーク", "インテリア"],
    },
    {
        "asin": "B0BVMN9H6D",
        "name": "スイッチボット Hub 2",
        "url": f"https://www.amazon.co.jp/dp/B0BVMN9H6D/?tag={_TAG}",
        "keywords": ["スマートホーム", "スマート家電", "Alexa", "IoT"],
    },
    {
        "asin": "B07B959W3D",
        "name": "コクヨ バッグインバッグ カハ-BR31D",
        "url": f"https://www.amazon.co.jp/dp/B07B959W3D/?tag={_TAG}",
        "keywords": ["バッグインバッグ", "収納", "ビジネスバッグ", "整理整頓"],
        "category": "gadget",
    },

    # === 日用品・節約グッズ（一人暮らし向け定番品）===
    # ※ ASIN はAmazon商品ページのURLから確認可能（/dp/{ASIN}/）。
    #   実際の商品リンクで動作確認後に差し替えてください。
    {
        "asin": "B07BHHQGMC",
        "name": "アース製薬 ブラックキャップ ゴキブリ駆除剤 12個入",
        "url": f"https://www.amazon.co.jp/dp/B07BHHQGMC/?tag={_TAG}",
        "keywords": ["ゴキブリ対策", "害虫駆除", "一人暮らし", "防虫"],
        "category": "daily",
    },
    {
        "asin": "B09MBSHZRZ",
        "name": "SANEI 節水シャワーヘッド 低水圧対応 PS303-80XA",
        "url": f"https://www.amazon.co.jp/dp/B09MBSHZRZ/?tag={_TAG}",
        "keywords": ["節水", "シャワーヘッド", "水道代節約", "一人暮らし"],
        "category": "daily",
    },
    {
        "asin": "B07TCDFLJ6",
        "name": "激落ちくん メラミンスポンジ 徳用 40個入",
        "url": f"https://www.amazon.co.jp/dp/B07TCDFLJ6/?tag={_TAG}",
        "keywords": ["掃除", "メラミンスポンジ", "節約", "キッチン"],
        "category": "daily",
    },
    {
        "asin": "B08PQWQBW3",
        "name": "山善 電気毛布 掛け敷き兼用 188×130cm",
        "url": f"https://www.amazon.co.jp/dp/B08PQWQBW3/?tag={_TAG}",
        "keywords": ["電気毛布", "節電", "暖房費節約", "冬"],
        "category": "daily",
    },
    {
        "asin": "B08L8FVLH6",
        "name": "サニパック ニオイが2週間逃げない袋 Lサイズ 20枚",
        "url": f"https://www.amazon.co.jp/dp/B08L8FVLH6/?tag={_TAG}",
        "keywords": ["ゴミ袋", "消臭", "一人暮らし", "生活用品"],
        "category": "daily",
    },
    {
        "asin": "B074RDMXL2",
        "name": "CB Japan 珪藻土バスマット Lサイズ",
        "url": f"https://www.amazon.co.jp/dp/B074RDMXL2/?tag={_TAG}",
        "keywords": ["珪藻土", "バスマット", "一人暮らし", "快適グッズ"],
        "category": "daily",
    },
    {
        "asin": "B0098XCVEY",
        "name": "ライオン トップ スーパーNANOX 液体洗剤 詰め替え 大容量",
        "url": f"https://www.amazon.co.jp/dp/B0098XCVEY/?tag={_TAG}",
        "keywords": ["洗濯洗剤", "コスパ", "日用品", "節約"],
        "category": "daily",
    },
    {
        "asin": "B08F3ZJBR7",
        "name": "山崎実業 tower マグネット折り畳みフック 2個組",
        "url": f"https://www.amazon.co.jp/dp/B08F3ZJBR7/?tag={_TAG}",
        "keywords": ["収納", "フック", "一人暮らし", "整理整頓"],
        "category": "daily",
    },
    {
        "asin": "B08JKFFLWR",
        "name": "パナソニック 電動歯ブラシ ドルツ EW-DM62",
        "url": f"https://www.amazon.co.jp/dp/B08JKFFLWR/?tag={_TAG}",
        "keywords": ["電動歯ブラシ", "健康", "コスパ", "デンタルケア"],
        "category": "daily",
    },
    {
        "asin": "B07PQGTZ3B",
        "name": "アイリスオーヤマ LED シーリングライト 〜8畳 調光タイプ",
        "url": f"https://www.amazon.co.jp/dp/B07PQGTZ3B/?tag={_TAG}",
        "keywords": ["シーリングライト", "LED", "節電", "一人暮らし"],
        "category": "daily",
    },

    # === キッチン家電・調理器具 ===
    {
        "asin": "B08MBZ6CLB",
        "name": "象印 電気ケトル 0.8L 60秒沸騰 CK-AX08",
        "url": f"https://www.amazon.co.jp/dp/B08MBZ6CLB/?tag={_TAG}",
        "keywords": ["電気ケトル", "時短", "一人暮らし", "キッチン家電"],
        "category": "kitchen",
    },
    {
        "asin": "B07R4PN9D5",
        "name": "T-fal フライパン 26cm IH対応 テフロン加工",
        "url": f"https://www.amazon.co.jp/dp/B07R4PN9D5/?tag={_TAG}",
        "keywords": ["フライパン", "T-fal", "IH対応", "一人暮らし"],
        "category": "kitchen",
    },
    {
        "asin": "B08L8QTHMQ",
        "name": "アイリスオーヤマ 炊飯器 3合 マイコン式 RC-ME30",
        "url": f"https://www.amazon.co.jp/dp/B08L8QTHMQ/?tag={_TAG}",
        "keywords": ["炊飯器", "一人暮らし", "コスパ", "キッチン家電"],
        "category": "kitchen",
    },
    {
        "asin": "B0753LHJHL",
        "name": "ニトリ まな板 抗菌 Lサイズ 食洗機対応",
        "url": f"https://www.amazon.co.jp/dp/B0753LHJHL/?tag={_TAG}",
        "keywords": ["まな板", "抗菌", "食洗機対応", "キッチン用品"],
        "category": "kitchen",
    },
    {
        "asin": "B08B4SNMTV",
        "name": "レコルト ミニライスクッカー 1〜2合 一人暮らし向け",
        "url": f"https://www.amazon.co.jp/dp/B08B4SNMTV/?tag={_TAG}",
        "keywords": ["ライスクッカー", "一人暮らし", "コンパクト", "時短"],
        "category": "kitchen",
    },
    {
        "asin": "B07X2NKSZS",
        "name": "Panasonic 電子レンジ NE-FL222 17L フラットテーブル",
        "url": f"https://www.amazon.co.jp/dp/B07X2NKSZS/?tag={_TAG}",
        "keywords": ["電子レンジ", "一人暮らし", "パナソニック", "キッチン家電"],
        "category": "kitchen",
    },
    {
        "asin": "B09W2ML9JJ",
        "name": "山善 電気圧力鍋 1.5L YPC-M15 レシピ付き",
        "url": f"https://www.amazon.co.jp/dp/B09W2ML9JJ/?tag={_TAG}",
        "keywords": ["電気圧力鍋", "時短料理", "自炊", "コスパ"],
        "category": "kitchen",
    },

    # === PC・デスク環境 ===
    {
        "asin": "B07FN3XKWF",
        "name": "Logicool K380 マルチデバイスBluetoothキーボード",
        "url": f"https://www.amazon.co.jp/dp/B07FN3XKWF/?tag={_TAG}",
        "keywords": ["キーボード", "Logicool", "テレワーク", "マルチデバイス"],
        "category": "gadget",
    },
    {
        "asin": "B08F7N5DRX",
        "name": "UGREEN USB-C ハブ 7-in-1 4K HDMI PD100W",
        "url": f"https://www.amazon.co.jp/dp/B08F7N5DRX/?tag={_TAG}",
        "keywords": ["USBハブ", "MacBook", "テレワーク", "PC周辺機器"],
        "category": "gadget",
    },
    {
        "asin": "B0B2F4QRSZ",
        "name": "Anker 778 USB-C ドッキングステーション 12-in-1",
        "url": f"https://www.amazon.co.jp/dp/B0B2F4QRSZ/?tag={_TAG}",
        "keywords": ["ドッキングステーション", "テレワーク", "Anker", "デスク環境"],
        "category": "gadget",
    },
    {
        "asin": "B075ZYG89B",
        "name": "エルゴトロン LX デスクマウント モニターアーム 白",
        "url": f"https://www.amazon.co.jp/dp/B075ZYG89B/?tag={_TAG}",
        "keywords": ["モニターアーム", "デスク環境", "テレワーク", "姿勢改善"],
        "category": "gadget",
    },
    {
        "asin": "B08HH9YWQL",
        "name": "BenQ ScreenBar モニターライト クランプ式",
        "url": f"https://www.amazon.co.jp/dp/B08HH9YWQL/?tag={_TAG}",
        "keywords": ["モニターライト", "デスク環境", "目の疲れ", "テレワーク"],
        "category": "gadget",
    },
    {
        "asin": "B07H5GKNZB",
        "name": "サンワサプライ ノートPCスタンド 折りたたみ アルミ",
        "url": f"https://www.amazon.co.jp/dp/B07H5GKNZB/?tag={_TAG}",
        "keywords": ["ノートPCスタンド", "テレワーク", "姿勢改善", "デスク環境"],
        "category": "gadget",
    },

    # === スマートホーム・IoT ===
    {
        "asin": "B09B2JQ7KF",
        "name": "SwitchBot 温湿度計プラス 大画面 アラート機能",
        "url": f"https://www.amazon.co.jp/dp/B09B2JQ7KF/?tag={_TAG}",
        "keywords": ["温湿度計", "スマートホーム", "SwitchBot", "快適生活"],
        "category": "gadget",
    },
    {
        "asin": "B07WLCP7SV",
        "name": "SwitchBot スマートロック 鍵 スマホで操作",
        "url": f"https://www.amazon.co.jp/dp/B07WLCP7SV/?tag={_TAG}",
        "keywords": ["スマートロック", "鍵", "スマートホーム", "防犯"],
        "category": "gadget",
    },
    {
        "asin": "B09JQMJHXY",
        "name": "Echo Dot 第5世代 スマートスピーカー with Alexa",
        "url": f"https://www.amazon.co.jp/dp/B09JQMJHXY/?tag={_TAG}",
        "keywords": ["Echo Dot", "Alexa", "スマートホーム", "音楽"],
        "category": "gadget",
    },
    {
        "asin": "B08CXWRRN2",
        "name": "Fire TV Stick 4K Max ストリーミングメディアプレイヤー",
        "url": f"https://www.amazon.co.jp/dp/B08CXWRRN2/?tag={_TAG}",
        "keywords": ["Fire TV Stick", "動画配信", "テレビ", "Netflix"],
        "category": "gadget",
    },

    # === モバイル・充電系 ===
    {
        "asin": "B07FZ8S74R",
        "name": "Anker PowerCore 10000 モバイルバッテリー 大容量",
        "url": f"https://www.amazon.co.jp/dp/B07FZ8S74R/?tag={_TAG}",
        "keywords": ["モバイルバッテリー", "Anker", "大容量", "スマホ充電"],
        "category": "gadget",
    },
    {
        "asin": "B09PNBQCS9",
        "name": "Anker 543 USB-C ケーブル 1.8m 100W急速充電",
        "url": f"https://www.amazon.co.jp/dp/B09PNBQCS9/?tag={_TAG}",
        "keywords": ["USB-Cケーブル", "急速充電", "Anker", "充電アクセサリー"],
        "category": "gadget",
    },
    {
        "asin": "B08D7GWH5D",
        "name": "Anker 511 Charger Nano 20W USB-C 超小型",
        "url": f"https://www.amazon.co.jp/dp/B08D7GWH5D/?tag={_TAG}",
        "keywords": ["充電器", "コンパクト", "iPhone", "USB-C"],
        "category": "gadget",
    },

    # === 健康・フィットネス ===
    {
        "asin": "B07R1YB2XZ",
        "name": "タニタ 体重計 BC-768 体組成計 スマホ連携",
        "url": f"https://www.amazon.co.jp/dp/B07R1YB2XZ/?tag={_TAG}",
        "keywords": ["体重計", "体組成計", "健康管理", "タニタ"],
        "category": "health",
    },
    {
        "asin": "B091J3HNKZ",
        "name": "フィリップス 電動歯ブラシ ソニッケアー 3100",
        "url": f"https://www.amazon.co.jp/dp/B091J3HNKZ/?tag={_TAG}",
        "keywords": ["電動歯ブラシ", "ホワイトニング", "健康", "デンタルケア"],
        "category": "health",
    },
    {
        "asin": "B09NXK1BPS",
        "name": "オムロン 血圧計 上腕式 HEM-7142T2 スマホ連携",
        "url": f"https://www.amazon.co.jp/dp/B09NXK1BPS/?tag={_TAG}",
        "keywords": ["血圧計", "健康管理", "オムロン", "スマホ連携"],
        "category": "health",
    },
    {
        "asin": "B07PMQVZHB",
        "name": "ALPHAX ストレッチポール EX ブラック",
        "url": f"https://www.amazon.co.jp/dp/B07PMQVZHB/?tag={_TAG}",
        "keywords": ["ストレッチポール", "腰痛対策", "テレワーク", "健康"],
        "category": "health",
    },
    {
        "asin": "B08RCT4Y8J",
        "name": "マイプロテイン Impact ホエイプロテイン 1kg バニラ",
        "url": f"https://www.amazon.co.jp/dp/B08RCT4Y8J/?tag={_TAG}",
        "keywords": ["プロテイン", "筋トレ", "コスパ", "健康"],
        "category": "health",
    },

    # === 収納・インテリア ===
    {
        "asin": "B07YCWFWRR",
        "name": "IKEA フェルゴ ボックス 収納 3個セット",
        "url": f"https://www.amazon.co.jp/dp/B07YCWFWRR/?tag={_TAG}",
        "keywords": ["収納ボックス", "インテリア", "整理整頓", "一人暮らし"],
        "category": "daily",
    },
    {
        "asin": "B0829TK9LL",
        "name": "平安伸銅工業 突っ張り棒 強力タイプ 耐荷重30kg",
        "url": f"https://www.amazon.co.jp/dp/B0829TK9LL/?tag={_TAG}",
        "keywords": ["突っ張り棒", "収納", "一人暮らし", "DIY収納"],
        "category": "daily",
    },
    {
        "asin": "B07BPKL7BZ",
        "name": "Seria ワイヤーバスケット 収納 積み重ね",
        "url": f"https://www.amazon.co.jp/dp/B07BPKL7BZ/?tag={_TAG}",
        "keywords": ["ワイヤーバスケット", "収納", "インテリア", "100均"],
        "category": "daily",
    },

    # === 睡眠・リラックス ===
    {
        "asin": "B08XWQFPQ6",
        "name": "西川 エアー 01 ベーシック マットレス セミダブル",
        "url": f"https://www.amazon.co.jp/dp/B08XWQFPQ6/?tag={_TAG}",
        "keywords": ["マットレス", "睡眠改善", "腰痛対策", "一人暮らし"],
        "category": "daily",
    },
    {
        "asin": "B078GVNHLS",
        "name": "アイリスオーヤマ 低反発枕 43×63cm 高さ調整可能",
        "url": f"https://www.amazon.co.jp/dp/B078GVNHLS/?tag={_TAG}",
        "keywords": ["枕", "低反発", "睡眠", "首こり対策"],
        "category": "daily",
    },
    {
        "asin": "B09T8MJLYH",
        "name": "山善 加湿器 超音波式 木目調 アロマ対応",
        "url": f"https://www.amazon.co.jp/dp/B09T8MJLYH/?tag={_TAG}",
        "keywords": ["加湿器", "乾燥対策", "インテリア", "冬家電"],
        "category": "daily",
    },

    # === 掃除・生活家電 ===
    {
        "asin": "B08C2ZKDGC",
        "name": "マキタ コードレス掃除機 CL107FDSHW 軽量",
        "url": f"https://www.amazon.co.jp/dp/B08C2ZKDGC/?tag={_TAG}",
        "keywords": ["コードレス掃除機", "マキタ", "軽量", "一人暮らし"],
        "category": "daily",
    },
    {
        "asin": "B01NAFLNSO",
        "name": "ニトムズ コロコロ フロアクリン 本体 + 替えテープ",
        "url": f"https://www.amazon.co.jp/dp/B01NAFLNSO/?tag={_TAG}",
        "keywords": ["コロコロ", "掃除", "ペット", "日用品"],
        "category": "daily",
    },
    {
        "asin": "B09YBK9D9L",
        "name": "アイリスオーヤマ 衣類乾燥除湿機 IJD-I50 梅雨対策",
        "url": f"https://www.amazon.co.jp/dp/B09YBK9D9L/?tag={_TAG}",
        "keywords": ["除湿機", "衣類乾燥", "梅雨", "一人暮らし"],
        "category": "daily",
    },
]


def get_pool_by_category(category: str) -> list:
    """カテゴリで商品をフィルタリングして返す"""
    return [p for p in PRODUCT_POOL if p.get("category") == category]
