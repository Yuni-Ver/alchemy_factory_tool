import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from calculate_production import calculate_from_input
from recipe_graph import build_recipe_graph
from streamlit.testing.v1 import AppTest


def recipe(name, inputs, output=1, probability=1):
    return dict(recipe_id=name, recipe_name=name, craft_time=Decimal(30),
                device_id=name, device_name=name, inputs=inputs,
                output_quantity=Decimal(output), probability=Decimal(probability))


class InputProductionTests(unittest.TestCase):
    def setUp(self):
        self.recipes = {
            "final": recipe("final", [("middle", Decimal(2)), ("ore", Decimal(1))]),
            "middle": recipe("middle", [("ore", Decimal(3)), ("water", Decimal(1))], 2, "0.5"),
        }

    def test_shared_raw_material_and_probability(self):
        rate, machines, materials = calculate_from_input("final", "ore", Decimal(70), self.recipes, {})
        self.assertEqual(rate, Decimal(10))
        self.assertEqual(materials, {"ore": Decimal(70), "water": Decimal(20)})
        self.assertEqual([m["machine_count"] for m in machines], [5, 10])

    def test_intermediate_supply_removes_upstream(self):
        rate, machines, materials = calculate_from_input("final", "middle", Decimal(20), self.recipes, {})
        self.assertEqual(rate, Decimal(10))
        self.assertEqual([m["item_id"] for m in machines], ["final"])
        self.assertEqual(materials, {"middle": Decimal(20), "ore": Decimal(10)})
        self.assertIn("middle", self.recipes)
        graph = build_recipe_graph(machines, materials, self.recipes, {}, "final")
        self.assertNotIn("process:middle", graph)
        self.assertNotIn("item:water", graph)

    def test_invalid_input_and_cycle(self):
        for item, rate in [("ore", 0), ("ore", -1), ("ore", "NaN"),
                           ("ore", "Infinity"), ("unused", 10), ("final", 10)]:
            with self.subTest(item=item, rate=rate), self.assertRaises(ValueError):
                calculate_from_input("final", item, Decimal(rate), self.recipes, {})
        self.recipes["middle"]["inputs"] = [("final", Decimal(1))]
        with self.assertRaises(ValueError):
            calculate_from_input("final", "ore", Decimal(10), self.recipes, {})
        rate, _, _ = calculate_from_input("final", "middle", Decimal(20), self.recipes, {})
        self.assertEqual(rate, Decimal(10))

    def test_ui_modes_recipe_change_and_input_rate(self):
        script = str(Path(__file__).resolve().parents[1] / "src" / "streamlit_app.py")
        app = AppTest.from_file(script).run()
        app.selectbox[0].select("coke").run()
        app.radio(key="calculation_mode").set_value("入力指定").run()
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        app.selectbox(key="input_item").select("coal").run()
        app.number_input(key="input_rate").set_value(20.0).run()
        self.assertTrue(any("20.00 個/分" in s.value for s in app.subheader))
        processes = app.dataframe[1].value
        self.assertEqual(len(processes), 1)
        self.assertEqual(processes.iloc[0]["必要台数"], 2)
        app.selectbox(key="recipe:coke").select("coke-and-charcoal").run()
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        self.assertNotEqual(app.selectbox(key="input_item").value, "coal")
        app.selectbox(key="input_item").select("charcoal-powder").run()
        app.number_input(key="input_rate").set_value(60.0).run()
        self.assertFalse(app.error)
        self.assertEqual(len(app.dataframe[1].value), 1)
        self.assertEqual(len(app.get("graphviz_chart")), 1)
        self.assertEqual(len(app.get("download_button")), 1)
        app.radio(key="calculation_mode").set_value("出力指定").run()
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        self.assertEqual(app.number_input(key="output_rate").value, 10.0)


if __name__ == "__main__":
    unittest.main()
