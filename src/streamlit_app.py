from collections import Counter
from decimal import Decimal
from functools import partial

import duckdb
import streamlit as st

from calculate_production import DB_PATH, calculate_production, load_data
from number_display import format_display, truncate_display
from recipe_graph import build_recipe_graph, machine_utilization, render_recipe_graph


st.set_page_config(page_title="Alchemy Factory 生産計算", layout="wide")
st.set_option("client.toolbarMode", "viewer")
st.title("Alchemy Factory 生産ライン計算")
st.caption("アイテムと毎分の目標生産量から、必要な設備と素材を計算します。")

if not DB_PATH.exists():
    st.error(f"データベースが見つかりません: {DB_PATH}")
    st.stop()

try:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        recipe_options, item_names = load_data(con, all_recipes=True)
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
item_id = st.selectbox("生産するアイテム", item_ids, format_func=item_label)
rate = st.number_input("目標生産量（個/分）", min_value=0.01, value=10.0, step=1.0, format="%.2f")

st.subheader("使用するレシピ")
st.caption("数値は小数点以下2桁で切り捨て表示します。計算には切り捨て前の値を使用します。")
st.caption("最終アイテムと中間素材ごとに選択できます。変更すると必要な素材と計算結果を更新します。初期値はレシピID順の最初です。")
recipes_by_item = {}
pending = [item_id]
visited = set()
while pending:
    current_item = pending.pop(0)
    if current_item in visited:
        continue
    visited.add(current_item)
    options = recipe_options.get(current_item, [])
    if not options:
        continue
    by_id = {recipe["recipe_id"]: recipe for recipe in options}

    def recipe_label(recipe_id, by_id=by_id):
        recipe = by_id[recipe_id]
        ingredients = "、".join(
            f"{item_names.get(ingredient, ingredient)} × {format_display(quantity)}"
            for ingredient, quantity in recipe["inputs"]
        ) or "入力素材なし"
        return (
            f"{recipe['recipe_name']} [{recipe_id}] / "
            f"{recipe['device_name'] or '設備未設定'} / {format_display(recipe['craft_time'])}秒 / "
            f"{ingredients} → {format_display(recipe['output_quantity'])}個 "
            f"(確率 {format_display(recipe['probability'] * 100)}%)"
        )

    key = f"recipe:{current_item}"
    saved_key = f"selected_recipe:{current_item}"
    if st.session_state.get(key) not in by_id:
        saved = st.session_state.get(saved_key)
        st.session_state[key] = saved if saved in by_id else options[0]["recipe_id"]
    selected = st.selectbox(
        f"{'最終アイテム' if current_item == item_id else '中間素材'}：{item_label(current_item)}",
        list(by_id), format_func=recipe_label, key=key,
        disabled=len(options) == 1,
    )
    st.session_state[saved_key] = selected
    recipes_by_item[current_item] = by_id[selected]
    pending.extend(ingredient for ingredient, _ in by_id[selected]["inputs"])

if not recipes_by_item:
    st.info("このアイテムには生産レシピがありません。")

if item_id:
    try:
        machines, materials = calculate_production(
            item_id, Decimal(str(rate)), recipes_by_item, item_names
        )
    except (ValueError, ArithmeticError) as exc:
        st.error(f"計算できません: {exc}")
        st.stop()

    st.subheader(f"{item_label(item_id)}：{format_display(rate, grouped=True)} 個/分")
    st.caption("生産量は目標を満たす理論上の必要量です。設備台数は工程ごとに切り上げ、上で選択したレシピを使用します。")

    st.subheader("レシピの関連図")
    st.caption("左から右へ、素材 → 加工機 → 出力アイテムの順に表示します。黄色は外部調達、青は中間素材、緑は生産目標です。矢印は各工程の毎分の必要量を表します。")
    dot_source = build_recipe_graph(machines, materials, recipes_by_item, item_names, item_id)
    st.graphviz_chart(dot_source, use_container_width=True)
    st.download_button(
        "関連図をPNGで保存", data=partial(render_recipe_graph, dot_source),
        file_name=f"production-{item_id}.png", mime="image/png", on_click="ignore",
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
            [{"アイテム": m["item_name"], "レシピ": recipes_by_item[m["item_id"]]["recipe_name"], "設備": m["device_name"] or "設備未設定",
              "必要台数": m["machine_count"], "必要生産量（個/分）": float(truncate_display(m["target_rate"])), "設備稼働率（%）": float(truncate_display(machine_utilization(m, recipes_by_item[m["item_id"]])))}
             for m in sorted(machines, key=lambda m: m["recipe_id"])],
            column_config={"必要生産量（個/分）": st.column_config.NumberColumn(format="%.2f"), "設備稼働率（%）": st.column_config.NumberColumn(format="%.2f %%")},
            hide_index=True, use_container_width=True,
        )
    else:
        st.info("このアイテムには生産レシピがないため、全量を外部調達します。")

    st.subheader("外部調達素材")
    if materials:
        st.dataframe(
            [{"素材": item_names.get(material_id, material_id), "必要量（個/分）": float(truncate_display(amount))}
             for material_id, amount in sorted(materials.items())],
            column_config={"必要量（個/分）": st.column_config.NumberColumn(format="%.2f")},
            hide_index=True, use_container_width=True,
        )
    else:
        st.info("外部調達が必要な素材はありません。")
