# Alchemy Factory Tool

## 生産計算画面

プロジェクトのフォルダーで実行します。

```powershell
uv sync --no-install-project
uv run --no-project streamlit run src/streamlit_app.py
```

ブラウザーでアイテムを日本語名から選び、毎分の目標生産量を入力して「計算する」を押すと、必要設備、各工程の必要生産量、外部調達素材を表示します。

日本語名とIDの対応は `database/alchemy.duckdb` の `items.item_id` / `items.item_name` から読み込みます。同名アイテムにはIDも表示します。レシピのないアイテムは全量を外部調達として表示します。

既存の `src/calculate_production.py` の読み込み・計算関数を再利用しています。工程の生産量は理論上の必要量、設備数は切り上げです。複数レシピの選択も既存CLIと同じです。

DBが使用中というエラーが出る場合は、VS CodeなどのDuckDB接続を閉じてから画面を再読み込みしてください。

既存CLIも引き続き利用できます。

```powershell
uv run --no-project python src/calculate_production.py gloom-spores 10
```

現在のパッケージ設定には未作成のモジュールへの参照があるため、上記の手順ではプロジェクト本体のインストールを省き、依存関係だけを導入します。

関連図では素材 → 加工機 → 出力アイテムの流れ、設備台数、加工時間、毎分の入力・出力量を表示します。既存計算で採用された工程のみを示し、確率出力には期待値であることを表示します。
