# 📋 分散ローカルLLM 自動作業リスト (`neo-sf-aozora`)

- **会話ID**: `b531d04e-6cb0-4202-9ea3-0056c8e2d7f6`
- **最終同期日時 (JST)**: `2026-10-10T02:08:46`
- **進捗サマリー**: 全 **69** 作品 （完了: **65** / 挿絵待ち: **0** / プロット作成済: **1** / 未着手: **3**）
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
| #66 | `origuchi-shisha-no-sho` | 死者の書（折口信夫） | 古墳石室の音響共鳴特性（アーキオアコースティクス）解析、古天文学による春分・秋分の太陽軌道復元、ハス繊維のナノ微細構造が織りなす構造色ホログラフィ | `plot_ready` | 🔥 **セカンダリ `sff7020:1234`** (煽り系SF執筆) |
| #67 | `koda-goju-no-to` | 五重塔（幸田露伴） | 木組み仕口の摩擦減衰と心柱による同調質量ダンパー（TMD）機構、スーパーコンピュータによる超大型台風の流体・構造連成解析、木材セルロース結晶の経年強度増加 | `pending` | ✍️ **プライマリ `rtx5060lp:11434`** (`shosetsu` 執筆) |
| #68 | `hori-kaze-tachinu` | 風立ちぬ（堀辰雄） | 個別化mRNAワクチンと粘膜免疫誘導による呼吸器疾患の克服、山岳森林浴におけるフィトンチッドと自律神経・NK細胞活性化、生体バイタル同期による共感ケア | `pending` | 🔥 **セカンダリ `sff7020:1234`** (煽り系SF執筆) |
| #69 | `tayama-futon` | 蒲団（田山花袋） | 嗅球から扁桃体・海馬へ直結する情動記憶回路の神経科学、ガスクロマトグラフィー質量分析（GC-MS）による微量揮発性分子プロファイリング、メタ認知療法による執着からの解放 | `pending` | ✍️ **プライマリ `rtx5060lp:11434`** (`shosetsu` 執筆) |

## ✅ 完了済み作品（最新10件）

| No. | 作品ID | 原典タイトル（著者） | プロット (`sff7020`) | 執筆担当 (`written_by`) | 校閲 (`sff7020`) | 挿絵 (`kenomac-mini`) |
|:---:|:---|:---|:---:|:---:|:---:|:---:|
| #65 | `sakaguchi-sakura-no-mori` | 桜の森の満開の下（坂口安吾） | ✓ (sff7020) | ✓ `rtx5060lp` (2026-10-10) | ✓ (sff7020) | 🎨 (kenomac-mini) |
| #64 | `yumeno-binzume-jigoku` | 瓶詰地獄（夢野久作） | - | ✓ `rtx5060lp` (2026-10-03) | ✓ (sff7020) | 🎨 (kenomac-mini) |
| #63 | `edogawa-oshie-to-tabisuru-otoko` | 押絵と旅する男（江戸川乱歩） | ✓ (sff7020) | ✓ `rtx5060lp` (2026-10-10) | 校閲済 | 🎨 (kenomac-mini) |
| #62 | `dazai-hashire-merosu` | 走れメロス（太宰治） | ✓ (sff7020) | ✓ `rtx5060lp` (2026-10-09) | 校閲済 | 🎨 (kenomac-mini) |
| #61 | `nakajima-tsuki-no-usagi` | 悟浄出世（中島敦） | ✓ (sff7020) | ✓ `rtx5060lp` (2026-10-09) | 校閲済 | 🎨 (kenomac-mini) |
| #60 | `izumi-gejigeji` | 春昼・春昼後刻（泉鏡花） | ✓ (sff7020) | ✓ `rtx5060lp` (2026-10-09) | 校閲済 | 🎨 (kenomac-mini) |
| #59 | `soseki-kusamakura` | 草枕（夏目漱石） | ✓ (sff7020) | ✓ `rtx5060lp` (2026-10-09) | 校閲済 | 🎨 (kenomac-mini) |
| #58 | `kajii-sakura-no-ki` | 櫻の樹の下には（梶井基次郎） | - | ✓ `rtx5060lp` (2026-10-08) | 校閲済 | 🎨 (kenomac-mini) |
| #57 | `miyazawa-gusukobudori` | グスコーブドリの伝記（宮沢賢治） | - | ✓ `rtx5060lp` (2026-10-04) | 校閲済 | 🎨 (kenomac-mini) |
| #56 | `akutagawa-haguruma` | 歯車（芥川龍之介） | - | ✓ `rtx5060lp` (2026-10-03) | 校閲済 | 🎨 (kenomac-mini) |
