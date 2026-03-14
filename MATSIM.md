# MATSim SimCity ブランチ (`feature/matsim-simcity`)

## 概要

mainブランチのOSM/NetworkXパイプラインを基盤として、MATSim（Multi-Agent Transport Simulation）による大規模エージェントシミュレーションとSimCity風Web可視化を追加するブランチ。

## mainブランチとの連携

### 共有する基盤（main由来）
- `src/data/` — OSM PBFダウンロード・パース
- `src/network/` — NetworkXグラフ構築・簡略化・フィルタ
- `src/config.py` — 道路属性デフォルト値、Geofabrik URL、地域定義

### 本ブランチで追加した機能
- `src/matsim/` — MATSim統合（8モジュール）
- `web/` — deck.gl + MapLibre GL によるSimCity風可視化
- `scripts/run_matsim.py` — 単一地域パイプライン
- `scripts/run_partitioned.py` — 分割パイプライン（日本全国対応）
- `scripts/generate_demo_data.py` — デモデータ生成

### 依存関係の追加
- `pyproj` — UTM座標変換
- `lxml` — MATSim XML生成
- Java 21+ — MATSim 2025.0の実行に必要

## アーキテクチャ

```
[main] OSM PBF → Pyrosm/osmnx → NetworkX DiGraph
                                       │
                          ┌─────────────┤
                          │             │
                   [main] UXsim    [この branch] MATSim
                          │             │
                     Folium/PNG    ┌────┴────┐
                                  │         │
                            network.xml  plans.xml
                            signals.xml  config.xml
                                  │
                            MATSim (Java)
                                  │
                           events.xml.gz
                                  │
                          ┌───────┴───────┐
                          │               │
                    trajectories.json  link_counts.json
                          │
                    deck.gl Web UI
```

## 機能一覧

### 1. MATSim ネットワーク変換 (`src/matsim/network_converter.py`)
- NetworkX DiGraph → MATSim `network.xml`
- UTM自動投影（エリアの経度からUTMゾーンを自動判定）
- リンク容量を道路種別×車線数から算出

### 2. 信号システム (`src/matsim/signal_extractor.py`)
- OSM `highway=traffic_signals` ノードを抽出
- 方位角ベースでNS/EWグループに分類
- 固定時間制御の信号XMLを3ファイル生成

### 3. 合成人口 (`src/matsim/population.py`)
- 9地域の人口中心を定義（関東10拠点、関西6拠点 等）
- home-work-home活動チェーンを生成
- 出発時刻: N(7:30, 0:30)、帰宅時刻: N(17:30, 0:45)

### 4. MATSim実行基盤 (`src/matsim/runner.py`, `java_manager.py`)
- MATSim 2025.0 JAR自動ダウンロード
- Java 21+検出、subprocess実行、進捗ログ

### 5. イベント解析 (`src/matsim/event_parser.py`)
- `events.xml.gz` → エージェント軌跡JSON
- リンク別交通量の時系列データ
- ネットワークGeoJSON生成
- **UTMゾーン自動検出**（network.xmlのCRS属性から）

### 6. 分割パイプライン (`src/matsim/partitioned.py`)
- 日本全国を9都市圏に分割（札幌〜福岡）
- 1エリアずつ順次実行（RAM制約への対応）
- 境界エージェントの抽出・注入（2パスモード）
- 全エリアの結果を統合して可視化

### 7. SimCity Web UI (`web/`)
- deck.gl ScatterplotLayer: エージェントのアニメーション
- PathLayer: 渋滞度に応じた道路着色（緑→黄→赤）
- HeatmapLayer: 交通密度ヒートマップ
- タイムラインスライダー（0.5x〜60x再生速度）
- リアルタイム統計パネル
- 地域セレクタ（全国/関東/関西 等）

## 実行方法

```bash
# デモデータで可視化確認（MATSim不要）
python scripts/generate_demo_data.py --agents 2000
python -m http.server 8080 --directory web

# 単一地域シミュレーション
python scripts/run_matsim.py --region kanto --agents 10000 --iterations 5

# 日本全国分割シミュレーション
python scripts/run_partitioned.py --preset japan --iterations 3
python scripts/run_partitioned.py --preset japan --agents-multiplier 10  # 10倍スケール

# 結果をWeb UIに反映
cp data/output/matsim_partitioned/viz/* web/data/
python -m http.server 8080 --directory web
```

## 実績

| スケール | エージェント数 | 実行時間 | 備考 |
|---|---|---|---|
| 1x (テスト) | 9,000 | ~15分 | 各エリア1,000 |
| 10x | 65,000 | ~13分 | 各エリア3,000〜15,000 |

## 今後の拡張候補
- [ ] エージェント100倍スケール（65万）
- [ ] `tertiary`道路の追加（ネットワーク密度向上）
- [ ] 信号有効化での再実行
- [ ] 2パスモードでのエリア間需要交換
- [ ] パーソントリップ調査データの統合
- [ ] リアルタイムWebSocket配信
