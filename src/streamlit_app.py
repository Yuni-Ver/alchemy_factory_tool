from collections import Counter
from decimal import Decimal

import duckdb
import streamlit as st

from calculate_production import DB_PATH, calculate_production, load_data
from recipe_graph import build_recipe_graph, machine_utilization


st.set_page_config(page_title="Alchemy Factory 生産計算", layout="wide")
st.title("Alchemy Factory 生産ライン計算")
st.caption("アイテムと毎分の目標生産量から、必要な設備と素材を計算します。")

if not DB_PATH.exists():
    st.error(f"データベースが見つかりません: {DB_PATH}")
    st.stop()

try:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        recipes_by_item, item_names = load_data(con)
    finally:
        con.close()
except duckdb.Error as exc:
    st.error("データベースを読み込めません。VS Code などで DB を開いている場合は接続を閉じてから再読み込みしてください。")
    with st.expander("エラー詳細"):
        st.code(str(exc))
    st.stop()

if not item_names:
    st.warning("items テーブルにアイテムがありません。")
    st.stop()

name_counts = Counter(item_names.values())


def item_label(item_id):
    name = item_names[item_id] or item_id
    return f"{name} ({item_id})" if name_counts[item_names[item_id]] > 1 else name


item_ids = sorted(item_names, key=lambda item_id: (item_names[item_id] or item_id, item_id))
with st.form("production"):
    item_id = st.selectbox("生産するアイテム", item_ids, format_func=item_label)
    rate = st.number_input("目標生産量（個/分）", min_value=0.01, value=10.0, step=1.0, format="%.2f")
    submitted = st.form_submit_button("計算する", type="primary")

if submitted:
    try:
        machines, materials = calculate_production(
            item_id, Decimal(str(rate)), recipes_by_item, item_names
        )
    except (ValueError, ArithmeticError) as exc:
        st.error(f"計算できません: {exc}")
        st.stop()

    st.subheader(f"{item_label(item_id)}：{rate:,.2f} 個/分")
    st.caption("生産量は目標を満たす理論上の必要量です。設備台数は工程ごとに切り上げます。複数レシピがある場合は既存の計算処理と同じくレシピID順の最初を採用します。")

    st.subheader("レシピの関連図")
    st.caption("左から右へ、素材 → 加工機 → 出力アイテムの順に表示します。黄色は外部調達、青は中間素材、緑は生産目標です。矢印は各工程の毎分の必要量を表します。")
    st.graphviz_chart(
        build_recipe_graph(machines, materials, recipes_by_item, item_names, item_id),
        use_container_width=True,
    )
    st.caption("計算で採用したレシピの入力と対象アイテムの出力を表示しています。副産物や別レシピは含みません。")
    st.caption("入力素材が1種類のアセンブラーは、同じ素材を2枠へ供給するものとして、必要量を半分ずつ2ラインに分けて表示します。")

    st.subheader("必要設備")
    if machines:
        device_counts = Counter()
        for machine in machines:
            device_counts[machine["device_name"] or "設備未設定"] += machine["machine_count"]
        st.metric("設備の合計", f"{sum(device_counts.values()):,} 台")
        st.dataframe(
            [{"設備": device, "必要台数": count} for device, count in sorted(device_counts.items())],
            hide_index=True, use_container_width=True,
        )
        st.subheader("各工程の生産量")
        st.caption("設備稼働率は、必要生産量 ÷ 設置台数分の最大生産量です。同じ工程の設備を均等に動かす場合の平均値で、確率出力は期待値を使います。")
        st.dataframe(
            [{"アイテム": m["item_name"], "設備": m["device_name"] or "設備未設定",
              "必要台数": m["machine_count"], "必要生産量（個/分）": float(m["target_rate"]), "設備稼働率（%）": float(machine_utilization(m, recipes_by_item[m["item_id"]]))}
             for m in sorted(machines, key=lambda m: m["recipe_id"])],
            column_config={"必要生産量（個/分）": st.column_config.NumberColumn(format="%.2f"), "設備稼働率（%）": st.column_config.NumberColumn(format="%.1f %%")},
            hide_index=True, use_container_width=True,
        )
    else:
        st.info("このアイテムには生産レシピがないため、全量を外部調達します。")

    st.subheader("外部調達素材")
    if materials:
        st.dataframe(
            [{"素材": item_names.get(material_id, material_id), "必要量（個/分）": float(amount)}
             for material_id, amount in sorted(materials.items())],
            column_config={"必要量（個/分）": st.column_config.NumberColumn(format="%.2f")},
            hide_index=True, use_container_width=True,
        )
    else:
        st.info("外部調達が必要な素材はありません。")
