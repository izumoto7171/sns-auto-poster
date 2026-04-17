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
from datetime import datetime, timedelta
from typing import Optional

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
        **_kwargs,  # 旧コードからの余分なキーを無視
    ) -> None:
        """投稿ログを1件 INSERT する。失敗時は error_message に詳細を記録。"""
        row = {
            "platform":      platform,
            "post_type":     post_type,
            "label":         label,
            "chars":         chars,
            "text":          text,
            "success":       success,
            "mode":          mode,
            "has_image":     has_image,
            "url":           url,
            "tweet1_id":     tweet1_id,
            "tweet2_id":     tweet2_id,
            "tweet3_id":     tweet3_id,
            "thread_url":    thread_url,
            "dry_run":       dry_run,
            "error_message": error_message,
        }
        # 空文字列は None に変換（Supabase の TEXT 型は空文字でも OK だが NULL の方が意味が明確）
        row = {k: (None if v == "" else v) for k, v in row.items()}
        _get_supabase().table("posts").insert(row).execute()

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
        is_active=True の商品を intent_score 降順で返す。
        fetched_at が max_age_hours 以上古ければ空リストを返す（再生成トリガー）。
        旧コードの load_cache() に相当。
        """
        rows = (
            _get_supabase()
            .table("amazon_products")
            .select("data, intent_score, context_boost, fetched_at")
            .eq("is_active", True)
            .order("intent_score", desc=True)
            .execute()
            .data
        ) or []

        if not rows:
            return []

        # 鮮度チェック（最初の行の fetched_at を基準にする）
        fetched_at_str = rows[0].get("fetched_at", "")
        if fetched_at_str:
            try:
                fetched_at = datetime.fromisoformat(fetched_at_str.replace("Z", "+00:00"))
                # タイムゾーン非対応 datetime でも比較できるよう offset を除去
                fetched_at = fetched_at.replace(tzinfo=None)
                age_hours = (datetime.now() - fetched_at).total_seconds() / 3600
                if age_hours >= max_age_hours:
                    return []
            except Exception:
                pass

        # data JSONB を展開して返す（旧 JSON の dict リストと互換）
        result = []
        for r in rows:
            product = r.get("data") or {}
            if isinstance(product, str):
                product = json.loads(product)
            # DB に保存されたスコアで上書き
            product["intent_score"]  = r.get("intent_score",  product.get("intent_score",  50))
            product["context_boost"] = r.get("context_boost", product.get("context_boost", 0))
            result.append(product)
        return result

    def save_amazon_deals(self, products: list) -> None:
        """
        既存の is_active 行を無効化し、新商品を INSERT する。
        旧コードの save_cache() / DEALS_JSON.write_text() に相当。
        """
        sb = _get_supabase()
        # 既存を無効化
        sb.table("amazon_products").update({"is_active": False}).eq("is_active", True).execute()
        # 新商品を INSERT
        for p in products:
            sb.table("amazon_products").insert({
                "data":          p,
                "intent_score":  p.get("intent_score",  50),
                "context_boost": p.get("context_boost", 0),
                "is_active":     True,
                "fetched_at":    p.get("fetched_at", datetime.now().isoformat()),
            }).execute()

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


# ─────────────────────────────────────────
# モジュールレベル シングルトン（各スクリプトから `from db_client import db` で使う）
# ─────────────────────────────────────────
db = DBClient()
