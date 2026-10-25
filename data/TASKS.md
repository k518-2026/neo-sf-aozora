# 📋 分散ローカルLLM 自動作業リスト (`neo-sf-aozora`)

- **会話ID**: `b531d04e-6cb0-4202-9ea3-0056c8e2d7f6`
- **最終同期日時 (JST)**: `2026-10-25T09:42:50`
- **進捗サマリー**: 全 **93** 作品 （完了: **90** / 挿絵待ち: **0** / プロット作成済: **0** / 未着手: **3**）
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
| #91 | `sakaguchi-hakuchi` | 白痴（坂口安吾） | 脳波ハイパースキャニングによる対人神経同期（Inter-brain synchrony）、大規模火災旋風・熱対流渦シミュレーション、極限ストレス・被曝環境下における神経細胞保護と可塑性適応 | `pending` | ✍️ **プライマリ `rtx5060lp:11434`** (`shosetsu` 執筆) |
| #92 | `akutagawa-majutsu` | 魔術（芥川龍之介） | 凝縮系核反応・格子支援核融合（LENR）による元素変換、完全没入型ニューロVR知覚インターフェース、強化学習エージェントにおけるグリーディ方策（強欲アルゴリズム）の局所最適トラップと破綻 | `pending` | ✍️ **プライマリ `rtx5060lp:11434`** (`shosetsu` 執筆) |
| #93 | `edogawa-nisen-doka` | 二銭銅貨（江戸川乱歩） | ナノ粒子PUF（物理的複製困難関数）による金属ステガノグラフィ、量子アニーリング・イジング模型による組合せ最適化暗号解読、ゼロ知識対話型証明と二重ブラフ・メカニズム | `pending` | ✍️ **プライマリ `rtx5060lp:11434`** (`shosetsu` 執筆) |

## ✅ 完了済み作品（最新10件）

| No. | 作品ID | 原典タイトル（著者） | プロット (`sff7020`) | 執筆担当 (`written_by`) | 校閲 (`sff7020`) | 挿絵 (`kenomac-mini`) |
|:---:|:---|:---|:---:|:---:|:---:|:---:|
| #90 | `soseki-jitensha-nikki` | 自転車日記（夏目漱石） | - | ✓ `rtx5060lp` (2026-10-21) | ✓ (sff7020) | 🎨 (kenomac-mini) |
| #89 | `akutagawa-imogayu` | 芋粥（芥川龍之介） | - | ✓ `rtx5060lp` (2026-10-21) | ✓ (sff7020) | 🎨 (kenomac-mini) |
| #88 | `dazai-kachikachi-yama` | カチカチ山（太宰治） | - | ✓ `rtx5060lp` (2026-10-21) | ✓ (sff7020) | 🎨 (kenomac-mini) |
| #87 | `miyazawa-cello-goushe` | セロ弾きのゴーシュ（宮沢賢治） | - | ✓ `rtx5060lp` (2026-10-19) | ✓ (sff7020) | 🎨 (kenomac-mini) |
| #86 | `dazai-shayo` | 斜陽（太宰治） | - | ✓ `rtx5060lp` (2026-10-19) | ✓ (sff7020) | 🎨 (kenomac-mini) |
| #85 | `edogawa-kogane-kamen` | 黄金仮面（江戸川乱歩） | - | ✓ `rtx5060lp` (2026-10-19) | ✓ (sff7020) | 🎨 (kenomac-mini) |
| #84 | `akutagawa-butoukai` | 舞踏会（芥川龍之介） | - | ✓ `rtx5060lp` (2026-10-18) | ✓ (sff7020) | 🎨 (kenomac-mini) |
| #83 | `soseki-mon` | 門（夏目漱石） | - | ✓ `rtx5060lp` (2026-10-18) | ✓ (sff7020) | 🎨 (kenomac-mini) |
| #82 | `nakajima-riryo` | 李陵（中島敦） | - | ✓ `rtx5060lp` (2026-10-18) | ✓ (sff7020) | 🎨 (kenomac-mini) |
| #81 | `akutagawa-torokko` | トロッコ（芥川龍之介） | - | ✓ `rtx5060lp` (2026-10-16) | ✓ (sff7020) | 🎨 (kenomac-mini) |
