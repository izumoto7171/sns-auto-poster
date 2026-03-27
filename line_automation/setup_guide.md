# LINE Bot セットアップガイド

## ステップ1: LINE Developersでチャンネル作成

1. https://developers.line.biz/ にアクセス
2. 「ログイン」→ LINEアカウントでログイン
3. 「プロバイダー作成」→ 名前を入力（例: AI副業情報）
4. 「チャンネル作成」→「Messaging API」を選択
5. 以下を入力:
   - チャンネル名: AI副業情報Bot（など）
   - 業種: 個人
   - チャンネル説明: AI副業情報をお届けします

## ステップ2: 必要な情報をメモ

チャンネル設定から取得:
- **Channel Secret** (Basic settings)
- **Channel Access Token** (Messaging API設定 → 発行)

## ステップ3: .envに追加

```
LINE_CHANNEL_ACCESS_TOKEN=取得したトークン
LINE_CHANNEL_SECRET=取得したシークレット
```

## ステップ4: Webhookの設定

### ローカルテスト（ngrokを使う）

```bash
# ngrokインストール（初回のみ）
brew install ngrok

# ローカルサーバー起動
python3 line_automation/line_bot_server.py server

# 別ターミナルでngrok起動
ngrok http 5000
```

ngrokが表示するURL（例: https://abc123.ngrok.io）をコピーして
LINE Developers → Messaging API設定 → Webhook URLに貼り付け:
```
https://abc123.ngrok.io/callback
```

### 本番運用（Render.comで無料デプロイ）

→ render_deploy.md を参照

## ステップ5: 動作確認

1. LINE Official Account Managerでアカウントを公開
2. QRコードをスキャンして友だち登録
3. ウェルカムメッセージが届けば成功！

## ステップ6: ステップ配信のcron設定

```bash
# 毎日10時にステップ配信
0 10 * * * cd /Users/takumi/tiktok-lifehack && python3 line_automation/line_bot_server.py step >> /tmp/line_step.log 2>&1
```

## ステップ配信の仕組み

- 登録0日目: ウェルカムメッセージ + Day1-1（登録直後）
- 登録1日目: Day1-2（翌日10時）
- 登録2日目: Day2（2日後10時）
- 登録3日目: Day3（3日後10時）
- 登録4日目: Day4（4日後10時）
- 登録5日目: Day5（5日後10時）

## 無料枠について

LINE Messaging APIの無料枠:
- 応答メッセージ（Reply）: 無制限
- プッシュメッセージ（Push）: 200通/月まで無料
- 200通を超えた場合: 約3円/通

※ 最初は200通で十分。月100人登録しても余裕あり。
