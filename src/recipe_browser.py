"""入力・設備・出力を絞り込んで閲覧する独立した画面。"""

import streamlit as st
from collections import defaultdict
from decimal import Decimal
from fractions import Fraction
from hashlib import sha256

from number_display import format_display
from recipe_search import search_recipes


def input_equipment_ratios(recipe, item_label):
    """入力1個/分を処理する設備数と、設備1台の入力処理量。"""
    quantities = defaultdict(lambda: Decimal(0))
    for item_id, quantity in recipe["inputs"]:
        quantities[item_id] += quantity
    rows = []
    for item_id, quantity in quantities.items():
        if quantity <= 0 or recipe["craft_time"] <= 0:
            continue
        exact = Fraction(recipe["craft_time"]) / (60 * Fraction(quantity))
        theoretical = Decimal(exact.numerator) / Decimal(exact.denominator)
        # 小数2桁の表示で0台になる比率も、分数で確認できるようにする。
        theory_label = (f"{exact} 台（0.01台未満）" if theoretical < Decimal("0.01")
                        else f"{format_display(theoretical)} 台")
        rows.append({"入力素材": item_label(item_id),
                     "入力1個/分あたりの設備（理論）": theory_label,
                     "入力1個/分の必要設置台数": (exact.numerator + exact.denominator - 1) // exact.denominator,
                     "設備1台の入力処理量（個/分）": format_display(Decimal(60) * quantity / recipe["craft_time"])})
    return rows


def ratio_summary(recipe, item_label, column):
    return "、".join(f"{row['入力素材']}：{row[column]}" for row in input_equipment_ratios(recipe, item_label)) or "対象なし"


def select_result_row(state, table_key, results, output_item):
    rows = state.get(table_key, {}).get("selection", {}).get("rows", [])
    if not rows or not 0 <= rows[0] < len(results):
        return
    recipe = results[rows[0]]
    outputs = [i for i, _, _ in recipe["outputs"]]
    current = state.get("browser_recipe")
    output = (current[1] if current and current[0] == recipe["recipe_id"] and current[1] in outputs
              else output_item if output_item in outputs else outputs[0])
    state["browser_recipe"] = (recipe["recipe_id"], output)


def output_equipment_rates(recipe, item_label):
    return [{"出力アイテム": item_label(i),
             "設備1台の出力量（個/分・期待値）": format_display(Decimal(60) / recipe["craft_time"] * q * p)}
            for i, q, p in recipe["outputs"]]


def show_recipe_browser(recipe_options, item_names, item_label, apply_recipe):
    st.title("レシピ一覧・検索")
    st.caption("入力素材・設備・出力アイテムを組み合わせて検索できます。各条件はすべて満たすものを表示します。")
    all_recipes = search_recipes(recipe_options, item_names, "")
    inputs = sorted({i for r in all_recipes for i, _ in r["inputs"]}, key=item_label)
    outputs = sorted(recipe_options, key=item_label)
    devices = {r["device_id"]: r["device_name"] or "設備未設定" for r in all_recipes}
    # Noneは「すべて」に使い、設備未設定は専用の値で区別する。
    device_choices = sorted(devices, key=lambda d: (devices[d], str(d)))
    query = st.text_input("キーワード", key="browser_query", placeholder="名前・IDで検索")
    left, middle, right = st.columns(3)
    with left:
        input_item = st.selectbox("入力素材", [None] + inputs,
                                  format_func=lambda i: "すべて" if i is None else item_label(i), key="browser_input")
    with middle:
        device = st.selectbox("設備", ["__all__"] + device_choices,
                              format_func=lambda d: "すべて" if d == "__all__" else f"{devices[d]} ({d or '未設定'})", key="browser_device")
    with right:
        output_item = st.selectbox("出力アイテム", [None] + outputs,
                                   format_func=lambda i: "すべて" if i is None else item_label(i), key="browser_output")
    results = search_recipes(recipe_options, item_names, query, input_item=input_item,
                             output_item=output_item, device_id=device if device != "__all__" else None)
    if device is None:
        results = [r for r in results if r["device_id"] is None]
    st.subheader(f"検索結果：{len(results)}件")
    st.caption("設備の比率は入力素材1個/分あたりです。理論台数は小数2桁で切り捨て、実際の設置台数は切り上げます。複数素材は同時にレシピの割合で供給する前提です。入力素材ごとの台数を合算する必要はありません。")
    if not results:
        st.info("条件に一致するレシピがありません。検索条件を変更してください。")
        return
    table_key = "browser_results_" + sha256(repr(([(r["recipe_id"]) for r in results], output_item)).encode()).hexdigest()[:16]

    def on_result_select():
        select_result_row(st.session_state, table_key, results, output_item)

    st.caption("行をクリックすると、そのレシピを詳細表示に反映します。")
    st.dataframe([
        {"入力素材": "、".join(f"{item_label(i)} × {format_display(q)}" for i, q in r["inputs"]) or "なし",
         "設備": r["device_name"] or "設備未設定",
         "入力1個/分あたりの設備（理論）": ratio_summary(r, item_label, "入力1個/分あたりの設備（理論）"),
         "入力1個/分の必要設置台数": ratio_summary(r, item_label, "入力1個/分の必要設置台数"),
         "設備1台の入力処理量（個/分）": ratio_summary(r, item_label, "設備1台の入力処理量（個/分）"),
         "出力アイテム": "、".join(f"{item_label(i)} × {format_display(q)}（確率 {format_display(p * 100)}%）" for i, q, p in r["outputs"]),
         "加工時間（秒）": format_display(r["craft_time"]),
         "レシピ": r["recipe_name"]}
        for r in results
    ], hide_index=True, width="stretch", key=table_key,
       on_select=on_result_select, selection_mode="single-row")
    by_id = {r["recipe_id"]: r for r in results}
    choices = [(r["recipe_id"], i) for r in results for i, _, _ in r["outputs"]]
    choice = st.selectbox("詳細を表示するレシピ・出力", choices,
                          format_func=lambda pair: f"{by_id[pair[0]]['recipe_name']} [{pair[0]}] → {item_label(pair[1])}",
                          key="browser_recipe")
    recipe = by_id[choice[0]]
    st.subheader(recipe["recipe_name"])
    st.write(f"設備：{recipe['device_name'] or '設備未設定'} ／ 加工時間：{format_display(recipe['craft_time'])} 秒/回")
    st.dataframe(output_equipment_rates(recipe, item_label), hide_index=True, width="stretch")
    st.caption("設備1台が100%稼働した場合の毎分の出力量です。確率出力は期待値を表示しています。")
    ratios = input_equipment_ratios(recipe, item_label)
    if ratios:
        st.dataframe(ratios, hide_index=True, width="stretch")
    left, right = st.columns(2)
    with left:
        st.write("入力（1回あたり）")
        for i, q in recipe["inputs"]:
            st.write(f"{item_label(i)} × {format_display(q)}")
        if not recipe["inputs"]:
            st.write("入力素材なし")
    with right:
        st.write("出力（1回あたり）")
        for i, q, p in recipe["outputs"]:
            st.write(f"{item_label(i)} × {format_display(q)} ／ 確率 {format_display(p * 100)}%")
    st.button("このレシピで生産計算へ", on_click=apply_recipe, args=choice, key="browser_apply")
