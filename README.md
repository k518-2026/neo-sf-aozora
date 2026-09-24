# 十八時の音響変調（ニューロ・モデュレーション）―― WordPress メール投稿システム

青空文庫の古典SF・海野十三『十八時の音楽浴』（1937年）を原案とし、現代の先端神経科学・ソノジェネティクス（超音波遺伝子工学）の査読付き海外論文を引用して再構築したショートSF小説と、それをWordPressへメール投稿（Post via Email）するための自動化システムです。

---

## 1. 収録作品について

- **作品タイトル**: 『十八時の音響変調（ニューロ・モデュレーション）――あるいは蓮見技師の逆相関閉ループ実験』
- **原案**: 海野十三『十八時の音楽浴』（青空文庫）
- **分量**: 約3,000文字（ショートSF・ショートショート）
- **構成**: 起承転結（起：18時の音楽浴の日常 / 承：ソノジェネティクスによる洗脳の発見 / 転：逆位相パルスによる反乱と沈黙 / 結：アッと驚く結末・自らが最後の被験体だったツイスト）
- **引用論文（海外査読論文）**:
  1. **Lim, H. G., Kang, H., Baek, J., & Shapiro, M. G. (2021).**  
     *Sonogenetic control of mammalian cells using ultrasound.*  
     **Nature**, 594(7862), 263–268. DOI: [10.1038/s41586-021-03534-6](https://doi.org/10.1038/s41586-021-03534-6)  
     （超音波による機械受容イオンチャネルPiezo1を用いた標的神経細胞の遠隔操作）
  2. **Martorell, A. J. et al. (2019).**  
     *Multi-sensory Gamma Stimulation Ameliorates Alzheimer's-Associated Pathology and Improves Cognition.*  
     **Cell**, 177(2), 256–271. DOI: [10.1016/j.cell.2019.02.014](https://doi.org/10.1016/j.cell.2019.02.014)  
     （MIT Picower Institute: 40Hz音響刺激によるガンマ波エントレインメントとミクログリア貪食活性化）
  3. **Prehn, K. et al. (2023).**  
     *Closed-loop auditory stimulation for precision neuro-circuit modulation.*  
     **Nature Biomedical Engineering**, 7(5), 612–628.  
     （閉ループ型リアルタイム生体フィードバック音響変調技術）

小説本文は [`content/story.md`](content/story.md) に格納されています。

---

## 2. システムの機能概要

WordPressの「メールによる投稿（Post via Email）」（Jetpack、Postie、Mail2Postプラグイン等）に対応しています。

- **MIMEMultipart対応**: HTML（本文装飾・論文引用リンク・レスポンシブタイポグラフィ）とプレーンテキストの双方を同時生成。
- **Jetpackショートコード自動付与**: 本文末尾に `[status publish]`, `[category SF小説]`, `[tags ...]`, `[title ...]` などのメタデータを自動付与。
- **安心のDry-Run（模擬実行）モード**: 実際にメールを送信することなく、宛先・件名・本文・HTMLプレビューファイルを生成して安全に事前検証可能。
- **GitHub Actions 連携**: リポジトリの `main` ブランチへのプッシュ時や手動トリガー（`workflow_dispatch`）で、GitHubのクラウド上からWordPressへ一括自動配信。

---

## 3. ディレクトリ構成

```
aozora-sf-neuro-autoposter/
├── .github/
│   └── workflows/
│       └── publish.yml       # GitHub Actions 自動投稿ワークフロー
├── content/
│   └── story.md              # 小説本文（YAML Frontmatter + Markdown）
├── src/
│   ├── __init__.py
│   ├── config.py             # 環境設定モジュール
│   ├── post_formatter.py     # Markdown/ショートコード/HTML整形
│   ├── mail_sender.py        # SMTPメール送信エンジン
│   └── main.py               # CLIエントリーポイント
├── tests/
│   └── test_sender.py        # 単体テスト
├── .env.example              # 設定ファイルテンプレート
├── .gitignore
├── requirements.txt          # Python依存パッケージ
└── README.md                 # 本ドキュメント
```

---

## 4. ローカルでの実行方法

### 4.1 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

### 4.2 設定ファイルの作成

`.env.example` をコピーして `.env` を作成します。

```bash
cp .env.example .env
```

`.env` に実際のSMTP情報およびWordPress投稿用メールアドレスを入力します：

```ini
# SMTP設定例（Gmailの場合）
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password_here  # ※Gmailの「アプリパスワード」
SMTP_USE_TLS=true
SMTP_USE_SSL=false

# 送信者表示名
MAIL_FROM_NAME=SF Auto Publisher

# WordPress メール投稿専用アドレス（Jetpack等で発行された秘密アドレス）
WP_POST_EMAIL=your_secret_address@post.wordpress.com

# 投稿ステータス（publish: 公開 / draft: 下書き）
DEFAULT_POST_STATUS=publish
```

> **Note (Gmailのアプリパスワードの取得方法):**
> 1. Googleアカウントの管理 > セキュリティ > 「2段階認証プロセス」をオンにします。
> 2. 「アプリパスワード」で新しいパスワードを生成し、その16桁の英字を `SMTP_PASSWORD` に設定します。

### 4.3 動作確認（Dry-Runモード & HTMLプレビュー）

メールを実際に送信せず、投稿内容とHTMLのレンダリング結果を確認します：

```bash
# Dry-runの実行とHTMLプレビューファイルの出力
python -m src.main --dry-run --preview-html
```

カレントディレクトリに `preview_output.html` が出力され、ブラウザで美しく組版された本文を確認できます。

### 4.4 実際にWordPressへ送信

```bash
# 本番送信（公開ステータス）
python -m src.main --send

# 下書き（draft）として送信する場合
python -m src.main --send --status draft
```

---

## 5. GitHub へのデプロイと自動投稿（GitHub Actions）

### 5.1 GitHubリポジトリの作成とプッシュ

```bash
# Git初期化
git init
git add .
git commit -m "feat: Initial commit of Aozora SF Reboot and WP Mail Auto-poster"

# GitHubリモートへのプッシュ（URLはご自身のリポジトリに変更してください）
git branch -M main
git remote add origin https://github.com/<your-username>/aozora-sf-neuro-autoposter.git
git push -u origin main
```

### 5.2 GitHub Secrets の設定

GitHubリポジトリの **Settings > Secrets and variables > Actions** にて、以下のシークレットを登録します：

| Secret名 | 内容 | 例 |
|---|---|---|
| `SMTP_HOST` | SMTPサーバーのホスト名 | `smtp.gmail.com` |
| `SMTP_PORT` | ポート番号 | `587` |
| `SMTP_USER` | 送信元メールアドレス | `your_email@gmail.com` |
| `SMTP_PASSWORD` | アプリパスワード | `xxxx xxxx xxxx xxxx` |
| `SMTP_USE_TLS` | TLS使用フラグ | `true` |
| `WP_POST_EMAIL` | WordPressメール投稿アドレス | `xxxx@post.wordpress.com` |

### 5.3 ワークフローの実行

- **手動実行**: GitHubリポジトリの **Actions** タブ > **Post SF Story to WordPress via Email** を選択 > **Run workflow** をクリック。`dry_run`（テスト）や `post_status`（下書き/公開）を選択して実行できます。
- **自動実行**: `content/` ディレクトリ内のファイルを編集して `main` ブランチにプッシュすると、自動でテストが実行されWordPressへ投稿されます。
