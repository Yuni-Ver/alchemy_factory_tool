# Alchemy Factory Tool

## 生産計算画面

プロジェクトのフォルダーで実行します。

```powershell
uv sync --no-install-project
uv run --no-project streamlit run src/streamlit_app.py
```

ブラウザーでアイテムを日本語名から選び、毎分の目標生産量を入力すると、必要設備、各工程の必要生産量、外部調達素材を表示します。最終アイテムと選択した経路に含まれる中間素材のレシピを選ぶと、素材、設備、関連図、稼働率を自動更新します。候補には設備、加工時間、入力素材、出力量、出力確率を表示します。

日本語名とIDの対応は `database/alchemy.duckdb` の `items.item_id` / `items.item_name` から読み込みます。同名アイテムにはIDも表示します。レシピのないアイテムは全量を外部調達として表示します。

既存の `src/calculate_production.py` の読み込み・計算関数を再利用しています。工程の生産量は理論上の必要量、設備数は切り上げです。初期選択とCLIはレシピID順の最初を採用します。循環するレシピを選んだ場合は計算エラーを表示するので、別のレシピに変更してください。副産物の相殺や同じ素材の複数レシピへの生産分配は行いません。

DBが使用中というエラーが出る場合は、VS CodeなどのDuckDB接続を閉じてから画面を再読み込みしてください。

生産量、素材量、加工時間、確率、稼働率は小数点以下2桁で切り捨て表示します（例：1.239 → 1.23）。画面・関連図・CLIで共通です。内部計算は元の精度を維持し、必要設備台数は引き続き切り上げます。

既存CLIも引き続き利用できます。

```powershell
uv run --no-project python src/calculate_production.py gloom-spores 10
```

現在のパッケージ設定には未作成のモジュールへの参照があるため、上記の手順ではプロジェクト本体のインストールを省き、依存関係だけを導入します。

関連図では素材 → 加工機 → 出力アイテムの流れ、設備台数、加工時間、毎分の入力・出力量を表示します。既存計算で採用された工程のみを示し、確率出力には期待値であることを表示します。

画面には通常の関連図を表示します。「関連図をPNGで保存」を押したときだけ画像を生成し、そのままダウンロードします。PNG生成にはGraphvizが必要です（画面表示には不要）。Windowsでは次のコマンドで導入できます。

```powershell
winget install --id Graphviz.Graphviz --exact --accept-package-agreements --accept-source-agreements
```
