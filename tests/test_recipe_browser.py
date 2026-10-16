import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from streamlit.testing.v1 import AppTest
from calculate_production import DB_PATH, load_data
from recipe_search import search_recipes
from recipe_browser import input_equipment_ratios, output_equipment_rates, select_result_row
from decimal import Decimal
import duckdb


class RecipeBrowserTests(unittest.TestCase):
    def test_selected_row_updates_recipe_and_output(self):
        results = [{"recipe_id": "a", "outputs": [("one", 1, 1), ("two", 1, 1)]},
                   {"recipe_id": "b", "outputs": [("three", 1, 1)]}]
        state = {"table": {"selection": {"rows": [0]}}}
        select_result_row(state, "table", results, "two")
        self.assertEqual(state["browser_recipe"], ("a", "two"))
        select_result_row(state, "table", results, None)
        self.assertEqual(state["browser_recipe"], ("a", "two"))
        state["table"]["selection"]["rows"] = [1]
        select_result_row(state, "table", results, "two")
        self.assertEqual(state["browser_recipe"], ("b", "three"))
        state["table"]["selection"]["rows"] = []
        select_result_row(state, "table", results, None)
        self.assertEqual(state["browser_recipe"], ("b", "three"))

    def test_output_per_machine_includes_probability_and_truncates(self):
        recipe = {"craft_time": Decimal(7), "outputs": [("one", Decimal(2), Decimal("0.5")), ("two", Decimal(1), Decimal(1))]}
        rows = output_equipment_rates(recipe, str)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["設備1台の出力量（個/分・期待値）"], "8.57")
        self.assertEqual(rows[1]["設備1台の出力量（個/分・期待値）"], "8.57")

    def test_input_equipment_ratios(self):
        recipe = {"craft_time": Decimal(6), "inputs": [("ore", Decimal(1)), ("ore", Decimal(1)), ("water", Decimal(4))]}
        rows = input_equipment_ratios(recipe, lambda i: i)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["入力1個/分あたりの設備（理論）"], "0.05 台")
        self.assertEqual(rows[0]["入力1個/分の必要設置台数"], 1)
        self.assertEqual(rows[0]["設備1台の入力処理量（個/分）"], "20.00")
        self.assertEqual(rows[1]["入力1個/分あたりの設備（理論）"], "0.02 台")
        recipe["craft_time"] = Decimal(600)
        self.assertEqual(input_equipment_ratios(recipe, str)[0]["入力1個/分の必要設置台数"], 5)
        recipe["craft_time"] = Decimal(1)
        recipe["inputs"] = [("ore", Decimal(10))]
        self.assertIn("1/600", input_equipment_ratios(recipe, str)[0]["入力1個/分あたりの設備（理論）"])
        recipe["inputs"] = []
        self.assertEqual(input_equipment_ratios(recipe, str), [])

    def test_combined_filters(self):
        with duckdb.connect(str(DB_PATH), read_only=True) as con:
            recipes, names = load_data(con, all_recipes=True)
        result = search_recipes(recipes, names, "", input_item="charcoal-powder", output_item="coke")
        self.assertEqual([r["recipe_id"] for r in result], ["coke-and-charcoal"])
        device = result[0]["device_id"]
        self.assertEqual(len(search_recipes(recipes, names, "", input_item="charcoal-powder", device_id=device, output_item="coke")), 1)
        self.assertEqual(search_recipes(recipes, names, "", input_item="coal-ore", output_item="copper-ingot"), [])

    def test_navigation_filters_apply_and_preserved_state(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "src" / "streamlit_app.py")).run()
        app.selectbox(key="target_item").select("coke").run()
        app.number_input(key="output_rate").set_value(25.0).run()
        app.checkbox(key="optimize_final").check().run()
        app.radio(key="screen").set_value("レシピ一覧・検索").run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.get("graphviz_chart")), 0)
        app.selectbox(key="browser_input").select("charcoal-powder").run()
        app.selectbox(key="browser_output").select("coke").run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.dataframe[0].value), 1)
        self.assertNotIn("レシピID", app.dataframe[0].value.columns)
        self.assertEqual(len(app.dataframe[1].value), 2)
        app.text_input(key="browser_query").set_value("no-match-xyz").run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.dataframe), 0)
        app.text_input(key="browser_query").set_value("").run()
        app.selectbox(key="browser_recipe").select(("coke-and-charcoal", "coke")).run()
        app.button(key="browser_apply").click().run()
        self.assertFalse(app.exception)
        self.assertFalse(app.error, [error.value for error in app.error])
        self.assertEqual(app.radio(key="screen").value, "生産計算")
        self.assertEqual(app.selectbox(key="recipe:coke").value, "coke-and-charcoal")
        self.assertEqual(app.number_input(key="output_rate").value, 25.0)
        self.assertTrue(app.checkbox(key="optimize_final").value)
        app.radio(key="screen").set_value("レシピ一覧・検索").run()
        app.radio(key="screen").set_value("生産計算").run()
        self.assertFalse(app.exception)
        self.assertEqual(app.number_input(key="output_rate").value, 25.0)
        self.assertEqual(app.selectbox(key="recipe:coke").value, "coke-and-charcoal")


if __name__ == "__main__":
    unittest.main()
