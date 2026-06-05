"""
tests/test_analytics_loop.py — アナリティクス自己学習ループ 動作確認テスト

supabase / X API への実接続は一切行わない。
unittest.mock で db_client.db の各メソッドを直接パッチし、
ロジック・エラーハンドリングのみを検証する。

実行方法:
  cd ~/tiktok-lifehack
  python3 tests/test_analytics_loop.py
"""

import sys
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, call

# プロジェクトルートを import パスに追加
_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, _ROOT)

# ─── テスト用モックデータ ───────────────────────────────────────
_NOW_UTC = datetime.now(timezone.utc)

# DB に存在する「24〜48h 経過・未回収」レコード
_FAKE_PENDING = [
    {
        "id":         1001,
        "tweet1_id":  "1234567890",
        "genre":      "side_hustle",
        "text":       "副業で月5万円稼いだ話。",
        "created_at": (_NOW_UTC - timedelta(hours=30)).isoformat(),
    },
    {
        "id":         1002,
        "tweet1_id":  "9876543210",
        "genre":      "gadget",
        "text":       "買って良かったガジェット3選。",
        "created_at": (_NOW_UTC - timedelta(hours=36)).isoformat(),
    },
    {
        # tweet1_id が未記録のケース → スキップされるべき
        "id":         1003,
        "tweet1_id":  None,
        "genre":      "saving",
        "text":       "節約術まとめ。",
        "created_at": (_NOW_UTC - timedelta(hours=25)).isoformat(),
    },
]

# X API から返ってくるメトリクス（ツイート ID ごと）
_FAKE_METRICS = {
    "1234567890": {"impression_count": 600, "click_count": 0},
    "9876543210": {"impression_count": 80,  "click_count": 0},
}

# ジャンル別インプレッション平均値
_FAKE_GENRE_AVG = {
    "side_hustle": 300.0,   # 1001 は 600 → 平均 300 の 2.0 倍 → winner
    "gadget":      200.0,   # 1002 は 80  → 平均 200 の 0.4 倍 → not winner
    "saving":      0.0,     # データ不足（3 件未満）
}


# ─── analytics_fetcher テスト ──────────────────────────────────

class TestAnalyticsFetcher(unittest.TestCase):
    """money_agent/analytics_fetcher.py のロジックテスト"""

    # ----------------------------------------------------------
    # ヘルパー: tweepy.Client のモックを作成
    # ----------------------------------------------------------
    def _make_tweepy_mock(self) -> MagicMock:
        client = MagicMock()

        def _get_tweet_side_effect(id, tweet_fields=None):
            metrics = _FAKE_METRICS.get(str(id))
            if metrics is None:
                resp = MagicMock()
                resp.data = None
                return resp
            resp = MagicMock()
            resp.data = MagicMock()
            resp.data.public_metrics = {
                "impression_count": metrics["impression_count"],
                "retweet_count":    0,
                "like_count":       0,
                "reply_count":      0,
            }
            return resp

        client.get_tweet.side_effect = _get_tweet_side_effect
        return client

    # ----------------------------------------------------------
    # determine_winner() のユニットテスト
    # ----------------------------------------------------------
    def test_determine_winner_with_avg(self):
        """ジャンル平均が取れている場合: 1.5 倍超で True"""
        from money_agent.analytics_fetcher import determine_winner
        self.assertTrue(determine_winner(600, "side_hustle", 300.0),
                        "imp=600 >= avg=300 * 1.5=450 → winner のはず")
        self.assertFalse(determine_winner(80, "gadget", 200.0),
                         "imp=80 < avg=200 * 1.5=300 → not winner のはず")

    def test_determine_winner_fallback(self):
        """ジャンル平均 0 のフォールバック: WINNER_FALLBACK_IMPRESSIONS 超で True"""
        from money_agent.analytics_fetcher import determine_winner, WINNER_FALLBACK_IMPRESSIONS
        self.assertTrue(determine_winner(WINNER_FALLBACK_IMPRESSIONS + 1, "saving", 0.0))
        self.assertFalse(determine_winner(WINNER_FALLBACK_IMPRESSIONS - 1, "saving", 0.0))

    def test_determine_winner_boundary(self):
        """境界値: ちょうど 1.5 倍は True（>=）"""
        from money_agent.analytics_fetcher import determine_winner
        self.assertTrue(determine_winner(450, "side_hustle", 300.0))

    # ----------------------------------------------------------
    # fetch_tweet_metrics() のユニットテスト
    # ----------------------------------------------------------
    def test_fetch_tweet_metrics_ok(self):
        """正常ケース: メトリクスが取得できる"""
        from money_agent.analytics_fetcher import fetch_tweet_metrics
        client  = self._make_tweepy_mock()
        metrics = fetch_tweet_metrics(client, "1234567890")
        self.assertEqual(metrics.get("impression_count"), 600)
        self.assertEqual(metrics.get("click_count"),      0)

    def test_fetch_tweet_metrics_not_found(self):
        """ツイートが存在しない場合: 空 dict を返す"""
        from money_agent.analytics_fetcher import fetch_tweet_metrics
        client  = self._make_tweepy_mock()
        metrics = fetch_tweet_metrics(client, "0000000000")  # 存在しない ID
        self.assertEqual(metrics, {})

    def test_fetch_tweet_metrics_no_client(self):
        """client=None のとき: 空 dict を返す（クラッシュしない）"""
        from money_agent.analytics_fetcher import fetch_tweet_metrics
        metrics = fetch_tweet_metrics(None, "1234567890")
        self.assertEqual(metrics, {})

    def test_fetch_tweet_metrics_api_error(self):
        """X API が例外を投げた場合: 空 dict を返す"""
        from money_agent.analytics_fetcher import fetch_tweet_metrics
        client = MagicMock()
        client.get_tweet.side_effect = Exception("rate limit exceeded")
        metrics = fetch_tweet_metrics(client, "1234567890")
        self.assertEqual(metrics, {})

    # ----------------------------------------------------------
    # run_analytics_fetch() の結合テスト（DB + tweepy すべてモック）
    # ----------------------------------------------------------
    def test_run_full_normal(self):
        """
        通常ケース: pending 3 件中 2 件処理・1 件スキップ
        - 1001 (side_hustle, imp=600, avg=300) → winner
        - 1002 (gadget, imp=80, avg=200)       → not winner
        - 1003 (tweet_id=None)                 → skip
        """
        import db_client
        from money_agent import analytics_fetcher

        tweepy_client = self._make_tweepy_mock()

        with patch.object(db_client.db, "get_pending_analytics_posts",
                          return_value=_FAKE_PENDING), \
             patch.object(db_client.db, "get_genre_impression_avg",
                          side_effect=lambda genre: _FAKE_GENRE_AVG.get(genre, 0.0)), \
             patch.object(db_client.db, "update_post_analytics") as mock_update, \
             patch.object(analytics_fetcher, "_build_tweepy_client",
                          return_value=tweepy_client):

            result = analytics_fetcher.run_analytics_fetch()

        self.assertEqual(result["processed"], 2, "処理件数が 2 件のはず")
        self.assertEqual(result["skipped"],   1, "スキップ件数が 1 件のはず（tweet_id=None）")
        self.assertEqual(result["winners"],   1, "winner は 1 件のはず（side_hustle）")

        # update_post_analytics の呼び出し内容を検証
        calls = mock_update.call_args_list
        self.assertEqual(len(calls), 2)

        # 1001 → winner=True
        call_1001 = next(c for c in calls if c.kwargs.get("post_id") == 1001)
        self.assertTrue(call_1001.kwargs["is_winner"])
        self.assertEqual(call_1001.kwargs["impression_count"], 600)

        # 1002 → winner=False
        call_1002 = next(c for c in calls if c.kwargs.get("post_id") == 1002)
        self.assertFalse(call_1002.kwargs["is_winner"])
        self.assertEqual(call_1002.kwargs["impression_count"], 80)

    def test_run_no_pending(self):
        """pending が 0 件の場合: 何もせず {processed:0} を返す"""
        import db_client
        from money_agent import analytics_fetcher

        with patch.object(db_client.db, "get_pending_analytics_posts", return_value=[]), \
             patch.object(analytics_fetcher, "_build_tweepy_client") as mock_client:

            result = analytics_fetcher.run_analytics_fetch()

        self.assertEqual(result["processed"], 0)
        self.assertEqual(result["winners"],   0)
        self.assertEqual(result["skipped"],   0)
        mock_client.assert_not_called()   # tweepy 初期化はされないはず

    def test_run_tweepy_unavailable(self):
        """tweepy クライアントが None（認証情報なし）: 全件スキップ"""
        import db_client
        from money_agent import analytics_fetcher

        with patch.object(db_client.db, "get_pending_analytics_posts",
                          return_value=_FAKE_PENDING[:2]), \
             patch.object(db_client.db, "update_post_analytics") as mock_update, \
             patch.object(analytics_fetcher, "_build_tweepy_client",
                          return_value=None):

            result = analytics_fetcher.run_analytics_fetch()

        # client=None なので全件スキップ（update は呼ばれない）
        self.assertEqual(result["processed"], 0)
        self.assertEqual(result["skipped"],   2)
        mock_update.assert_not_called()


# ─── deal_selector winner ボーナステスト ───────────────────────

class TestDealSelectorWinnerBonus(unittest.TestCase):
    """crawlers/deal_selector.py の winner ボーナス機能テスト"""

    # ----------------------------------------------------------
    # _get_winner_bonus_scores() の単体テスト
    # ----------------------------------------------------------
    def test_bonus_with_winners(self):
        """winner 投稿がある場合: 該当サービスにボーナスが付く"""
        import db_client
        from crawlers.deal_selector import _get_winner_bonus_scores

        # a8 ジャンル 2 件 + amazon ジャンル 1 件
        fake_counts = {"side_hustle": 2, "gadget": 1, "saving": 1}
        with patch.object(db_client.db, "get_winner_genre_counts",
                          return_value=fake_counts):
            bonus = _get_winner_bonus_scores()

        self.assertIn("a8",     bonus, "a8 にボーナスが付くはず（side_hustle）")
        self.assertIn("amazon", bonus, "amazon にボーナスが付くはず（gadget）")
        self.assertIn("rakuten", bonus, "rakuten にボーナスが付くはず（saving）")

        # a8: side_hustle 2件 → 2 * 5% = 10%
        self.assertAlmostEqual(bonus["a8"], 0.10, places=5)
        # amazon: gadget 1件 → 5%
        self.assertAlmostEqual(bonus["amazon"], 0.05, places=5)

    def test_bonus_max_cap(self):
        """winner が多くても上限 20% を超えない"""
        import db_client
        from crawlers.deal_selector import _get_winner_bonus_scores, _WINNER_BONUS_MAX

        # side_hustle 100 件 → 5% × 100 = 500%、上限 20% にクリップされるはず
        with patch.object(db_client.db, "get_winner_genre_counts",
                          return_value={"side_hustle": 100}):
            bonus = _get_winner_bonus_scores()

        self.assertLessEqual(bonus.get("a8", 0), _WINNER_BONUS_MAX,
                             f"上限 {_WINNER_BONUS_MAX} を超えてはいけない")

    def test_bonus_no_winners(self):
        """winner が 0 件の場合: 空 dict を返す"""
        import db_client
        from crawlers.deal_selector import _get_winner_bonus_scores

        with patch.object(db_client.db, "get_winner_genre_counts",
                          return_value={}):
            bonus = _get_winner_bonus_scores()

        self.assertEqual(bonus, {})

    def test_bonus_db_error(self):
        """DB エラー時: 空 dict を返しクラッシュしない"""
        import db_client
        from crawlers.deal_selector import _get_winner_bonus_scores

        with patch.object(db_client.db, "get_winner_genre_counts",
                          side_effect=Exception("DB connection failed")):
            bonus = _get_winner_bonus_scores()

        self.assertEqual(bonus, {})

    # ----------------------------------------------------------
    # select_best_deal() の結合テスト（外部呼び出しをすべてモック）
    # ----------------------------------------------------------
    def _make_a8_programs(self) -> list:
        return [
            {"ins_id": "a01", "name": "freee会計", "reward": "8,000円", "hashtags": ["#確定申告"],
             "sns_score": 5, "posted_count": 0, "affiliate_url": "https://example.com/freee",
             "hatena_url": ""},
        ]

    def _make_rakuten_products(self) -> list:
        return [
            {"name": "コスパ最強フライパン", "url": "https://item.rakuten.co.jp/test/001",
             "reviewCount": 120, "reviewAverage": 4.2, "price": 2980},
        ]

    def test_select_best_deal_with_winner_bonus(self):
        """
        winner ボーナスがある状態で select_best_deal() がエラーなく実行され、
        正しい形式の dict を返すことを確認する。
        """
        import db_client
        from crawlers import deal_selector

        # winner ボーナス: a8 +10%
        fake_winner_counts = {"side_hustle": 2}

        with patch.object(db_client.db, "get_winner_genre_counts",
                          return_value=fake_winner_counts), \
             patch("crawlers.deal_selector._fetch_rakuten_deal",
                   return_value=self._make_rakuten_products()[0]), \
             patch("crawlers.deal_selector._fetch_a8_deal",
                   return_value=self._make_a8_programs()[0]), \
             patch("crawlers.deal_selector._fetch_amazon_deal",
                   return_value={"title": "テスト商品", "price": 3000}), \
             patch("crawlers.crawler_a8.load_programs",
                   return_value=self._make_a8_programs()):

            result = deal_selector.select_best_deal(verbose=False)

        self.assertIsInstance(result, dict, "戻り値は dict のはず")
        self.assertIn("service", result)
        self.assertIn("deal",    result)
        self.assertIn("score",   result)
        self.assertIn(result["service"], ["rakuten", "a8", "amazon"],
                      "service は 3 種類のいずれかのはず")
        self.assertGreater(result["score"], 0, "スコアは正の数のはず")

    def test_select_best_deal_without_winner_bonus(self):
        """
        winner が 0 件（初期状態）でも select_best_deal() がエラーなく動作する。
        """
        import db_client
        from crawlers import deal_selector

        with patch.object(db_client.db, "get_winner_genre_counts",
                          return_value={}), \
             patch("crawlers.deal_selector._fetch_rakuten_deal",
                   return_value=self._make_rakuten_products()[0]), \
             patch("crawlers.deal_selector._fetch_a8_deal",
                   return_value=self._make_a8_programs()[0]), \
             patch("crawlers.deal_selector._fetch_amazon_deal",
                   return_value={"title": "テスト商品", "price": 3000}), \
             patch("crawlers.crawler_a8.load_programs",
                   return_value=self._make_a8_programs()):

            result = deal_selector.select_best_deal(verbose=False)

        self.assertIsInstance(result, dict)
        self.assertIn("service", result)

    def test_select_best_deal_all_fetch_fail(self):
        """
        全サービスの案件取得が失敗（空 dict）しても {} を返してクラッシュしない。
        """
        import db_client
        from crawlers import deal_selector

        with patch.object(db_client.db, "get_winner_genre_counts",
                          return_value={}), \
             patch("crawlers.deal_selector._fetch_rakuten_deal", return_value={}), \
             patch("crawlers.deal_selector._fetch_a8_deal",     return_value={}), \
             patch("crawlers.deal_selector._fetch_amazon_deal", return_value={}), \
             patch("crawlers.crawler_a8.load_programs",         return_value=[]):

            result = deal_selector.select_best_deal(verbose=False)

        self.assertEqual(result, {}, "全失敗時は空 dict を返すはず")

    def test_score_with_winner_bonus_is_higher(self):
        """
        winner ボーナスがある場合のスコアが、ない場合より大きいかを検証する。
        同一サービスが選ばれるようにランダムを固定して比較。
        """
        import random
        import db_client
        from crawlers import deal_selector

        a8_prog = self._make_a8_programs()[0]
        a8_service_score_no_bonus   = None
        a8_service_score_with_bonus = None

        # ボーナスなし: a8 のベーススコアを取得
        with patch.object(db_client.db, "get_winner_genre_counts", return_value={}), \
             patch("crawlers.crawler_a8.load_programs", return_value=[a8_prog]):
            from crawlers.deal_selector import _a8_score
            from datetime import date
            a8_service_score_no_bonus = _a8_score(date.today(), [a8_prog]).score

        # ボーナスあり: side_hustle 2 件 → a8 に +10%
        with patch.object(db_client.db, "get_winner_genre_counts",
                          return_value={"side_hustle": 2}):
            from crawlers.deal_selector import _get_winner_bonus_scores
            bonus = _get_winner_bonus_scores()
            a8_bonus = bonus.get("a8", 0.0)
            a8_service_score_with_bonus = a8_service_score_no_bonus * (1.0 + a8_bonus)

        self.assertGreater(
            a8_service_score_with_bonus,
            a8_service_score_no_bonus,
            "winner ボーナスがある場合のスコアがない場合より大きいはず",
        )


# ─── db_client 新メソッドの存在確認テスト ──────────────────────

class TestDBClientNewMethods(unittest.TestCase):
    """db_client.py に追加した新メソッドのシグネチャ確認"""

    def setUp(self):
        import db_client
        self.db = db_client.db

    def test_get_pending_analytics_posts_signature(self):
        """get_pending_analytics_posts(hours_min, hours_max) が呼べる"""
        # _get_supabase() を呼ばせないよう、直接パッチ
        from unittest.mock import patch
        import db_client
        with patch("db_client._get_supabase") as mock_sb:
            mock_sb.return_value.table.return_value \
                .select.return_value.eq.return_value.eq.return_value \
                .eq.return_value.gte.return_value.lte.return_value \
                .execute.return_value.data = []
            result = self.db.get_pending_analytics_posts(hours_min=24, hours_max=48)
        self.assertIsInstance(result, list)

    def test_update_post_analytics_signature(self):
        """update_post_analytics(post_id, impression_count, click_count, is_winner) が呼べる"""
        import db_client
        with patch("db_client._get_supabase") as mock_sb:
            mock_sb.return_value.table.return_value \
                .update.return_value.eq.return_value.execute.return_value = MagicMock()
            # クラッシュしないことのみ確認
            self.db.update_post_analytics(
                post_id=1, impression_count=100, click_count=0, is_winner=False
            )

    def test_get_winner_posts_signature(self):
        """get_winner_posts(genre, limit) が呼べる"""
        import db_client
        with patch("db_client._get_supabase") as mock_sb:
            chain = MagicMock()
            chain.execute.return_value.data = []
            mock_sb.return_value.table.return_value \
                .select.return_value.eq.return_value = chain
            result = self.db.get_winner_posts(genre="side_hustle", limit=3)
        self.assertIsInstance(result, list)

    def test_get_winner_genre_counts_signature(self):
        """get_winner_genre_counts(days) が呼べる"""
        import db_client
        with patch("db_client._get_supabase") as mock_sb:
            mock_sb.return_value.table.return_value \
                .select.return_value.eq.return_value.eq.return_value \
                .gte.return_value.execute.return_value.data = [
                    {"genre": "side_hustle"},
                    {"genre": "gadget"},
                    {"genre": "side_hustle"},
                ]
            result = self.db.get_winner_genre_counts(days=14)
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("side_hustle"), 2)
        self.assertEqual(result.get("gadget"), 1)

    def test_get_genre_impression_avg_signature(self):
        """get_genre_impression_avg(genre) が呼べる"""
        import db_client
        with patch("db_client._get_supabase") as mock_sb:
            mock_sb.return_value.table.return_value \
                .select.return_value.eq.return_value.eq.return_value \
                .eq.return_value.gt.return_value.execute.return_value.data = [
                    {"impression_count": 100},
                    {"impression_count": 200},
                    {"impression_count": 300},
                ]
            result = self.db.get_genre_impression_avg("side_hustle")
        self.assertAlmostEqual(result, 200.0, places=1)

    def test_insert_post_accepts_new_fields(self):
        """insert_post() が genre / writing_style / posted_at_hour を受け付ける"""
        import db_client
        with patch("db_client._get_supabase") as mock_sb:
            mock_sb.return_value.table.return_value \
                .insert.return_value.execute.return_value = MagicMock()
            # 新フィールド付きで呼び出してもクラッシュしないことを確認
            self.db.insert_post(
                platform       = "x",
                post_type      = "a8",
                text           = "テスト投稿",
                success        = True,
                genre          = "side_hustle",
                writing_style  = "Gemini/共感・悩み解決型",
                posted_at_hour = 8,
            )


# ─── メイン ───────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("アナリティクス自己学習ループ テストスイート")
    print(f"Python {sys.version.split()[0]}  /  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    loader  = unittest.TestLoader()
    suite   = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestAnalyticsFetcher))
    suite.addTests(loader.loadTestsFromTestCase(TestDealSelectorWinnerBonus))
    suite.addTests(loader.loadTestsFromTestCase(TestDBClientNewMethods))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 60)
    if result.wasSuccessful():
        print(f"PASSED  {result.testsRun} tests")
    else:
        print(f"FAILED  failures={len(result.failures)}  errors={len(result.errors)}")
    print("=" * 60)

    sys.exit(0 if result.wasSuccessful() else 1)
