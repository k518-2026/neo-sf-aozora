# neo-sf-aozora ―― 青空文庫SF × 先端科学リブート & WordPress メール自動投稿システム

青空文庫に収載されている日本の古典SF・科学奇譚（海野十三、蘭郁二郎、夢野久作、小栗虫太郎など）を原案とし、現代の先端科学技術（Nature, Science, Cell などの海外査読論文）を取り入れて再構築した本格ショートSF小説（約3,000文字）を、**毎日朝4時（JST）**に自動生成して WordPress へメール投稿（Post via Email）する自動化リポジトリです。

過去に投稿した作品履歴をデータベース管理し、**作品の重複を完全に防止**します。

---

## 1. システムの特徴

- ⏰ **毎日朝4時（JST）の全自動実行**:
  - GitHub Actions のスケジューラ（`cron: '0 19 * * *'` = JST 04:00）により、毎朝自動起動。
- 📚 **青空文庫SFマスターカタログ搭載**:
  - 海野十三『十八時の音楽浴』『蠅男』『人造人間事件』『振動魔』、蘭郁二郎『植物人間』『夢鬼』『脳髄手術』、夢野久作『人間レコード』『爆弾太平記』、小栗虫太郎『完全犯罪』『二十世紀鉄仮面』など名作SFを網羅。
- 🔬 **実在する海外トップ査読論文の引用**:
  - Google Gemini API（`gemini-2.5-flash`）を活用し、Nature, Science, Cell, PNAS 等の実在論文（著者・雑誌名・年号・DOI・受容体や数式などのメカニズム）をストーリーの核心技術に論理的に統合。
- 🎭 **起承転結 ＆ アッと驚く結末（ツイスト）**:
  - 約3,000文字の知的でスリリングな本格ショートSF。ラストには読者の認識を覆す衝撃的などんでん返しを必ず配置。
- 🗄️ **過去記事・履歴管理（重複防止）**:
  - 投稿済み作品は `data/history.json` および `data/POSTED_STORIES.md` に永続記録。
  - GitHub Actions 実行完了時に、生成された記事ファイル（`content/*.md`）と履歴データを GitHub リポジトリへ自動で `git commit & push`。
- ✉️ **WordPress メール投稿（Post via Email）**:
  - Jetpack や Postie 等のメール投稿仕様に対応。
  - HTML（洗練されたタイポグラフィ装飾・論文引用リンク）とプレーンテキストをマルチパート送信。
  - `[status publish]`, `[category SF小説]`, `[tags ...]` 等のショートコードを自動付加。
- 🛡️ **安心のDry-Run ＆ HTMLプレビュー機能**:
  - 実際にメールを送信せず、生成結果とHTMLプレビュー（`preview_output.html`）をブラウザで検証可能。

---

## 2. ディレクトリ構成

```
neo-sf-aozora/
├── .github/
│   └── workflows/
│       └── publish.yml       # 毎朝4時実行 ＆ 自動コミットのワークフロー
├── content/
│   └── story.md              # 第1作『十八時の音響変調』（初期収録）
├── data/
│   ├── aozora_catalog.json   # 青空文庫SF作品マスターカタログ（作品・テーマ・先端技術）
│   ├── history.json          # 投稿済み履歴データベース（重複防止管理）
│   └── POSTED_STORIES.md     # 投稿済み作品一覧アーカイブ表
├── src/
│   ├── __init__.py
│   ├── config.py             # 設定管理
│   ├── history_manager.py    # 履歴照合・未投稿作品自動選定・重複防止
│   ├── story_generator.py    # Gemini API による海外論文引用SF自動執筆エンジン
│   ├── post_formatter.py     # Markdown → レスポンシブHTML/ショートコード変換
│   ├── mail_sender.py        # TLS/SSL対応 SMTPメール送信エンジン
│   └── main.py               # CLIエントリーポイント
├── tests/
│   └── test_sender.py        # 単体テストスイート
├── .env.example              # 環境変数設定テンプレート
├── .gitignore
├── requirements.txt
└── README.md
```

---

## 3. GitHub Actions による自動実行と設定

### 3.1 GitHub Secrets の設定

GitHubリポジトリの **Settings > Secrets and variables > Actions** にて、以下のシークレットを登録します：

| Secret名 | 必須 | 内容 | 設定例 |
|---|:---:|---|---|
| `GEMINI_API_KEY` | **推奨** | Google Gemini API キー | `AIzaSy...` |
| `SMTP_HOST` | **必須** | SMTPサーバーのホスト名 | `smtp.gmail.com` |
| `SMTP_PORT` | **必須** | SMTPポート番号 | `587` |
| `SMTP_USER` | **必須** | 送信用メールアドレス | `your_email@gmail.com` |
| `SMTP_PASSWORD` | **必須** | 送信パスワード（Gmailアプリパスワード） | `xxxx xxxx xxxx xxxx` |
| `WP_POST_EMAIL` | **必須** | WordPressメール投稿受信用アドレス | `secret_xxxx@post.wordpress.com` |
| `SMTP_USE_TLS` | 任意 | TLS接続（デフォルト: `true`） | `true` |

### 3.2 動作スケジュール

- **自動実行**: 毎日 **日本時間 午前4時00分**（UTC 19:00）に定期起動します。
- **手動実行（即時テスト）**:
  GitHubの **Actions** タブ > **Daily Neo Aozora Sci-Fi Reboot to WordPress** を選択し、**Run workflow** をクリックします。
  - `dry_run`: `true` を選べばメール送信・履歴コミットを行わずにテストできます。
  - `post_status`: `publish`（公開）または `draft`（下書き）を選択可能。
  - `work_id`: カタログ内の特定の青空文庫作品（例: `unno-fly-man`）を指定して生成・投稿可能。

---

## 4. ローカルでの実行方法

### 4.1 インストールと設定

```powershell
cd e:\GoogleAntigravity\neo-sf-aozora

# パッケージのインストール
pip install -r requirements.txt

# 設定ファイルを作成
copy .env.example .env
```

`.env` に実際の認証情報を入力します：

```ini
GEMINI_API_KEY=AIzaSy...
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
WP_POST_EMAIL=your_secret@post.wordpress.com
DEFAULT_POST_STATUS=publish
```

### 4.2 テスト実行（Dry-Run）

未投稿の作品を自動選定し、メール送信を行わずにHTML出力をブラウザで確認します：

```powershell
python -m src.main --dry-run
```
※出力された `preview_output.html` をブラウザで開いて確認できます。

### 4.3 手動での本番投稿

```powershell
# 自動選定された未投稿作品を生成し、WordPressへメール送信＆履歴更新
python -m src.main --send

# 作品IDを指定して下書きとして送信する場合
python -m src.main --work-id unno-fly-man --status draft --send
```

---

## 5. 投稿済み履歴一覧（アーカイブ）

[`data/POSTED_STORIES.md`](data/POSTED_STORIES.md) にて、過去に投稿された作品と引用論文の一覧を閲覧できます。
自動実行のたびにテーブルが自動更新され、リポジトリにプッシュされます。
