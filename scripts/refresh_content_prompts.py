"""
A8プログラムごとに「ストーリー型投稿プロンプト」を生成して
affiliate_programs.content_prompt カラムに保存する。

スタイル参考: @single_life_lab
  冒頭: 一人暮らしのあるある悩み（2〜3行）
  中間: 商品・サービスが悩みを解決した体験（1〜2行）
  末尾: 生活がどう変わったか・QOL向上（1行）

使い方:
  python scripts/refresh_content_prompts.py
  python scripts/refresh_content_prompts.py --dry-run   # DBに保存しない
  python scripts/refresh_content_prompts.py --limit 5   # 最大5件のみ更新
"""
import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# .env を最優先で読み込む
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from db_client import db
from crawlers.crawler_a8 import _history  # キューではなく全履歴を使う
from money_agent.gemini_client import generate as gemini_generate


def load_programs() -> list:
    """キュー・履歴を合わせた全A8プログラムを返す（重複なし）"""
    seen = set()
    result = []
    for p in _history.list_load():
        key = p.get("ins_id", "")
        if key and key not in seen:
            seen.add(key)
            result.append(p)
    return result


# ── ジャンル別「悩みシナリオ」ヒント ──────────────────────────────
# Gemini に渡す「どんな悩みを冒頭に置くか」のヒント。
# program の hashtags を見てマッチングする。
_GENRE_HINTS: list[tuple[list[str], str]] = [
    (
        ["副業", "在宅ワーク", "フリーランス", "副収入"],
        "毎月の給料だけじゃ心もとない、副収入を作りたいけど何から始めればいいかわからない悩み",
    ),
    (
        ["節税", "確定申告", "経費", "会計", "freee", "マネーフォワード"],
        "確定申告の書類が難しすぎて毎年ギリギリになる、税金の仕組みがよくわからない悩み",
    ),
    (
        ["NISA", "積立", "投資", "iDeCo", "資産運用"],
        "貯金はしてるけど増えない、投資を始めたいが怖くて踏み出せない悩み",
    ),
    (
        ["クレジットカード", "ポイ活", "楽天", "キャッシュレス"],
        "毎月の買い物でポイントをほとんど貯められていない、どのカードを使えばいいか迷っている悩み",
    ),
    (
        ["転職", "就活", "スキルアップ", "キャリア"],
        "今の仕事が合っていない気がするが転職する勇気が出ない、スキルが身についているか不安な悩み",
    ),
    (
        ["保険", "医療保険", "生命保険"],
        "入っている保険が本当に必要なものかわからない、毎月の保険料が高い気がする悩み",
    ),
    (
        ["節約", "生活費", "光熱費", "食費"],
        "毎月お金が貯まらない、節約しようとしてもどこから手をつければいいかわからない悩み",
    ),
    (
        ["ガジェット", "スマホ", "イヤホン", "PC"],
        "テレワーク・作業環境を整えたいが何を買えば正解かわからない、無駄な買い物をしたくない悩み",
    ),
    (
        ["家電", "掃除", "洗濯", "料理", "キッチン"],
        "家事に時間がかかりすぎる、自炊を続けたいが面倒で外食に頼りがちな悩み",
    ),
    (
        ["ブログ", "アフィリエイト", "SEO", "コンテンツ"],
        "ブログを始めたいが書き方がわからない、アクセスが増えない、収益化できるか不安な悩み",
    ),
    (
        ["AI", "ChatGPT", "Gemini", "自動化"],
        "AIツールを使いこなせていない、毎日の作業を効率化したいが何から試せばいいかわからない悩み",
    ),
]

_DEFAULT_HINT = "一人暮らしの生活費・固定費が高くなりがちで、もっとうまくお金を管理したい悩み"


def _match_hint(hashtags: list[str]) -> str:
    for keywords, hint in _GENRE_HINTS:
        for tag in hashtags:
            clean = tag.lstrip("#").strip()
            if any(kw in clean for kw in keywords):
                return hint
    return _DEFAULT_HINT


def _build_story_prompt(name: str, reward: str, hint: str) -> str:
    """Geminiに渡すプロンプト生成用メタプロンプト"""
    return f"""以下の情報をもとに、X（Twitter）投稿用の「ストーリー型プロンプト」を作成してください。

## このプロンプトの目的
Geminiが実際のツイートを生成する際に使う「指示文」です。
生成されるツイートは @single_life_lab スタイルで書かれます。

## @single_life_lab スタイルの構造
1. 冒頭（2〜3行）: 一人暮らしの「あるある悩み」を具体的に描写する
   → 読んだ人が「わかる…」と思うシーンから始める
2. 中間（1〜2行）: {name} を使って悩みが解決した体験を語る
   → 「〇〇だったのに、使ったら△△になった」という変化を見せる
3. 末尾（1行）: 生活がどう変わったか・QOLがどう上がったかを一言で
   → 感情的な変化（「気が楽になった」「時間が浮いた」など）で締める

## サービス情報
- サービス名: {name}
- 特典・報酬: {reward}
- ターゲットの悩み: {hint}

## 出力形式
以下のフォーマットで「ストーリー型Geminiプロンプト」を1つ出力してください。
冒頭の説明や余分な文章は不要です。プロンプト本文だけを出力してください。

---
あなたは一人暮らしの20〜30代男性として、{name}を実際に使った体験をXに投稿します。

【状況】
{hint}

【投稿構造（必ず守る）】
① 冒頭（2〜3行）: 上記の悩みを「一人称の独り言」として具体的に描写する。
   - 「〜が面倒くさい」「〜で困ってた」「〜に気づいてなかった」など等身大の言葉で
   - 数字や具体的なシーンを入れると読まれやすい
② 中間（1〜2行）: {name}を使って状況がどう変わったかを体験談として書く。
   - 「〜したら」「〜を知ってから」という転換で繋ぐ
   - {reward}という条件も自然な文脈で触れる（無理に入れなくていい）
③ 末尾（1行）: 変化後の気持ち・生活の変化を感情的な一言で締める。
   - 「気が楽になった」「時間が浮いた」「もっと早く知りたかった」など

【制約（厳守）】
- 80〜120文字以内（URLとハッシュタグは除く）
- 「おすすめ」「ぜひ」「絶対」「チェック」禁止
- 広告・宣伝っぽい言葉は避け、本音の体験談として書く
- URLとハッシュタグは書かない（後で追加する）
- 本文のみ出力（説明・タイトル不要）
---"""


def main() -> None:
    parser = argparse.ArgumentParser(description="A8プログラムのcontent_promptを更新")
    parser.add_argument("--dry-run", action="store_true", help="DBに保存しない（確認用）")
    parser.add_argument("--limit", type=int, default=0, help="最大処理件数（0=全件）")
    parser.add_argument("--force", action="store_true", help="既存のpromptも上書きする")
    args = parser.parse_args()

    programs = load_programs()
    if not programs:
        print("A8プログラムが見つかりません。")
        return

    print(f"対象プログラム: {len(programs)} 件")

    updated = 0
    skipped = 0

    for i, program in enumerate(programs):
        if args.limit > 0 and updated >= args.limit:
            break

        ins_id = program.get("ins_id", "")
        name   = program.get("name", "")
        reward = program.get("reward", "")
        tags   = program.get("hashtags", [])

        if not ins_id or not name:
            skipped += 1
            continue

        # --force なしで既存promptがある場合はスキップ
        if not args.force and not args.dry_run:
            existing = db.get_content_prompt(ins_id)
            if existing:
                print(f"  [{i+1}] スキップ（既存あり）: {name[:30]}")
                skipped += 1
                continue

        hint   = _match_hint(tags)
        prompt = _build_story_prompt(name, reward, hint)

        print(f"  [{i+1}] 生成中: {name[:40]}")
        print(f"         ヒント: {hint[:50]}...")

        if args.dry_run:
            print(f"         [DRY-RUN] プロンプト生成（保存スキップ）")
            print(f"         --- プロンプト先頭 ---")
            print(prompt[:300] + "...")
            print()
            updated += 1
            continue

        # Gemini にメタプロンプトを渡してストーリー型プロンプトを生成してもらう
        # test_tweet = Geminiが出力した「実際にツイート生成に使うプロンプト本文」
        story_prompt = gemini_generate(prompt, use_cache=False, temperature=0.85)
        if not story_prompt or len(story_prompt.strip()) < 50:
            print(f"         [WARN] Gemini生成失敗 → メタプロンプトをそのまま保存")
            story_prompt = prompt  # フォールバック: メタプロンプトを保存
        else:
            print(f"         生成OK: {story_prompt.strip()[:80]}...")

        db.save_content_prompt(ins_id, story_prompt.strip())
        print(f"         → affiliate_programs.content_prompt に保存: {ins_id[:40]}")
        updated += 1

        # Gemini API レート制限対策
        time.sleep(2)

    print(f"\n完了: {updated} 件更新 / {skipped} 件スキップ")


if __name__ == "__main__":
    main()
