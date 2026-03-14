```
    ___    ____       __                            ______            _________
   /   |  / / /      / /___ _____  ____ _____      /_  __/________ _/ __/ __(_)____
  / /| | / / /______/ / __ `/ __ \/ __ `/ __ \      / / / ___/ __ `/ /_/ /_/ / ___/
 / ___ |/ / /______/ / /_/ / /_/ / /_/ / / / /     / / / /  / /_/ / __/ __/ / /__
/_/  |_/_/_/    __/ /\__,_/ .___/\__,_/_/ /_/     /_/ /_/   \__,_/_/ /_/ /_/\___/
               /___/     /_/
   ______     _     __
  / ____/____(_)___/ /
 / / __/ ___/ / __  /        :::  Japan-wide Multi-Agent Traffic Simulation  :::
/ /_/ / /  / / /_/ /
\____/_/  /_/\__,_/          UXsim (mesoscopic)  +  MATSim (microscopic)
                             OpenStreetMap  ->  SimCity-style WebGL viz
```

# All-Japan Traffic Grid

日本全国の道路交通ネットワークシミュレーション・可視化システム。
OpenStreetMap から道路網を抽出し、メソスコピック（UXsim）およびマイクロスコピック（MATSim）の交通シミュレーションを実行。

## 姉妹プロジェクト

| プロジェクト | インフラ | データソース | リポジトリ |
|---|---|---|---|
| **All-Japan-Grid** | 送電網（変電所・送電線・発電所） | OpenStreetMap | [lutelute/All-Japan-Grid](https://github.com/lutelute/All-Japan-Grid) |
| **All-Japan Traffic Grid** | 道路交通網（道路・信号・エージェント） | OpenStreetMap | 本リポジトリ |

両プロジェクトはOSMを共通データソースとして、日本の社会インフラを地理的トポロジとして機械抽出・シミュレーションする取り組みです。

---

## 機能

### 1. 道路ネットワーク構築
- Geofabrik PBF / Overpass API からOSM道路データを取得
- 高速道路〜県道（motorway〜secondary）をフィルタリング
- NetworkX有向グラフへ変換（速度・車線数・道路種別）

### 2. UXsim 交通シミュレーション（メソスコピック）
- プラトーン単位のメソスコピックシミュレーション
- 日本全国9地域対応
- Folium（インタラクティブHTML）/ Matplotlib（静的PNG）で可視化

### 3. MATSim マルチエージェントシミュレーション
- 個別エージェント単位のマイクロスコピックシミュレーション
- OSM信号データの抽出・反映
- 合成人口生成（home-work-home活動チェーン）
- 日本全国9都市圏の分割パイプライン（順次実行でメモリ制約回避）
- 65,000エージェント規模で動作確認済み

### 4. SimCity風 Web可視化
- deck.gl + MapLibre GL によるダークテーマ3Dマップ
- エージェントのリアルタイムアニメーション
- 渋滞ヒートマップオーバーレイ
- タイムラインスライダー（0.5x〜60x再生速度）

---

## クイックスタート

### 前提条件
- Python 3.11+
- Java 21+（MATSimを使う場合）

### インストール
```bash
pip install -e .
```

### UXsim シミュレーション
```bash
python scripts/run_simulation.py --region kanto
python scripts/generate_map.py
```

### MATSim シミュレーション
```bash
# 単一地域
python scripts/run_matsim.py --region kanto --agents 10000 --iterations 5

# 日本全国（分割実行）
python scripts/run_partitioned.py --preset japan --agents-multiplier 10

# Web可視化
cp data/output/matsim_partitioned/viz/* web/data/
python -m http.server 8080 --directory web
```

### デモ（MATSim不要）
```bash
python scripts/generate_demo_data.py --agents 2000
python -m http.server 8080 --directory web
```

---

## プロジェクト構成

```
src/
├── config.py              # グローバル設定（道路属性、地域URL）
├── data/                  # OSMデータ取得・パース
│   ├── downloader.py      #   Geofabrik PBFダウンロード
│   ├── parser.py          #   Pyrosmパース・フィルタ
│   └── cache.py           #   キャッシュ管理
├── network/               # ネットワーク構築
│   ├── builder.py         #   GeoDataFrame → NetworkX
│   ├── filter.py          #   道路種別フィルタ・デフォルト値
│   └── simplify.py        #   ノード統合・死端除去
├── simulation/            # UXsimシミュレーション
│   ├── world.py           #   NetworkX → UXsim World
│   ├── demand.py          #   OD需要生成
│   └── runner.py          #   シミュレーション実行
├── visualization/         # UXsim結果可視化
│   ├── export.py          #   GeoJSON/GeoDataFrameエクスポート
│   └── congestion_map.py  #   Folium/Matplotlib地図生成
└── matsim/                # MATSimシミュレーション
    ├── network_converter.py  # NetworkX → network.xml
    ├── signal_extractor.py   # OSM信号 → 信号XML
    ├── population.py         # 合成人口 → plans.xml
    ├── config_generator.py   # config.xml生成
    ├── java_manager.py       # MATSim JAR管理
    ├── runner.py             # MATSim実行
    ├── event_parser.py       # events.xml → 可視化JSON
    ├── pipeline.py           # 単一地域パイプライン
    └── partitioned.py        # 分割パイプライン

scripts/
├── run_simulation.py      # UXsimパイプライン実行
├── generate_map.py        # UXsim結果の地図生成
├── run_matsim.py          # MATSim単一地域実行
├── run_partitioned.py     # MATSim分割実行
└── generate_demo_data.py  # デモデータ生成

web/                       # SimCity風Web UI
├── index.html
├── css/style.css
└── js/
    ├── app.js             # メインコントローラ
    ├── layers.js           # deck.glレイヤー管理
    ├── timeline.js         # タイムライン制御
    ├── stats.js            # 統計パネル
    └── data-loader.js      # データ読み込み
```

---

## アーキテクチャ

```
OpenStreetMap (Geofabrik / Overpass API)
              │
              ▼
    OSMデータ取得・パース (src/data/)
              │
              ▼
    NetworkX DiGraph (src/network/)
              │
     ┌────────┴────────┐
     ▼                 ▼
  UXsim             MATSim
  (メソスコピック)      (マイクロスコピック)
     │                 │
     ▼                 ▼
  Folium/PNG      deck.gl Web UI
```

---

## ライセンス

MIT

## データソース

道路ネットワークデータは [OpenStreetMap](https://www.openstreetmap.org/) から取得しています（© OpenStreetMap contributors, ODbL）。
