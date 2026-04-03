# tiktok-lifehack プロジェクト設定

## プロジェクト概要
SNS自動投稿 × アフィリエイトで月10万円を目指すAIエージェントシステム。
GitHub Actions で1日4回 (8/12/18/22時 JST) に全プラットフォームへ自動投稿。

## 重要コマンド
```bash
# ローカルテスト
python3 money_agent/money_agent.py dry-run     # 記事生成のみ（投稿なし）
python3 money_agent/money_agent.py dashboard   # 収益ダッシュボード確認
python3 x_automation/x_poster.py live          # X投稿テスト
python3 bluesky_automation/bsky_poster.py live # Bluesky投稿テスト

# GitHub Actions
gh run list --limit 5                          # 直近の実行確認
gh run watch                                   # 実行をリアルタイム監視
```

## 収益構造
| プラットフォーム | 役割 | 収益目標 |
|---|---|---|
| はてなブログ | SEO記事 × アフィリエイト | 7万円/月 |
| note | 流入獲得 | 2万円/月 |
| X / Bluesky | SNSシェア | 1万円/月 |
| LINE Bot | ステップ配信 (毎日10時) | 高額商品 |

## アフィリエイト情報
- A8.net アカウント: a26032392970 (お得情報まとめブログ)
- 楽天アフィリエイト mat code: `4AZMKI+BFEJSI+2HOM+BW8O1`
- 主要プログラム: 楽天カード/楽天証券/SBI証券/TOSSY(DMM.com証券)/お名前.com
- keywords_db.py でアフィリエイトリンク管理

## GitHub Secrets（設定済み）
- GEMINI_API_KEY, HATENA_COOKIES, NOTE_COOKIES
- BSKY_HANDLE, BSKY_APP_PASSWORD
- X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET

## 既知の問題・注意点
- はてなブログ/noteはPlaywright (Cookie認証) — Cookieが期限切れになると失敗
- X投稿はtweepy (公式API) 優先 → ブラウザフォールバック
- Playwrightキャッシュあり → 初回実行は遅い
- money_agentのX投稿はx_poster.post_with_tweepy()を使用（x_browser_posterは使わない）

## ファイル変更時の注意
- keywords_db.py 変更後は `get_next_keyword()` の無限再帰防止ロジックを壊さないこと
- sns-post.yml のcron時刻はUTC表記（JST-9時間）
