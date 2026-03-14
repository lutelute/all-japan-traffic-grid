# CLAUDE.md — All-Japan Traffic Grid

## 次のタスク: UXsim全国ネットワーク上でMATSimエージェントベースシミュレーションを実行

### 背景
- `visualize/japan_traffic_animated.py` が日本全国9地域の**繋がった道路ネットワーク**（111,027リンク）をosmnxで取得し、UXsim（メソスコピック）で24時間シミュレーションしている
- 現在のMATSim実行は9都市圏の**分離された小さなbbox**（合計58,267リンク）でしか回していない
- やりたいこと: UXsimと同じ全国繋がったネットワーク上でMATSimエージェントベースシミュレーションを実行する

### 計画

#### Phase 1: ネットワーク変換
- `visualize/japan_traffic_animated.py` の `simulate_region()` が内部で構築するosmnxグラフ（9地域）を、MATSim用 `network.xml` に変換する
- 既存の `src/matsim/network_converter.py` の `convert_to_matsim_network()` をそのまま使える
- ただし9地域分のosmnxグラフを**1つのNetworkXグラフに統合**する必要がある
- 各地域は異なるUTMゾーンに跨るため、network_converter内のUTM自動判定が正しく動くか確認
- キャッシュ: `visualize/cache/anim24_{region}.json` にUXsimの結果はあるが、**osmnxのグラフ自体はキャッシュされていない**ので、再取得が必要（大きい地域は時間がかかる）

#### Phase 2: 統合グラフの構築
- 9地域のosmnxグラフを取得して1つの `nx.DiGraph` にマージ
- 地域境界で重複するノード/エッジの統合（osmnx node IDはOSM IDなので、同一IDなら同一ノード）
- 最大強連結成分を抽出（MATSimの到達可能性要件）
- 見積もり: 合計 ~30,000ノード, ~60,000エッジ（highway filter: motorway/trunk/primary）

#### Phase 3: 人口生成
- 既存の `src/matsim/population.py` を使用
- 9地域の人口中心は既に定義済み（`REGION_CENTERS`）
- エージェント数: まず10,000で動作確認、その後段階的に増加
- OD需要パターン: `visualize/japan_traffic_animated.py` の `HOURLY_DEMAND`（24時間パターン）を参考に、MATSim側でも24時間の活動チェーンに反映

#### Phase 4: 信号抽出（オプション）
- 既存の `src/matsim/signal_extractor.py` で osmnxの `features_from_bbox` を使って信号ノードを取得
- 全国規模だと信号数が膨大になる可能性 → 主要交差点のみに絞る

#### Phase 5: MATSim実行
- 統合ネットワーク1本で実行（分割なし）
- JVM メモリ: 8-16GB（10万エージェントまでなら36GB RAMで可能）
- イテレーション: 5-10
- sample_rate: 0.1（10%サンプリング → 実質的に10倍相当）

#### Phase 6: 結果統合と可視化
- event_parser.py でtrajectories.jsonを生成
- EPSGは統合ネットワークの重心から自動判定
- japan_matsim_animated.py で既存のUXsimアニメーションと同じLeafletスタイルで表示
- index.htmlポータルに追加

### 実装の要点

#### 新規作成するもの
- `scripts/run_matsim_fullnetwork.py` — 全国統合ネットワークでMATSimを実行するCLIスクリプト
- osmnxグラフの9地域マージロジック（`src/matsim/pipeline.py` に `_merge_regional_graphs()` を追加）

#### 既存で再利用するもの
- `src/matsim/network_converter.py` — NetworkX → network.xml
- `src/matsim/population.py` — 合成人口生成
- `src/matsim/config_generator.py` — config.xml
- `src/matsim/runner.py` — MATSim実行
- `src/matsim/event_parser.py` — events → JSON（EPSG自動検出済み）
- `visualize/japan_matsim_animated.py` — Leafletアニメーション

#### 注意点
- 北海道のbboxが巨大（104倍のOverpass制限）→ osmnxが自動分割するが時間がかかる。`motorway|trunk` フィルタなら管理可能
- 地域間のネットワーク接続: osmnxのOSM node IDが共通なので、単純なグラフ統合（`nx.compose`）で境界が自然に繋がる
- MATSim 2025.0 は Java 21 必須（`/opt/homebrew/opt/openjdk@21/bin/java` にインストール済み）
- MATSim JAR: `data/matsim/matsim-2025.0/matsim-2025.0.jar`（ダウンロード済み）

### 実行見積もり
| エージェント | RAM | 時間（5iter） | 備考 |
|---|---|---|---|
| 10,000 | ~4 GB | ~5分 | 動作確認用 |
| 50,000 | ~8 GB | ~15分 | 中規模 |
| 100,000 | ~16 GB | ~30分 | このマシンの上限付近 |

### 現在の環境
- macOS, Apple M4 Max, 14コア, 36GB RAM
- Python 3.14, Java 21 (OpenJDK Homebrew)
- pyrosm未インストール（ビルド不可）→ osmnxベースで代替済み
