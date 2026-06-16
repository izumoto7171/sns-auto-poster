"""
Supabase 共通クライアント

すべてのJSON読み書きをこのモジュール経由のDB操作に統一する。
並列実行時のファイル競合を排除し、GitHub Actions の複数ジョブが
同時に走っても整合性を保つ。

使い方:
    from db_client import db

    db.insert_post(platform="x", post_type="useful", ...)
    products = db.get_amazon_deals()

環境変数:
    SUPABASE_URL         — Supabase プロジェクト URL
    SUPABASE_SERVICE_KEY — service_role キー（RLS bypass）
"""

import os
import json
import random
from datetime import datetime, timedelta
from typing import Optional

# 商品プールの最大保持件数（ローリングプール）
_AMAZON_POOL_MAX = 30

# ─────────────────────────────────────────
# モジュールレベル シングルトン
# ─────────────────────────────────────────
_supabase_client = None


def _get_supabase():
    """Supabase クライアントを遅延初期化して返す（シングルトン）"""
    global _supabase_client
    if _supabase_client is None:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY", "")
        if not url or not key:
            raise RuntimeError(
                "SUPABASE_URL と SUPABASE_SERVICE_KEY が未設定です。"
                ".env または GitHub Secrets を確認してください。"
            )
        try:
            from supabase import create_client
            _supabase_client = create_client(url, key)
        except ImportError:
            raise RuntimeError(
                "supabase パッケージが未インストールです。"
                "pip install supabase を実行してください。"
            )
    return _supabase_client


class DBClient:
    """
    Supabase を介した全テーブル操作をラップするクライアント。
    各メソッドは旧 JSON 操作と 1:1 に対応する。
    """

    # =========================================================
    # posts — SNS 投稿ログ (X / Bluesky / はてなブログ / note)
    # =========================================================

    def insert_post(
        self,
        platform: str,
        post_type: str = "",
        label: str = "",
        chars: int = 0,
        text: str = "",
        success: bool = False,
        mode: str = "live",
        has_image: bool = False,
        url: str = "",
        tweet1_id: str = "",
        tweet2_id: str = "",
        tweet3_id: str = "",
        thread_url: str = "",
        dry_run: bool = False,
        error_message: str = "",
        genre: str = "",
        writing_style: str = "",
        posted_at_hour: Optional[int] = None,
        **_kwargs,  # 旧コードからの余分なキーを無視
    ) -> None:
        """投稿ログを1件 INSERT する。失敗時は error_message に詳細を記録。"""
        if posted_at_hour is None:
            posted_at_hour = datetime.now().hour
        row = {
            "platform":        platform,
            "post_type":       post_type,
            "label":           label,
            "chars":           chars,
            "text":            text,
            "success":         success,
            "mode":            mode,
            "has_image":       has_image,
            "url":             url,
            "tweet1_id":       tweet1_id,
            "tweet2_id":       tweet2_id,
            "tweet3_id":       tweet3_id,
            "thread_url":      thread_url,
            "dry_run":         dry_run,
            "error_message":   error_message,
            "genre":           genre,
            "writing_style":   writing_style,
            "posted_at_hour":  posted_at_hour,
            "impression_count": 0,
            "click_count":     0,
            "is_winner":       False,
        }
        # 空文字列は None に変換（Supabase の TEXT 型は空文字でも OK だが NULL の方が意味が明確）
        row = {k: (None if v == "" else v) for k, v in row.items()}
        _get_supabase().table("posts").insert(row).execute()

    def get_pending_analytics_posts(self, hours_min: int = 24, hours_max: int = 48) -> list:
        """
        投稿から hours_min〜hours_max 時間経過かつ impression_count=0 の X 投稿を返す。
        analytics_fetcher.py がアナリティクスを埋めるために使う。
        """
        from datetime import timezone
        now     = datetime.now(timezone.utc)
        dt_min  = (now - timedelta(hours=hours_max)).isoformat()
        dt_max  = (now - timedelta(hours=hours_min)).isoformat()
        rows = (
            _get_supabase()
            .table("posts")
            .select("id, tweet1_id, genre, text, created_at")
            .eq("platform", "x")
            .eq("success", True)
            .eq("impression_count", 0)
            .gte("created_at", dt_min)
            .lte("created_at", dt_max)
            .execute()
            .data
        ) or []
        return rows

    def update_post_analytics(
        self,
        post_id: int,
        impression_count: int,
        click_count: int = 0,
        is_winner: bool = False,
    ) -> None:
        """投稿の impression_count / click_count / is_winner を更新する。"""
        _get_supabase().table("posts").update({
            "impression_count": impression_count,
            "click_count":      click_count,
            "is_winner":        is_winner,
        }).eq("id", post_id).execute()

    def get_winner_posts(self, genre: str = "", limit: int = 5) -> list:
        """
        is_winner=True の成功投稿を返す。few-shot プロンプト注入に使う。
        genre 指定時は同ジャンルを優先し、不足分を全体から補う。
        """
        sb = _get_supabase()
        results: list = []
        if genre:
            rows = (
                sb.table("posts")
                .select("text, genre, writing_style")
                .eq("platform", "x")
                .eq("is_winner", True)
                .eq("genre", genre)
                .order("impression_count", desc=True)
                .limit(limit)
                .execute()
                .data
            ) or []
            results.extend(rows)
        if len(results) < limit:
            remaining = limit - len(results)
            rows = (
                sb.table("posts")
                .select("text, genre, writing_style")
                .eq("platform", "x")
                .eq("is_winner", True)
                .order("impression_count", desc=True)
                .limit(remaining)
                .execute()
                .data
            ) or []
            existing_texts = {r["text"] for r in results}
            for r in rows:
                if r["text"] not in existing_texts:
                    results.append(r)
        return results[:limit]

    def get_winner_genre_counts(self, days: int = 14) -> dict:
        """
        直近 days 日間の is_winner=True 投稿をジャンル別にカウントして返す。
        deal_selector のボーナススコア計算に使う。
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        rows = (
            _get_supabase()
            .table("posts")
            .select("genre")
            .eq("platform", "x")
            .eq("is_winner", True)
            .gte("created_at", cutoff)
            .execute()
            .data
        ) or []
        counts: dict[str, int] = {}
        for r in rows:
            g = r.get("genre") or "unknown"
            counts[g] = counts.get(g, 0) + 1
        return counts

    def get_genre_impression_avg(self, genre: str) -> float:
        """
        指定ジャンルの impression_count 平均値を返す（is_winner 判定の基準値）。
        データが3件未満の場合は 0 を返す。
        """
        rows = (
            _get_supabase()
            .table("posts")
            .select("impression_count")
            .eq("platform", "x")
            .eq("success", True)
            .eq("genre", genre)
            .gt("impression_count", 0)
            .execute()
            .data
        ) or []
        if len(rows) < 3:
            return 0.0
        total = sum(r["impression_count"] for r in rows)
        return total / len(rows)

    def get_posts(self, platform: Optional[str] = None, limit: int = 100) -> list:
        """
        投稿ログを新しい順で取得する。
        旧コードの load_log() → reversed(log) パターンに対応。
        """
        q = (
            _get_supabase()
            .table("posts")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
        )
        if platform:
            q = q.eq("platform", platform)
        rows = q.execute().data or []
        # 旧 JSON の形式（datetime フィールド付き）に揃える
        for r in rows:
            if "created_at" in r and "datetime" not in r:
                r["datetime"] = r["created_at"]
        return rows

    # =========================================================
    # amazon_products — Amazon 商品日次キャッシュ
    # =========================================================

    def get_amazon_deals(self, max_age_hours: float = 6.0) -> list:
        """
        is_active=True の商品をプールから返す。
        - 新しい商品（max_age_hours 以内）が存在する場合: そのバッチから加重ランダムで返す
        - 全商品が古い場合: 空リストを返して再生成をトリガー
        - ローリングプールにより、毎回異なる商品が選ばれやすくなる
        旧コードの load_cache() に相当。
        """
        rows = (
            _get_supabase()
            .table("amazon_products")
            .select("data, intent_score, context_boost, fetched_at")
            .eq("is_active", True)
            .order("fetched_at", desc=True)  # 新しい順に取得
            .execute()
            .data
        ) or []

        if not rows:
            return []

        # 最新バッチの鮮度チェック（最も新しい行の fetched_at を基準にする）
        newest_fetched_at_str = rows[0].get("fetched_at", "")
        if newest_fetched_at_str:
            try:
                newest_fetched_at = datetime.fromisoformat(newest_fetched_at_str.replace("Z", "+00:00"))
                newest_fetched_at = newest_fetched_at.replace(tzinfo=None)
                age_hours = (datetime.now() - newest_fetched_at).total_seconds() / 3600
                if age_hours >= max_age_hours:
                    return []  # 最新バッチも古い → 再生成トリガー
            except Exception:
                pass

        # data JSONB を展開（旧 JSON の dict リストと互換）
        result = []
        for r in rows:
            product = r.get("data") or {}
            if isinstance(product, str):
                product = json.loads(product)
            product["intent_score"]  = r.get("intent_score",  product.get("intent_score",  50))
            product["context_boost"] = r.get("context_boost", product.get("context_boost", 0))
            result.append(product)

        # 加重ランダムシャッフル: intent_score が高いほど先頭に来やすいが、毎回順序が変わる
        # weights = score + 10（最低重みを保証）
        if len(result) > 1:
            weights = [max(p.get("intent_score", 50), 10) for p in result]
            shuffled = []
            pool = list(zip(weights, result))
            while pool:
                w_list = [w for w, _ in pool]
                idx = random.choices(range(len(pool)), weights=w_list, k=1)[0]
                _, product = pool.pop(idx)
                shuffled.append(product)
            result = shuffled

        return result

    def save_amazon_deals(self, products: list) -> None:
        """
        ローリングプール方式で商品を追加する。
        - 既存の全件削除はしない（最大 _AMAZON_POOL_MAX 件を保持）
        - 新商品を INSERT し、プールが上限を超えたら最古の is_active 行を無効化
        旧コードの save_cache() / DEALS_JSON.write_text() に相当。
        """
        sb = _get_supabase()
        now_iso = datetime.now().isoformat()

        # 新商品を INSERT
        for p in products:
            sb.table("amazon_products").insert({
                "data":          p,
                "intent_score":  p.get("intent_score",  50),
                "context_boost": p.get("context_boost", 0),
                "is_active":     True,
                "fetched_at":    p.get("fetched_at", now_iso),
            }).execute()

        # プール件数が上限を超えたら最古のものを無効化
        active_rows = (
            sb.table("amazon_products")
            .select("id, fetched_at")
            .eq("is_active", True)
            .order("fetched_at", desc=False)  # 古い順
            .execute()
            .data
        ) or []

        overflow = len(active_rows) - _AMAZON_POOL_MAX
        if overflow > 0:
            old_ids = [r["id"] for r in active_rows[:overflow]]
            for oid in old_ids:
                sb.table("amazon_products").update({"is_active": False}).eq("id", oid).execute()
            print(f"  [Pool] 古い商品 {overflow}件 を無効化（プール上限={_AMAZON_POOL_MAX}）")

    def deactivate_amazon_product_by_asin(self, asin: str) -> int:
        """
        指定ASINの amazon_products レコードを無効化（is_active=False）する。
        data JSONB フィールド内の asin キーで検索する。

        Returns:
            無効化した件数
        """
        if not asin:
            return 0
        sb = _get_supabase()
        # is_active=True の全商品を取得し、Python側でASINを照合
        rows = (
            sb.table("amazon_products")
            .select("id, data")
            .eq("is_active", True)
            .execute()
            .data
        ) or []

        target_ids = [
            r["id"] for r in rows
            if (r.get("data") or {}).get("asin") == asin
        ]
        for row_id in target_ids:
            sb.table("amazon_products").update(
                {"is_active": False}
            ).eq("id", row_id).execute()

        return len(target_ids)

    def get_last_amazon_deal_age_hours(self) -> Optional[float]:
        """
        最新の amazon_products 行の fetched_at からの経過時間（時間）を返す。
        行がない場合は None。
        旧コードの「同日実行チェック」に相当。
        """
        rows = (
            _get_supabase()
            .table("amazon_products")
            .select("fetched_at")
            .eq("is_active", True)
            .order("fetched_at", desc=True)
            .limit(1)
            .execute()
            .data
        ) or []
        if not rows:
            return None
        fetched_at_str = rows[0].get("fetched_at", "")
        try:
            fetched_at = datetime.fromisoformat(fetched_at_str.replace("Z", "+00:00"))
            fetched_at = fetched_at.replace(tzinfo=None)
            return (datetime.now() - fetched_at).total_seconds() / 3600
        except Exception:
            return None

    # =========================================================
    # keyword_history — キーワード使用履歴
    # =========================================================

    def get_recent_keywords(self, days: int = 14) -> list:
        """
        過去 N 日のキーワード一覧（重複なし）を返す。
        旧コードの get_recent_keywords(history, days) に相当。
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        rows = (
            _get_supabase()
            .table("keyword_history")
            .select("keywords")
            .gte("created_at", cutoff)
            .execute()
            .data
        ) or []
        keywords: set = set()
        for r in rows:
            kws = r.get("keywords", [])
            if isinstance(kws, str):
                kws = json.loads(kws)
            keywords.update(kws)
        return list(keywords)

    def add_keyword_history(self, keywords: list, month: int, season: str) -> None:
        """
        キーワード履歴を1件 INSERT し、30日以上前のエントリを削除する。
        旧コードの add_history_entry() + save_history() に相当。
        """
        sb = _get_supabase()
        sb.table("keyword_history").insert({
            "keywords": keywords,
            "month":    month,
            "season":   season,
        }).execute()
        # 30日以上前のエントリを削除（自動クリーンアップ）
        cutoff = (datetime.now() - timedelta(days=30)).isoformat()
        sb.table("keyword_history").delete().lt("created_at", cutoff).execute()

    # =========================================================
    # static_products — 静的商品マスタ
    # =========================================================

    def get_static_products(self) -> list:
        """
        is_active=True の静的商品を返す。
        旧コードの load_static_products() に相当。
        """
        rows = (
            _get_supabase()
            .table("static_products")
            .select("data")
            .eq("is_active", True)
            .execute()
            .data
        ) or []
        result = []
        for r in rows:
            product = r.get("data") or {}
            if isinstance(product, str):
                product = json.loads(product)
            result.append(product)
        return result

    def save_static_products(self, products: list) -> None:
        """
        既存を無効化し、新しい静的商品リストを INSERT する。
        旧コードの save_static_products() に相当。
        """
        sb = _get_supabase()
        sb.table("static_products").update({"is_active": False}).eq("is_active", True).execute()
        for p in products:
            sb.table("static_products").insert({
                "data":      p,
                "is_active": True,
            }).execute()

    # =========================================================
    # analytics_insights — フィードバック insights（単一行）
    # =========================================================

    def get_insights(self) -> dict:
        """
        feedback_insights を返す。行がなければ空 dict。
        旧コードの load_insights() に相当。
        """
        rows = (
            _get_supabase()
            .table("analytics_insights")
            .select("data")
            .eq("id", 1)
            .execute()
            .data
        ) or []
        if not rows:
            return {}
        data = rows[0].get("data", {})
        if isinstance(data, str):
            data = json.loads(data)
        return data or {}

    def save_insights(self, insights: dict) -> None:
        """
        insights を upsert する（常に id=1 の行を更新）。
        旧コードの save_insights() に相当。
        """
        insights["updated_at"] = datetime.now().isoformat()
        _get_supabase().table("analytics_insights").upsert({
            "id":         1,
            "data":       insights,
            "updated_at": insights["updated_at"],
        }).execute()

    # =========================================================
    # analytics_history — SNS メトリクス累積
    # =========================================================

    def save_analytics_records(self, records: list) -> int:
        """
        既存 ID を除外して新規レコードのみ INSERT する。
        旧コードの save_history() に相当。
        Returns: 新規挿入件数
        """
        if not records:
            return 0
        sb = _get_supabase()
        # 既存 ID を取得
        existing_rows = sb.table("analytics_history").select("id").execute().data or []
        existing_ids = {r["id"] for r in existing_rows}
        new_records = [r for r in records if r.get("id") not in existing_ids]
        for r in new_records:
            sb.table("analytics_history").insert({
                "id":              r.get("id", ""),
                "platform":        r.get("platform", ""),
                "text":            r.get("text", "")[:500],
                "post_created_at": r.get("created_at") or None,
                "likes":           r.get("likes", 0),
                "retweets":        r.get("retweets", 0),
                "replies":         r.get("replies", 0),
                "impressions":     r.get("impressions", 0),
                "reposts":         r.get("reposts", 0),
                "score":           r.get("score", 0),
                "collected_at":    r.get("collected_at", datetime.now().isoformat()),
            }).execute()
        # 古いレコードを削除して 500 件以内に保つ
        total = len(existing_ids) + len(new_records)
        if total > 500:
            # 収集日時が古い順に超過分を削除
            overflow = total - 500
            old_rows = (
                sb.table("analytics_history")
                .select("id")
                .order("collected_at", desc=False)
                .limit(overflow)
                .execute()
                .data
            ) or []
            for row in old_rows:
                sb.table("analytics_history").delete().eq("id", row["id"]).execute()
        return len(new_records)

    def get_analytics_history(self, limit: int = 500) -> list:
        """
        分析履歴を score 降順で返す。
        旧コードの load_history() に相当。
        """
        rows = (
            _get_supabase()
            .table("analytics_history")
            .select("*")
            .order("score", desc=True)
            .limit(limit)
            .execute()
            .data
        ) or []
        # 旧コードの "created_at" キーに揃える
        for r in rows:
            if "post_created_at" in r and "created_at" not in r:
                r["created_at"] = r["post_created_at"] or ""
        return rows

    # =========================================================
    # a8_processed — A8.net 処理済みプログラム
    # =========================================================

    def get_a8_processed_ids(self, program_type: str = "new") -> set:
        """
        処理済みプログラム ID の set を返す。
        旧コードの load_seen() に相当。
        """
        rows = (
            _get_supabase()
            .table("a8_processed")
            .select("program_id")
            .eq("program_type", program_type)
            .execute()
            .data
        ) or []
        return {r["program_id"] for r in rows}

    def mark_a8_processed(self, program_id: str, program_type: str = "new") -> None:
        """
        プログラムを処理済みとしてマークする（UNIQUE 制約で重複無視）。
        旧コードの save_seen() に相当。
        """
        try:
            _get_supabase().table("a8_processed").insert({
                "program_id":   program_id,
                "program_type": program_type,
            }).execute()
        except Exception as e:
            # 重複挿入（UNIQUE 制約違反）は無視
            if "duplicate" not in str(e).lower() and "unique" not in str(e).lower():
                raise

    # =========================================================
    # affiliate_programs — アフィリエイトプログラム管理
    # =========================================================

    def get_affiliate_links(self) -> dict:
        """
        affiliate_links.json 形式の dict を返す。
        """
        rows = (
            _get_supabase()
            .table("affiliate_programs")
            .select("program_id, url, status, note")
            .execute()
            .data
        ) or []
        return {
            r["program_id"]: {
                "url":    r.get("url", ""),
                "status": r.get("status", "pending"),
                "note":   r.get("note", ""),
            }
            for r in rows
        }

    def update_affiliate_link(
        self,
        program_id: str,
        url: str,
        status: str = "active",
        note: str = "",
    ) -> None:
        """アフィリエイトリンクを upsert する。"""
        _get_supabase().table("affiliate_programs").upsert({
            "program_id": program_id,
            "url":        url,
            "status":     status,
            "note":       note,
            "updated_at": datetime.now().isoformat(),
        }).execute()

    def get_content_prompt(self, ins_id: str) -> Optional[str]:
        """
        affiliate_programs.content_prompt を取得する。
        未設定または取得失敗は None を返す。
        """
        try:
            rows = (
                _get_supabase()
                .table("affiliate_programs")
                .select("content_prompt")
                .eq("program_id", ins_id)
                .limit(1)
                .execute()
                .data
            ) or []
            if rows:
                return rows[0].get("content_prompt") or None
        except Exception:
            pass
        return None

    def save_content_prompt(self, ins_id: str, prompt: str) -> None:
        """
        ストーリー型投稿プロンプトを affiliate_programs に保存する。
        既存行は content_prompt のみ update、未存在行は insert。
        """
        sb = _get_supabase()
        now = datetime.now().isoformat()
        existing = sb.table("affiliate_programs").select("program_id").eq("program_id", ins_id).limit(1).execute().data
        if existing:
            sb.table("affiliate_programs").update({
                "content_prompt":    prompt,
                "prompt_updated_at": now,
                "updated_at":        now,
            }).eq("program_id", ins_id).execute()
        else:
            sb.table("affiliate_programs").insert({
                "program_id":        ins_id,
                "content_prompt":    prompt,
                "prompt_updated_at": now,
                "updated_at":        now,
            }).execute()

    # =========================================================
    # revenue_records — 収益トラッカー
    # =========================================================

    def insert_revenue_record(self, entry: dict) -> None:
        """
        収益レコードを1件 INSERT する。
        旧コードの log["posts"].append(entry) + save_log() に相当。
        """
        _get_supabase().table("revenue_records").insert({
            "date":                     entry.get("date", datetime.now().strftime("%Y-%m-%d")),
            "time":                     entry.get("time", ""),
            "platform":                 entry.get("platform", ""),
            "title":                    entry.get("title", ""),
            "keyword":                  entry.get("keyword", ""),
            "category":                 entry.get("category", ""),
            "affiliate_count":          entry.get("affiliate_count", 0),
            "url":                      entry.get("url", ""),
            "estimated_pv_30days":      entry.get("estimated_pv_30days", 0),
            "estimated_revenue_30days": entry.get("estimated_revenue_30days", 0),
        }).execute()

    def get_revenue_records(self, year: Optional[int] = None, month: Optional[int] = None) -> list:
        """
        収益レコードを返す。year/month 指定で月次フィルタ可能。
        旧コードの load_log() に相当。
        """
        q = _get_supabase().table("revenue_records").select("*").order("date", desc=True)
        if year and month:
            start = f"{year}-{month:02d}-01"
            end   = f"{year}-{month:02d}-31"
            q = q.gte("date", start).lte("date", end)
        return q.execute().data or []

    # =========================================================
    # agent_state — money_agent の進捗状態
    # =========================================================

    def get_agent_state(self) -> dict:
        """agent_state.json 相当のデータを返す。"""
        rows = (
            _get_supabase()
            .table("agent_state")
            .select("data")
            .eq("id", 1)
            .execute()
            .data
        ) or []
        if not rows:
            return {}
        data = rows[0].get("data", {})
        if isinstance(data, str):
            data = json.loads(data)
        return data or {}

    def save_agent_state(self, state: dict) -> None:
        """agent_state を upsert する。"""
        _get_supabase().table("agent_state").upsert({
            "id":         1,
            "data":       state,
            "updated_at": datetime.now().isoformat(),
        }).execute()

    # =========================================================
    # pending_tasks — Gemini生成待ちキュー
    # =========================================================

    def push_pending_task(
        self,
        source: str,
        product_key: str,
        raw_data: dict,
        priority: int = 0,
        post_type: str = "x",
    ) -> bool:
        """
        案件をキューに追加する。同一 (source, product_key, post_type) は無視。
        Returns: True=新規追加, False=既存スキップ
        """
        try:
            _get_supabase().table("pending_tasks").insert({
                "source":      source,
                "product_key": product_key,
                "raw_data":    raw_data,
                "priority":    priority,
                "post_type":   post_type,
                "status":      "pending",
            }).execute()
            return True
        except Exception as e:
            if "duplicate" in str(e).lower() or "unique" in str(e).lower():
                return False
            raise

    def pop_pending_batch(
        self,
        n: int = 8,
        source: Optional[str] = None,
        post_type: str = "x",
    ) -> list:
        """
        pending 状態のタスクを最大 n 件取り出し、status を 'processing' に更新して返す。
        priority 降順 → created_at 昇順でフェッチ。
        """
        sb = _get_supabase()
        q = (
            sb.table("pending_tasks")
            .select("*")
            .eq("status", "pending")
            .eq("post_type", post_type)
            .order("priority", desc=True)
            .order("created_at", desc=False)
            .limit(n)
        )
        if source:
            q = q.eq("source", source)
        rows = q.execute().data or []
        if not rows:
            return []
        ids = [r["id"] for r in rows]
        sb.table("pending_tasks").update({
            "status": "processing",
        }).in_("id", ids).execute()
        return rows

    def mark_task_done(self, task_id: int) -> None:
        """タスクを完了済みにマークする。"""
        _get_supabase().table("pending_tasks").update({
            "status":       "done",
            "processed_at": datetime.now().isoformat(),
        }).eq("id", task_id).execute()

    def mark_task_failed(self, task_id: int, error_msg: str) -> None:
        """タスクを失敗としてマークする。error_msg は 500 文字に切り捨て。"""
        _get_supabase().table("pending_tasks").update({
            "status":       "failed",
            "processed_at": datetime.now().isoformat(),
            "error_msg":    error_msg[:500],
        }).eq("id", task_id).execute()

    def count_pending_tasks(self, post_type: str = "x") -> int:
        """pending 状態のタスク件数を返す。"""
        rows = (
            _get_supabase()
            .table("pending_tasks")
            .select("id", count="exact")
            .eq("status", "pending")
            .eq("post_type", post_type)
            .execute()
        )
        return rows.count or 0

    # =========================================================
    # content_cache — Gemini生成済み投稿文の再利用キャッシュ
    # =========================================================

    CONTENT_CACHE_TTL_DAYS = 3  # キャッシュ有効期間（日）

    def get_content_cache(
        self,
        product_key: str,
        post_type: str = "x",
        max_age_days: Optional[int] = None,
    ) -> Optional[str]:
        """
        キャッシュから生成済みテキストを返す。なければ None。
        max_age_days 以上古いエントリは無効とみなす。
        """
        if max_age_days is None:
            max_age_days = self.CONTENT_CACHE_TTL_DAYS
        cutoff = (datetime.now() - timedelta(days=max_age_days)).isoformat()
        rows = (
            _get_supabase()
            .table("content_cache")
            .select("id, generated_text")
            .eq("product_key", product_key)
            .eq("post_type", post_type)
            .gte("created_at", cutoff)
            .limit(1)
            .execute()
            .data
        ) or []
        if not rows:
            return None
        # 使用回数 + 最終使用日時を更新
        _get_supabase().table("content_cache").update({
            "last_used_at": datetime.now().isoformat(),
            "use_count":    rows[0].get("use_count", 0) + 1,
        }).eq("id", rows[0]["id"]).execute()
        return rows[0]["generated_text"]

    def set_content_cache(
        self,
        product_key: str,
        source: str,
        post_type: str,
        generated_text: str,
        metadata: Optional[dict] = None,
    ) -> None:
        """
        生成済みテキストをキャッシュに保存する。
        同一 (product_key, post_type) は上書き（upsert）。
        """
        _get_supabase().table("content_cache").upsert({
            "product_key":    product_key,
            "source":         source,
            "post_type":      post_type,
            "generated_text": generated_text,
            "metadata":       metadata or {},
            "created_at":     datetime.now().isoformat(),
            "last_used_at":   None,
            "use_count":      0,
        }).execute()

    def cleanup_content_cache(self, max_age_days: int = 7) -> int:
        """
        max_age_days より古い・使用回数 0 のキャッシュを削除する。
        Returns: 削除件数
        """
        cutoff = (datetime.now() - timedelta(days=max_age_days)).isoformat()
        result = (
            _get_supabase()
            .table("content_cache")
            .delete()
            .lt("created_at", cutoff)
            .eq("use_count", 0)
            .execute()
        )
        deleted = len(result.data) if result.data else 0
        return deleted

    # ── success_metrics ──────────────────────────────────────────

    def get_success_metrics(self) -> list:
        """success_metrics テーブルの全レコードを返す"""
        rows = (
            _get_supabase()
            .table("success_metrics")
            .select("category, weight_bonus, click_count, impression_count, updated_at")
            .execute()
            .data
        )
        return rows or []

    def get_success_metrics_dict(self) -> dict:
        """category → weight_bonus の辞書を返す（priority 計算用）"""
        rows = self.get_success_metrics()
        return {r["category"]: r["weight_bonus"] for r in rows}

    def upsert_success_metric(
        self,
        category: str,
        weight_bonus: int,
        click_delta: int = 0,
        impression_delta: int = 0,
    ) -> None:
        """
        success_metrics を upsert する。
        既存レコードがあれば click_count / impression_count を加算する。
        """
        sb = _get_supabase()
        existing = (
            sb.table("success_metrics")
            .select("click_count, impression_count")
            .eq("category", category)
            .execute()
            .data
        )
        if existing:
            old = existing[0]
            sb.table("success_metrics").update({
                "weight_bonus":     weight_bonus,
                "click_count":      old["click_count"] + click_delta,
                "impression_count": old["impression_count"] + impression_delta,
                "updated_at":       datetime.utcnow().isoformat(),
            }).eq("category", category).execute()
        else:
            sb.table("success_metrics").insert({
                "category":         category,
                "weight_bonus":     weight_bonus,
                "click_count":      click_delta,
                "impression_count": impression_delta,
                "updated_at":       datetime.utcnow().isoformat(),
            }).execute()


# ─────────────────────────────────────────
# モジュールレベル シングルトン（各スクリプトから `from db_client import db` で使う）
# ─────────────────────────────────────────
db = DBClient()
