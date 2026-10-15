# 📋 分散ローカルLLM 自動作業リスト (`neo-sf-aozora`)

- **会話ID**: `b531d04e-6cb0-4202-9ea3-0056c8e2d7f6`
- **最終同期日時 (JST)**: `2026-10-15T20:15:03`
- **進捗サマリー**: 全 **75** 作品 （完了: **74** / 挿絵待ち: **0** / プロット作成済: **0** / 未着手: **1**）
- **交互執筆モード**: プライマリ **`rtx5060lp:11434`** (`shosetsu`) と セカンダリ **`sff7020:1234`** (`gemma-4-26b-a4b-qat`) が1作ずつ交互に小説執筆を担当します（相手がオフライン時はオンライン側がフェイルオーバー代行）。

## 🖥️ 各ローカルLLM PCの役割分担とノルマ

| PCホスト名 | 役割 (`role`) | エンドポイント / モデル | 1日あたり上限 | 担当作業内容 |
|:---|:---|:---|:---:|:---|
| **`rtx5060lp`** | `writer_primary` | `http://rtx5060lp:11434` (`shosetsu`) | 1 作品 | 【プライマリ執筆】交互担当（奇数枠）で正統派ハードSF小説・技術解説を執筆 (`content/*.md`) |
| **`sff7020`** | `writer_secondary` | `http://sff7020:1234` (`gemma-4-26b-a4b-qat`) | 1 作品 | 【セカンダリ執筆＆プロット】交互担当（偶数枠）で煽り・ケレン味のあるSF小説を執筆＆プロット設計 |
| **`kenomac-mini`** | `illustrator` | `http://kenomac-mini:7860` (`FLUX.2`) | 5 枚 | 【挿絵＆Web公開】FLUX.2 挿絵生成 (`content/*.png`) ＆ GitHub Pages (`docs/`) 更新 |

### ⚡ メインPC (`MINISFORUM64GB`) 電源OFF時の各PC単独・自律実行セットアップ
- **Windows (`rtx5060lp` / `sff7020`)**: リポジトリ内で `git pull` 後、`.\setup_autonomous_worker.ps1` を1回実行すると、PC起動時＆毎日20:00/21:00にGitHubからタスクを読み取って自律実行・Pushします（普段既に `run_worker.ps1` を自動実行している場合は自動で最新化されます）。
- **Mac (`kenomac-mini`)**: リポジトリ内で `git pull && bash setup_autonomous_worker.sh` を1回実行すると、macOS `LaunchAgent` に登録され、Mac起動時＆毎日20:15/21:15に未挿絵作品を検知して FLUX.2 挿絵生成＆GitHub Pages更新を自律実行します。

## 🚀 次回PC起動時の自動実行タスクキュー（GitHub蓄積タスク一覧）

| No. | 作品ID | 原典タイトル（著者） | 先端科学テーマ | 現在の状態 | 次回担当ライター（交互割当） |
|:---:|:---|:---|:---|:---:|:---|
| #75 | `edogawa-kaijin-nijumenso` | 怪人二十面相（江戸川乱歩） | 電気光学メタマテリアルによる動的皮膚迷彩・光学的クローキング、生体電位波形とマルチモーダル顔面特徴点のリアルタイム模倣、量子セキュア認証と少年探偵団の分散センシング網 | `pending` | ✍️ **プライマリ `rtx5060lp:11434`** (`shosetsu` 執筆) |

## ✅ 完了済み作品（最新10件）

| No. | 作品ID | 原典タイトル（著者） | プロット (`sff7020`) | 執筆担当 (`written_by`) | 校閲 (`sff7020`) | 挿絵 (`kenomac-mini`) |
|:---:|:---|:---|:---:|:---:|:---:|:---:|
| #74 | `akutagawa-jigokuhen` | 地獄変（芥川龍之介） | ✓ (sff7020) | ✓ `rtx5060lp` (2026-10-15) | 校閲済 | 🎨 (kenomac-mini) |
| #73 | `akutagawa-hana` | 鼻（芥川龍之介） | - | ✓ `rtx5060lp` (2026-10-15) | 校閲済 | 🎨 (kenomac-mini) |
| #72 | `soseki-botchan` | 坊っちゃん（夏目漱石） | - | ✓ `rtx5060lp` (2026-10-14) | ✓ (sff7020) | 🎨 (kenomac-mini) |
| #71 | `soseki-wagahai-wa-neko` | 吾輩は猫である（夏目漱石） | - | ✓ `rtx5060lp` (2026-10-14) | ✓ (sff7020) | 🎨 (kenomac-mini) |
| #70 | `dazai-ningen-shikkaku` | 人間失格（太宰治） | ✓ (sff7020) | ✓ `rtx5060lp` (2026-10-14) | 校閲済 | 🎨 (kenomac-mini) |
| #69 | `tayama-futon` | 蒲団（田山花袋） | - | ✓ `rtx5060lp` (2026-10-11) | ✓ (sff7020) | 🎨 (kenomac-mini) |
| #68 | `hori-kaze-tachinu` | 風立ちぬ（堀辰雄） | - | ✓ `rtx5060lp` (2026-10-10) | ✓ (sff7020) | 🎨 (kenomac-mini) |
| #67 | `koda-goju-no-to` | 五重塔（幸田露伴） | - | ✓ `rtx5060lp` (2026-10-10) | ✓ (sff7020) | 🎨 (kenomac-mini) |
| #66 | `origuchi-shisha-no-sho` | 死者の書（折口信夫） | ✓ (sff7020) | ✓ `rtx5060lp` (2026-10-10) | ✓ (sff7020) | 🎨 (kenomac-mini) |
| #65 | `sakaguchi-sakura-no-mori` | 桜の森の満開の下（坂口安吾） | ✓ (sff7020) | ✓ `rtx5060lp` (2026-10-10) | ✓ (sff7020) | 🎨 (kenomac-mini) |
