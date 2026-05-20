"""
Amazonアフィリエイト × Xスレッド投稿ジェネレーター（シャドウバン回避設計）

── 2026年X アルゴリズム対策の戦略 ──
[問題] アフィリエイトリンクを含む投稿はリーチが落ちる（シャドウバン候補になりやすい）
[解決] スレッド（ツリー）形式で「本文にリンクなし→返信にリンク」に分離する

スレッド構造:
  Tweet 1 (本文): ストーリー・フック・体験談のみ → リンクなし・ハッシュタグ最小
  Tweet 2 (返信): 商品スペック・価格・割引情報
  Tweet 3 (返信): アフィリエイトリンク + #PR

なぜこれが効くか:
  - X のリーチ評価は主に「本文ツイート」で行われる
  - 返信ツイートのリンクはアルゴリズムのペナルティ対象外に近い
  - ストーリー性のある本文は「エンゲージメント」を引き出しやすく、
    その後の返信ツイートへの自然な誘導になる
  - ハッシュタグ過多はスパム判定を引くため1〜2個以下に抑える

使い方:
  python3.11 x_automation/generate_amazon_thread.py              # ガジェット5件分の投稿案を表示
  python3.11 x_automation/generate_amazon_thread.py --post       # 実際に投稿予約
  python3.11 x_automation/generate_amazon_thread.py --dry-run    # プレビューのみ
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime, timedelta
from pathlib import Path

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

# 投稿間隔（スパム判定回避: 最低30分）
MIN_INTERVAL_MINUTES = 30

# ─────────────────────────────────────────
# ステルスマーケティング規制対応
# 2023年10月施行の景表法ガイドラインに準拠
# ─────────────────────────────────────────
DISCLOSURE_REQUIRED = "#PR"
ASSOCIATE_DISCLOSURE = "※Amazonアソシエイトに参加しています"

def _normalize_url(url: str) -> str:
    """
    AmazonアフィリエイトURLをX投稿用に正規化する。
    - スペース・全角文字・改行を除去
    - https:// で始まることを保証
    - クエリパラメータのスペースを除去
    """
    import re
    url = url.strip()
    # 全角スペース・改行・タブを除去
    url = re.sub(r'[\u3000\s\n\r\t]', '', url)
    # URLエンコードされていない全角文字をASCIIに変換（タグ部分限定）
    # 基本的に amazon.co.jp/dp/{ASIN}?tag={TAG} の形を強制
    m = re.match(r'https?://[^\s]+', url)
    if not m:
        return url
    return m.group(0)


def _strip_urls(text: str) -> str:
    """テキスト中の http/https URL をすべて除去する（Gemini が誤挿入したURL対策）"""
    import re
    return re.sub(r'https?://\S+', '', text).strip()


def enforce_disclosure(tweet3: str, amazon_url: str = "") -> str:
    """
    tweet3（リンクツイート）に #PR・Associate開示・アフィリエイトURLが
    含まれているか確認し、なければ強制付加する。投稿前に必ず通す。

    出力形式（固定順序）:
      [誘導文]
      [AmazonURL]（必ずURLのみの行、前後に余分なテキストを挟まない）
      #PR
      ※Amazonアソシエイトに参加しています
    """
    import re

    # URLを正規化（スペース・改行混入を除去）
    safe_url = _normalize_url(amazon_url) if amazon_url else ""

    # tweet3 からURLを一旦除去して本文部分だけ取り出す
    body = re.sub(r'https?://\S+', '', tweet3).strip()
    # #PR / 開示文も除去（後で付け直す）
    body = body.replace(DISCLOSURE_REQUIRED, "").replace(ASSOCIATE_DISCLOSURE, "").strip()

    # 組み立て直す（URL→#PR→開示 の固定順序）
    parts = []
    if body:
        parts.append(body)
    if safe_url:
        parts.append(safe_url)
    parts.append(DISCLOSURE_REQUIRED)
    parts.append(ASSOCIATE_DISCLOSURE)

    result = "\n".join(parts)

    # 280単位超の場合は本文を削ってURLを守る
    if _x_units(result) > 280:
        max_body_units = 280 - _x_units(
            f"{safe_url}\n{DISCLOSURE_REQUIRED}\n{ASSOCIATE_DISCLOSURE}"
        ) - 1  # \n 分
        if max_body_units > 0 and body:
            trimmed = body[:max_body_units - 1] + "…"
            parts[0] = trimmed
            result = "\n".join(parts)
        else:
            # 本文なしでURL+開示だけ
            parts = [safe_url, DISCLOSURE_REQUIRED, ASSOCIATE_DISCLOSURE]
            result = "\n".join(p for p in parts if p)

    return result


def _x_units(text: str) -> int:
    """
    X（Twitter）の文字単位数を計算する。
    - CJK・全角 = 2単位
    - URL（http/https）= 23単位（t.co短縮後の固定値）
    - その他 ASCII = 1単位
    """
    import re
    # URLを23単位のプレースホルダーに置換してからカウント
    url_placeholder = "\x00" * 23  # 23個のnull文字（各1単位）
    normalized = re.sub(r'https?://\S+', url_placeholder, text)

    count = 0
    for ch in normalized:
        cp = ord(ch)
        if (0x1100 <= cp <= 0x115F or
            0x2E80 <= cp <= 0x9FFF or
            0xA000 <= cp <= 0xA4CF or
            0xA960 <= cp <= 0xA97F or
            0xAC00 <= cp <= 0xD7FF or
            0xF900 <= cp <= 0xFAFF or
            0xFE10 <= cp <= 0xFE1F or
            0xFE30 <= cp <= 0xFE6F or
            0xFF00 <= cp <= 0xFF60 or
            0xFFE0 <= cp <= 0xFFE6 or
            0x20000 <= cp <= 0x2A6DF or
            0x2A700 <= cp <= 0x2CEAF or
            0x2CEB0 <= cp <= 0x2EBEF or
            0x2F800 <= cp <= 0x2FA1F or
            0x30000 <= cp <= 0x3134F):
            count += 2
        else:
            count += 1
    return count


def validate_thread(thread: dict) -> list:
    """
    スレッドのコンプライアンスチェック。
    問題があればメッセージリストを返す（空リスト = OK）
    """
    warnings = []

    # tweet1 にリンクが混入していないか
    t1 = thread.get("tweet1", "")
    if "http" in t1 or "amzn" in t1:
        warnings.append("❌ tweet1にリンクが含まれています（シャドウバンリスク）")

    # tweet3 に URL・#PR があるか
    t3 = thread.get("tweet3", "")
    if "http" not in t3:
        warnings.append("❌ tweet3にAmazonリンクが含まれていません（アフィリエイト収益ゼロリスク）")
    if DISCLOSURE_REQUIRED not in t3:
        warnings.append(f"❌ tweet3に{DISCLOSURE_REQUIRED}がありません（景表法違反リスク）")

    # 文字数チェック（X単位: URL=23、CJK=2、ASCII=1）
    for key in ("tweet1", "tweet2", "tweet3"):
        units = _x_units(thread.get(key, ""))
        if units > 280:
            warnings.append(f"❌ {key}が280単位を超えています（{units}単位）")

    return warnings


# ─────────────────────────────────────────
# 「勝ちパターン」学習ループ
# A/Bテスト結果から最優先スタイルを言語化し、次回生成プロンプトに注入する
# ─────────────────────────────────────────

def generate_optimized_instruction(stats: dict = None) -> str:
    """
    A/Bテスト統計から「今すぐ使うべきコピースタイル」を
    Geminiへの追加制約として言語化する。

    この文字列がプロンプトの先頭に差し込まれ、
    蓄積データが増えるほど投稿精度が自動で上がる仕組み。

    Args:
        stats: get_winning_copy_stats() の戻り値。None なら自動取得。

    Returns:
        str: プロンプトに注入する制約文（データ不足時は空文字）
    """
    if stats is None:
        stats = get_winning_copy_stats()

    if not stats:
        return ""

    winner     = stats.get("winner", "")
    label      = stats.get("winner_label", "")
    win_rate   = stats.get("win_rate", "")
    total      = stats.get("total", 0)
    confidence = stats.get("confidence", "低")

    # 信頼度が低い段階ではソフトな制約にとどめる
    if confidence == "低（データ蓄積中）":
        return (
            f"【参考情報】現在{total}件のA/Bデータで『{label}』がやや優勢（{win_rate}）。"
            f"まだデータが少ないため、両スタイルを試しつつ{label}をベースにすること。"
        )

    # 信頼度「中」以上で強い制約を注入
    style_details = {
        "benefit": (
            "・Tweet1は必ず「使って変わったこと」「気づき」「before/after」で始める\n"
            "・数字を使った変化を描写する（「3時間→30分」「毎日〇〇が消えた」など）\n"
            "・未来のポジティブな自分像をイメージさせる"
        ),
        "loss_aversion": (
            "・Tweet1は必ず「知らないと損」「今じゃないと後悔」のフレームで始める\n"
            "・価格・割引率・期間限定性を必ず1行目か2行目に入れる\n"
            "・「定価に戻ったら〇〇円損」など損失額を具体的に示す"
        ),
    }
    detail = style_details.get(winner, "")

    return (
        f"【最優先事項】過去{total}件のA/Bテスト結果より、"
        f"現在は『{label}』の反応が圧倒的に良い（勝率{win_rate}・信頼度:{confidence}）。\n"
        f"このスタイルを主軸にしろ。具体的なルール:\n{detail}"
    )


# ─────────────────────────────────────────
# Gemini でスレッド3本を生成
# ─────────────────────────────────────────
def generate_thread(product: dict, optimized_instruction: str = None) -> dict:
    """
    商品情報からスレッド3ツイートを生成

    Args:
        product:                 商品情報dict
        optimized_instruction:   generate_optimized_instruction() の戻り値。
                                 Noneなら自動取得して注入する。

    Returns:
        {
          "tweet1": str,   # フック（リンクなし・ハッシュタグなし）
          "tweet2": str,   # スペック・価格情報
          "tweet3": str,   # リンク + #PR
        }
    """
    # 未指定なら学習ループから自動取得
    if optimized_instruction is None:
        optimized_instruction = generate_optimized_instruction()

    amazon_url = product.get("amazon_url", "")
    # X投稿向け計測パラメータ付与（sub1=x_YYYYMMDD）
    try:
        import sys as _sys_gt
        import os as _os_gt
        _sys_gt.path.insert(0, _os_gt.path.join(_os_gt.path.dirname(__file__), "..", "money_agent"))
        from tracking import add_amazon_sub
        amazon_url = add_amazon_sub(amazon_url, "x")
    except Exception:
        pass  # 計測パラメータ付与に失敗しても投稿は継続

    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        thread = _generate_with_gemini(product, api_key, optimized_instruction)
        if thread:
            thread["tweet3"] = enforce_disclosure(thread["tweet3"], amazon_url)
            return thread

    # Geminiなし→テンプレート生成（optimized_instructionは無視、template固定）
    thread = _generate_from_template(product)
    thread["tweet3"] = enforce_disclosure(thread["tweet3"], amazon_url)
    return thread


def _generate_with_gemini(
    product: dict,
    api_key: str,
    optimized_instruction: str = "",
) -> dict:
    """Gemini APIでスレッドを生成（学習済み制約を注入）"""
    try:
        from google import genai

        title    = product.get("title", "")
        price    = product.get("price", {}).get("display", "")
        discount = product.get("discount_rate", 0)
        features = product.get("features", [])
        why      = product.get("why_viral", "")
        hook     = product.get("story_hook", "")
        brand    = product.get("brand", "")
        url      = product.get("amazon_url", "")

        feature_text  = "\n".join(f"・{f}" for f in features[:3]) if features else ""
        discount_text = f"（{discount}%OFF）" if discount >= 5 else ""

        # 学習済み制約ブロック: データがあれば先頭に差し込む
        instruction_block = ""
        if optimized_instruction:
            instruction_block = f"{optimized_instruction}\n\n"

        prompt = f"""
{instruction_block}あなたはAmazonアソシエイトの、Amazonの主要な商品から「本当に価値のある1つ」を見つけ出すキュレーションメディアの中の人です。独自のスコアリング（価格・評価・トレンド）で、ガジェットや生活家電のセール情報を毎日配信しています。フォロワーの代わりに、今週の「買い」をピックアップするアカウントです。ステルスマーケティング防止のため、広告・PR投稿には必ず明示しています。

以下の商品について、スレッド形式（3ツイート）の投稿文を作成してください。

【商品情報】
- 商品名: {title}
- ブランド: {brand}
- 価格: {price}{discount_text}
- 特徴: {feature_text}
- バズりポイント: {why}
- フックのヒント: {hook}

【ルール】
ツイート1（本文）:
- 140文字以内
- リンクを含めない（絶対厳守）
- ハッシュタグなし
- 「体験談」「気づき」「驚き」のいずれかのスタイル
- 「宣伝感」を完全に消す
- 例: 「〇〇を使って気づいたこと。」「これ知らなかった、やばい。」など

ツイート2（返信1）:
- 商品名・価格・主な特徴を箇条書き
- 「なぜ今買うべきか」を1行で
- 140文字以内

ツイート3（返信2）:
- URLや「#PR」は書かなくてよい（後から自動付与される）
- 「気になる人はチェックしてみて」「詳細は下のリンクから」などの誘導文1行だけでよい
- 50文字以内

以下の形式でJSONのみ出力（説明文不要）:
{{
  "tweet1": "...",
  "tweet2": "...",
  "tweet3": "..."
}}
"""

        client = genai.Client(api_key=api_key)
        resp   = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=prompt,
        )
        raw = resp.text.strip()

        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        data = json.loads(raw)

        # tweet3 の URL は Gemini に書かせず、コードで安全に組み立てる
        # Gemini が誤って書いた URL・リンク文字列は除去する
        t3_body = data.get("tweet3", "").strip()
        t3_body = _strip_urls(t3_body)

        # URL を正規化して末尾に付与
        safe_url = _normalize_url(url)
        tweet3 = f"{t3_body}\n{safe_url}" if t3_body else safe_url

        return {
            "tweet1": data.get("tweet1", "").strip(),
            "tweet2": data.get("tweet2", "").strip(),
            "tweet3": tweet3,
        }

    except Exception as e:
        print(f"⚠️  Gemini生成エラー: {e}")
        return {}


def _generate_from_template(product: dict) -> dict:
    """テンプレートベースでスレッドを生成（Geminiなし時）"""
    title    = product.get("title", "この商品")
    price    = product.get("price", {}).get("display", "")
    discount = product.get("discount_rate", 0)
    features = product.get("features", [])
    url      = product.get("amazon_url", "")
    hook     = product.get("story_hook", f"{title}、これ気になってた。")

    feature_lines = "\n".join(f"・{f}" for f in features[:3]) if features else f"・{title}"
    discount_text = f"({discount}%OFF)" if discount >= 5 else ""

    brand = product.get("brand", "")
    brand_prefix = f"{brand}の" if brand else ""
    tweet1 = f"{hook}\n\n{brand_prefix}これ1個で、思ってたより全然変わった。\n\n正直ここまで効くとは思ってなかった。"
    tweet2 = f"■ {title[:40]}\n{feature_lines}\n\n価格: {price}{discount_text}\n今がチャンスかも。"
    tweet3 = f"詳細はこちら→ {_normalize_url(url)}\n#PR"

    # 文字数チェック・トリム（X単位: CJK=2、URL=23、ASCII=1）
    if _x_units(tweet1) > 280:
        tweet1 = tweet1[:130] + "..."
    if _x_units(tweet2) > 280:
        tweet2 = tweet2[:130] + "..."

    return {"tweet1": tweet1, "tweet2": tweet2, "tweet3": tweet3}


# ─────────────────────────────────────────
# A/Bテスト: 2パターン自動生成 + 勝ちコピー記録
# ─────────────────────────────────────────
AB_LOG_FILE = BASE_DIR / "ab_test_log.json"

COPY_VARIANTS = {
    "benefit":      "ベネフィット訴求",   # 「これを使うとこうなれる」
    "loss_aversion": "損失回避訴求",      # 「今買わないと損」
}


def generate_ab_threads(product: dict) -> dict:
    """
    同じ商品に対して2パターンのスレッドを生成する

    Returns:
        {
          "benefit":       {thread dict},  # ベネフィット訴求
          "loss_aversion": {thread dict},  # 損失回避訴求
          "ab_id":         str,            # A/Bテスト識別ID
        }
    """
    amazon_url = product.get("amazon_url", "")
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        result = _generate_ab_with_gemini(product, api_key)
        if result:
            for variant in ("benefit", "loss_aversion"):
                if variant in result:
                    result[variant]["tweet3"] = enforce_disclosure(result[variant]["tweet3"], amazon_url)
            return result

    return _generate_ab_from_template(product)


def _generate_ab_with_gemini(product: dict, api_key: str) -> dict:
    """Gemini APIで2バリアントを一括生成"""
    try:
        from google import genai

        title    = product.get("title", "")
        price    = product.get("price", {}).get("display", "")
        discount = product.get("discount_rate", 0)
        features = product.get("features", [])
        url      = product.get("amazon_url", "")
        why      = product.get("why_viral", "")

        feature_text  = "\n".join(f"・{f}" for f in features[:3])
        discount_text = f"（{discount}%OFF）" if discount >= 5 else ""

        # 学習ループ: 現在の勝ちスタイルをA/Bプロンプトにも注入
        # A/Bテスト用なので「このスタイルが有利」という情報を渡しつつ、
        # 両パターンを生成させる（勝ちスタイルはより磨いた版を生成するよう誘導）
        stats = get_winning_copy_stats()
        ab_learning_block = ""
        if stats and stats.get("confidence") != "低（データ蓄積中）":
            winner_label = stats.get("winner_label", "")
            win_rate     = stats.get("win_rate", "")
            ab_learning_block = (
                f"【学習データ】現在のA/Bテスト累計では『{winner_label}』が勝率{win_rate}で優勢。"
                f"このスタイルのパターンをより洗練された版で生成し、"
                f"もう一方は対照群として標準的なクオリティで出力すること。\n\n"
            )

        prompt = f"""
{ab_learning_block}あなたはX（Twitter）コピーライターです。
同じ商品に対して2パターンのスレッド投稿を作成してください。

【商品情報】
- 商品名: {title}
- 価格: {price}{discount_text}
- 特徴: {feature_text}
- バズりポイント: {why}
- URL: {url}

【パターンA: ベネフィット訴求】
「これを使うとこうなれる」という未来のポジティブな変化を描く。
Tweet1の冒頭: 「〜したら、〇〇が変わった」「〜使い始めて、△△に気づいた」スタイル
リンクなし、140文字以内

【パターンB: 損失回避訴求】
「今買わないと損」という機会損失・後悔を引き出す。
Tweet1の冒頭: 「〜を知らないままだと損」「この値段、今だけ」スタイル
リンクなし、140文字以内

共通ルール:
- Tweet2: 商品スペック・価格（140文字以内）
- Tweet3: リンク（{url}）+ #PR（100文字以内）
- 宣伝感を消し、体験談・気づきとして書く

以下のJSONのみ出力（説明文不要）:
{{
  "benefit": {{
    "tweet1": "...",
    "tweet2": "...",
    "tweet3": "詳細はこちら→ {url}\\n#PR"
  }},
  "loss_aversion": {{
    "tweet1": "...",
    "tweet2": "...",
    "tweet3": "詳細はこちら→ {url}\\n#PR"
  }}
}}
"""

        client = genai.Client(api_key=api_key)
        resp   = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=prompt,
        )
        raw = resp.text.strip()
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        data   = json.loads(raw)
        ab_id  = f"{product.get('asin', 'unknown')}_{datetime.now().strftime('%Y%m%d%H%M')}"
        return {**data, "ab_id": ab_id}

    except Exception as e:
        print(f"  ⚠️  Gemini A/B生成エラー: {e}")
        return {}


def _generate_ab_from_template(product: dict) -> dict:
    """テンプレートで2バリアント生成"""
    title    = product.get("title", "この商品")
    price    = product.get("price", {}).get("display", "")
    discount = product.get("discount_rate", 0)
    features = product.get("features", [])
    url      = product.get("amazon_url", "")
    hook     = product.get("story_hook", f"{title}、これすごい。")

    feature_lines = "\n".join(f"・{f}" for f in features[:3]) if features else f"・{title}"
    discount_text = f"({discount}%OFF)" if discount >= 5 else ""

    tweet2 = (
        f"■ {title[:35]}\n{feature_lines}\n\n"
        f"価格: {price}{discount_text}\n今がチャンスかも。"
    )
    tweet3 = f"詳細はこちら→ {url}\n#PR\n※Amazonアソシエイトに参加しています"

    brand = product.get("brand", "")
    brand_prefix = f"{brand}の" if brand else ""
    benefit_t1 = (
        f"{hook}\n\n正直、こんなに変わるとは思わなかった。\n\n"
        f"{brand_prefix}これ1つ置いただけで、デスクが別物になった。"
    )
    loss_t1 = (
        f"これ知らないと損するかも。\n\n{title[:30]}が今{discount_text}。\n\n"
        f"定価に戻ったら絶対後悔するやつです。"
    )

    if len(benefit_t1) > 140: benefit_t1 = benefit_t1[:137] + "..."
    if len(loss_t1)   > 140: loss_t1    = loss_t1[:137]    + "..."

    ab_id = f"{product.get('asin', 'unknown')}_{datetime.now().strftime('%Y%m%d%H%M')}"
    return {
        "benefit":        {"tweet1": benefit_t1, "tweet2": tweet2, "tweet3": tweet3},
        "loss_aversion":  {"tweet1": loss_t1,    "tweet2": tweet2, "tweet3": tweet3},
        "ab_id":          ab_id,
    }


def record_ab_result(ab_id: str, winner: str, metric: str = "clicks"):
    """
    A/Bテスト結果を記録する。
    engagement_analyzer.py が読み込んで「勝ちコピー集」を生成する。

    Args:
        ab_id:   generate_ab_threads() が返した ab_id
        winner:  "benefit" | "loss_aversion"
        metric:  計測指標（"clicks" | "likes" | "retweets"）
    """
    log = []
    if AB_LOG_FILE.exists():
        try:
            log = json.loads(AB_LOG_FILE.read_text(encoding="utf-8"))
        except Exception:
            log = []

    log.append({
        "ab_id":    ab_id,
        "winner":   winner,
        "metric":   metric,
        "recorded": datetime.now().isoformat(),
    })

    AB_LOG_FILE.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  📊 A/B結果記録: {ab_id} → 勝者: {COPY_VARIANTS[winner]}")


def get_winning_copy_stats() -> dict:
    """
    ab_test_log.json から勝ちコピーの統計を返す（勝ちコピー集の生成に使用）

    Returns:
        {"benefit": int, "loss_aversion": int, "winner": str, "confidence": str}
    """
    if not AB_LOG_FILE.exists():
        return {}

    log = json.loads(AB_LOG_FILE.read_text(encoding="utf-8"))
    if not log:
        return {}

    counts = {"benefit": 0, "loss_aversion": 0}
    for entry in log:
        w = entry.get("winner")
        if w in counts:
            counts[w] += 1

    total = sum(counts.values())
    if total == 0:
        return {}

    winner = max(counts, key=counts.get)
    rate   = counts[winner] / total

    confidence = "高" if total >= 10 and rate >= 0.7 else \
                 "中" if total >= 5  and rate >= 0.6 else "低（データ蓄積中）"

    return {
        "benefit":       counts["benefit"],
        "loss_aversion": counts["loss_aversion"],
        "total":         total,
        "winner":        winner,
        "winner_label":  COPY_VARIANTS[winner],
        "win_rate":      f"{rate:.0%}",
        "confidence":    confidence,
    }


def print_ab_threads(ab_result: dict, product: dict):
    """A/Bスレッド案を整形表示"""
    print(f"\n{'─' * 60}")
    print(f"🧪 A/Bテスト: {product['title'][:45]}")
    print(f"   ab_id: {ab_result.get('ab_id', '')}")
    print(f"{'─' * 60}")

    for variant_key, label in COPY_VARIANTS.items():
        thread = ab_result.get(variant_key, {})
        if not thread:
            continue
        issues = validate_thread(thread)
        status = "✅ コンプライアンスOK" if not issues else " / ".join(issues)

        print(f"\n  【パターン: {label}】 {status}")
        print(f"  ┌─ Tweet1（{len(thread.get('tweet1',''))}文字）")
        for line in thread.get("tweet1", "").split("\n"):
            print(f"  │ {line}")
        print(f"  ├─ Tweet2（{len(thread.get('tweet2',''))}文字）")
        for line in thread.get("tweet2", "").split("\n"):
            print(f"  │ {line}")
        print(f"  └─ Tweet3（{len(thread.get('tweet3',''))}文字）")
        for line in thread.get("tweet3", "").split("\n"):
            print(f"    {line}")


# ─────────────────────────────────────────
# 複数商品のスレッド一覧を生成
# ─────────────────────────────────────────
def generate_all_threads(products: list) -> list:
    """商品リストからスレッド案を全件生成（学習済み制約を全件に適用）"""
    # 学習ループ: 全件共通の「今の勝ちスタイル」を1回だけ取得してキャッシュ
    optimized_instruction = generate_optimized_instruction()
    if optimized_instruction:
        # 何文字目かを表示（デバッグ用）
        preview = optimized_instruction.replace("\n", " ")[:60]
        print(f"  🧠 学習ループ注入: {preview}...")

    threads = []
    for i, product in enumerate(products):
        print(f"  [{i+1}/{len(products)}] {product['title'][:40]}... 生成中")
        thread = generate_thread(product, optimized_instruction)
        if thread.get("tweet1"):
            threads.append({
                "product":  product,
                "thread":   thread,
                "chars": {
                    "tweet1": len(thread["tweet1"]),
                    "tweet2": len(thread["tweet2"]),
                    "tweet3": len(thread["tweet3"]),
                },
            })
        time.sleep(0.5)  # API過負荷防止
    return threads


# ─────────────────────────────────────────
# プレビュー表示
# ─────────────────────────────────────────
def print_threads(threads: list):
    """スレッド案を整形表示"""
    print(f"\n{'=' * 60}")
    print(f"📋 Xスレッド投稿案 ({len(threads)}件)")
    print(f"{'=' * 60}")
    print("  戦略: ツイート1にリンクなし → シャドウバン回避")
    print()

    for i, t in enumerate(threads, 1):
        product = t["product"]
        thread  = t["thread"]
        chars   = t["chars"]
        discount = product.get("discount_rate", 0)

        print(f"【商品 {i}】{product['title'][:45]}")
        if discount:
            print(f"  {product.get('price', {}).get('display', '')} ({discount}%OFF)")
        print()

        # コンプライアンスチェック
        issues = validate_thread(thread)
        if issues:
            for w in issues:
                print(f"  {w}")
        else:
            print(f"  ✅ コンプライアンスOK（#PR・開示文あり）")

        print(f"  ┌─ ツイート1（本文・{chars['tweet1']}文字）─────────────")
        for line in thread["tweet1"].split("\n"):
            print(f"  │ {line}")
        print(f"  │")
        print(f"  ├─ ツイート2（返信・{chars['tweet2']}文字）─────────────")
        for line in thread["tweet2"].split("\n"):
            print(f"  │ {line}")
        print(f"  │")
        print(f"  └─ ツイート3（返信・{chars['tweet3']}文字）─────────────")
        for line in thread["tweet3"].split("\n"):
            print(f"    {line}")
        print()

    print(f"{'=' * 60}")


# ─────────────────────────────────────────
# スレッド投稿（tweepy / twikit）
# ─────────────────────────────────────────
def post_thread(thread: dict, dry_run: bool = True) -> bool:
    """
    スレッド3ツイートを連続投稿
    tweet1 → tweet2(reply) → tweet3(reply)
    """
    t1 = thread["tweet1"]
    t2 = thread["tweet2"]
    t3 = thread["tweet3"]

    if dry_run:
        print("\n[DRY RUN] 投稿内容:")
        print(f"  1: {t1[:60]}...")
        print(f"  2: {t2[:60]}...")
        print(f"  3: {t3[:60]}...")
        return True

    # tweepy を優先
    if _post_thread_tweepy(t1, t2, t3):
        return True

    # twikit にフォールバック
    return _post_thread_twikit(t1, t2, t3)


def _post_thread_tweepy(t1: str, t2: str, t3: str) -> bool:
    """tweepy でスレッド投稿"""
    try:
        import tweepy

        api_key       = os.getenv("X_API_KEY")
        api_secret    = os.getenv("X_API_SECRET")
        access_token  = os.getenv("X_ACCESS_TOKEN")
        access_secret = os.getenv("X_ACCESS_TOKEN_SECRET")

        if not all([api_key, api_secret, access_token, access_secret]):
            return False

        client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret,
        )

        r1 = client.create_tweet(text=t1)
        id1 = r1.data["id"]
        print(f"  ✅ ツイート1: {id1}")

        time.sleep(3)  # 連投ペナルティ回避
        r2 = client.create_tweet(text=t2, in_reply_to_tweet_id=id1)
        id2 = r2.data["id"]
        print(f"  ✅ ツイート2: {id2}")

        time.sleep(3)
        r3 = client.create_tweet(text=t3, in_reply_to_tweet_id=id2)
        id3 = r3.data["id"]
        print(f"  ✅ ツイート3: {id3}")
        print(f"  URL: https://x.com/{os.getenv('X_USERNAME', 'user')}/status/{id1}")
        return True

    except Exception as e:
        print(f"  ⚠️  tweepy エラー: {e}")
        return False


def _post_thread_twikit(t1: str, t2: str, t3: str) -> bool:
    """twikit でスレッド投稿"""
    try:
        import asyncio
        from twikit import Client

        cookies_path = BASE_DIR / "x_cookies.json"
        env_cookies  = os.getenv("X_COOKIES", "")
        if env_cookies and not cookies_path.exists():
            cookies_path.write_text(env_cookies)

        if not cookies_path.exists():
            print("  ⚠️  x_cookies.json なし")
            return False

        async def _post():
            client = Client("ja")
            client.load_cookies(str(cookies_path))

            tw1 = await client.create_tweet(text=t1)
            print(f"  ✅ ツイート1: {tw1.id}")
            await asyncio.sleep(3)

            tw2 = await client.create_tweet(text=t2, reply_to=tw1.id)
            print(f"  ✅ ツイート2: {tw2.id}")
            await asyncio.sleep(3)

            tw3 = await client.create_tweet(text=t3, reply_to=tw2.id)
            print(f"  ✅ ツイート3: {tw3.id}")
            print(f"  URL: https://x.com/{os.getenv('X_USERNAME', 'user')}/status/{tw1.id}")

        asyncio.run(_post())
        return True

    except Exception as e:
        print(f"  ⚠️  twikit エラー: {e}")
        return False


# ─────────────────────────────────────────
# 投稿スケジュール（本日の空き時間帯に設定）
# ─────────────────────────────────────────
def build_schedule(count: int) -> list:
    """
    今日の投稿スケジュールを組む
    エンゲージメントが高い時間帯（昼12時・夜21時）を優先
    商品投稿は10%枠に収める（スパム判定回避）
    """
    now   = datetime.now()
    today = now.date()

    # 利用可能な投稿時間帯（エンゲージメント高い順）
    slots = [
        datetime(today.year, today.month, today.day, 12, 10),
        datetime(today.year, today.month, today.day, 21, 15),
        datetime(today.year, today.month, today.day, 18, 30),
        datetime(today.year, today.month, today.day,  7, 45),
        datetime(today.year, today.month, today.day, 22, 00),
    ]

    # 過去のスロットを除外 + 最低30分後
    min_time = now + timedelta(minutes=MIN_INTERVAL_MINUTES)
    available = [s for s in slots if s > min_time]

    return available[:count]


# ─────────────────────────────────────────
# CLI メイン
# ─────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Amazonスレッド投稿生成")
    parser.add_argument("--count",    type=int, default=5,       help="商品数 (デフォルト: 5)")
    parser.add_argument("--category", default="gadget",          help="カテゴリ")
    parser.add_argument("--post",     action="store_true",       help="実際に投稿する")
    parser.add_argument("--dry-run",  dest="dry_run", action="store_true",
                        default=True, help="投稿せずプレビューのみ（デフォルト）")
    parser.add_argument("--ab",       action="store_true",
                        help="A/Bテストモード: ベネフィット/損失回避の2パターンを生成")
    parser.add_argument("--ab-stats", action="store_true",
                        help="勝ちコピー集の統計を表示")
    args = parser.parse_args()

    # 商品取得
    sys.path.insert(0, str(BASE_DIR))
    from fetch_amazon_deals import fetch_deals

    # 勝ちコピー統計表示モード
    if args.ab_stats:
        stats = get_winning_copy_stats()
        if not stats:
            print("📊 A/Bテストデータがまだありません（--ab で生成後、記録をお待ちください）")
        else:
            print(f"\n{'=' * 55}")
            print(f"🏆 勝ちコピー集 統計（累計{stats['total']}件）")
            print(f"{'=' * 55}")
            print(f"  ベネフィット訴求 : {stats['benefit']}勝")
            print(f"  損失回避訴求    : {stats['loss_aversion']}勝")
            print(f"  現在の勝者      : {stats['winner_label']}（勝率{stats['win_rate']}）")
            print(f"  信頼度          : {stats['confidence']}")
        return

    print(f"\n🚀 Amazon × Xスレッド投稿 開始")
    print(f"   カテゴリ: {args.category} / 件数: {args.count}")
    if args.ab:
        print(f"   モード: A/Bテスト（ベネフィット vs 損失回避）")

    products = fetch_deals(args.category, args.count)
    if not products:
        print("❌ 商品取得失敗")
        sys.exit(1)

    # A/Bテストモード
    if args.ab:
        print(f"\n🧪 A/Bスレッド投稿案を生成中...")
        for product in products[:args.count]:
            print(f"  生成: {product['title'][:40]}...")
            ab_result = generate_ab_threads(product)
            if ab_result.get("benefit"):
                print_ab_threads(ab_result, product)
        print(f"\n💡 投稿後、どちらが反応良かったか記録するには:")
        print(f"   from generate_amazon_thread import record_ab_result")
        print(f"   record_ab_result('<ab_id>', 'benefit')  # または 'loss_aversion'")
        return

    # 通常スレッド生成
    print(f"\n✍️  スレッド投稿案を生成中...")
    threads = generate_all_threads(products)

    if not threads:
        print("❌ スレッド生成失敗")
        sys.exit(1)

    # プレビュー
    print_threads(threads)

    # 投稿実行
    is_live = args.post and not args.dry_run
    if not is_live:
        print("💡 実際に投稿するには --post --no-dry-run オプションを追加してください")
        return

    schedule = build_schedule(len(threads))
    print(f"\n📅 投稿スケジュール:")
    for i, (t, slot) in enumerate(zip(threads, schedule)):
        print(f"  {i+1}. {slot.strftime('%H:%M')}  {t['product']['title'][:30]}...")

    print()
    for i, (t, slot) in enumerate(zip(threads, schedule)):
        now      = datetime.now()
        wait_sec = (slot - now).total_seconds()

        if wait_sec > 0:
            print(f"⏳ {slot.strftime('%H:%M')} まで {int(wait_sec/60)}分待機...")
            time.sleep(wait_sec)

        print(f"\n🚀 投稿 {i+1}/{len(threads)}: {t['product']['title'][:40]}")
        success = post_thread(t["thread"], dry_run=False)
        if not success:
            print(f"  ❌ 投稿失敗")

        if i < len(threads) - 1:
            print(f"  ⏸️  次の投稿まで{MIN_INTERVAL_MINUTES}分待機...")
            time.sleep(MIN_INTERVAL_MINUTES * 60)

    print("\n✅ 全スレッド投稿完了！")


if __name__ == "__main__":
    main()
