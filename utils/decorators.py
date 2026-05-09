"""
指数バックオフ リトライデコレータ（tenacity ベース）

使い方:
    from utils.decorators import api_retry

    @api_retry("gemini", context="hatena記事生成")
    def call_gemini():
        ...

    @api_retry("bitly", context="shorten")
    def shorten_url(url):
        ...

仕様:
    - リトライ対象エラーを標準出力に記録
    - 最大試行回数到達後は None を返し（例外を上げない）、
      DBの posts テーブルに error_message として「要手動確認」を記録
    - 重複投稿リスクがある関数（tweet1 など）にはデコレータを使わず
      呼び出し元で意図的に 1 回のみ試行すること
"""

import functools
import sys
import logging
from pathlib import Path
from typing import Callable, Any

from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
    RetryError,
    RetryCallState,
)

logger = logging.getLogger(__name__)

# ── API別リトライ設定 ──────────────────────────────────────────
_CONFIGS: dict[str, dict] = {
    "gemini": dict(
        max_attempts=4,
        wait_min=35,
        wait_max=120,
        patterns=["429", "RESOURCE_EXHAUSTED", "503", "500", "UNAVAILABLE"],
    ),
    "x": dict(
        max_attempts=3,
        wait_min=15,
        wait_max=60,
        patterns=["429", "Too Many Requests", "503", "Rate limit", "ConnectionError"],
    ),
    "note": dict(
        max_attempts=3,
        wait_min=10,
        wait_max=60,
        patterns=["429", "503", "500", "ConnectionError", "timeout"],
    ),
    "hatena": dict(
        max_attempts=3,
        wait_min=10,
        wait_max=60,
        patterns=["429", "503", "500", "ConnectionError", "timeout"],
    ),
    "bitly": dict(
        max_attempts=3,
        wait_min=5,
        wait_max=30,
        patterns=["429", "503", "500", "timeout", "Connection", "ConnectionError"],
    ),
    "default": dict(
        max_attempts=3,
        wait_min=10,
        wait_max=60,
        patterns=["429", "503", "500"],
    ),
}


# ── DB記録 ────────────────────────────────────────────────────
def _log_to_db(api: str, context: str, error: str) -> None:
    """全リトライ失敗時に posts テーブルへ「要手動確認」を記録する"""
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from db_client import db
        db.insert_post(
            platform=f"{api}_error",
            post_type="manual_review",
            label=context[:200],
            chars=0,
            text=f"[要手動確認] {error[:300]}",
            success=False,
            error_message=f"[要手動確認] 最大リトライ到達 ({api}): {error}",
        )
    except Exception as e:
        print(f"  [Retry] DBログ記録失敗: {e}")


def _notify_discord(api: str, context: str, error: str) -> None:
    """Gemini など重要APIの全リトライ失敗時に Discord へ通知する"""
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from utils.notifier import notify
        notify(
            f"utils/decorators.py ({api})",
            f"Gemini停止中：テンプレートで代用します" if api == "gemini" else f"{api} 全リトライ失敗",
            f"context={context[:100]} / error={error[:200]}",
        )
    except Exception as e:
        print(f"  [Retry] Discord通知失敗: {e}")


# ── デコレータ本体 ────────────────────────────────────────────
def api_retry(
    api: str = "default",
    context: str = "",
    log_on_giveup: bool = True,
) -> Callable:
    """
    tenacity ベースの指数バックオフ リトライデコレータ。

    Parameters
    ----------
    api           : 設定キー ("gemini" | "x" | "note" | "hatena" | "bitly" | "default")
    context       : ログ・DB記録用のコンテキスト文字列（関数名・処理内容など）
    log_on_giveup : True のとき全失敗後に DB へ記録する
    """
    cfg = _CONFIGS.get(api, _CONFIGS["default"])
    patterns = cfg["patterns"]

    def _is_retryable(exc: BaseException) -> bool:
        """リトライ対象エラーか判定"""
        err = str(exc)
        return any(p in err for p in patterns)

    def _before_sleep(retry_state: RetryCallState) -> None:
        """リトライ前ログ"""
        exc = retry_state.outcome.exception() if retry_state.outcome else None
        attempt = retry_state.attempt_number
        wait = round(retry_state.next_action.sleep if retry_state.next_action else 0, 1)
        err_msg = str(exc)[:120] if exc else "不明なエラー"
        print(
            f"  [Retry/{api}] {wait}秒後にリトライ "
            f"({attempt}/{cfg['max_attempts'] - 1}): {err_msg}"
        )

    def _on_giveup(retry_state: RetryCallState) -> None:
        """全リトライ失敗後の処理"""
        exc = retry_state.outcome.exception() if retry_state.outcome else None
        err_msg = str(exc) if exc else "不明なエラー"
        label = context or (retry_state.fn.__name__ if retry_state.fn else "unknown")
        print(
            f"  [Retry/{api}] 最大試行回数到達。スキップ。"
            f"context={label[:40]} error={err_msg[:100]}"
        )
        if log_on_giveup:
            _log_to_db(api, label, err_msg)
            _notify_discord(api, label, err_msg)

    def decorator(func: Callable) -> Callable:
        # tenacity retry でラップ
        retrying = retry(
            retry=retry_if_exception(_is_retryable),
            stop=stop_after_attempt(cfg["max_attempts"]),
            wait=wait_exponential(
                multiplier=1,
                min=cfg["wait_min"],
                max=cfg["wait_max"],
            ),
            before_sleep=_before_sleep,
            reraise=False,  # RetryError に変換
        )(func)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return retrying(*args, **kwargs)
            except RetryError as re:
                # リトライ対象外エラー or 最大試行到達
                exc = re.last_attempt.exception() if re.last_attempt else re
                err_msg = str(exc) if exc else str(re)
                label = context or func.__name__
                print(
                    f"  [Retry/{api}] 最大試行回数到達。スキップ。"
                    f"context={label[:40]} error={err_msg[:100]}"
                )
                if log_on_giveup:
                    _log_to_db(api, label, err_msg)
                    _notify_discord(api, label, err_msg)
                return None
            except Exception as exc:
                # リトライ対象外エラー（即失敗）
                err_msg = str(exc)
                label = context or func.__name__
                print(f"  [Retry/{api}] リトライ対象外エラー: {err_msg[:120]}")
                if log_on_giveup:
                    _log_to_db(api, label, err_msg)
                return None

        return wrapper

    return decorator
