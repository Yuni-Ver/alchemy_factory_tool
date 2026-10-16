import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from calculate_production import calculate_full_utilization, calculate_from_input
from recipe_graph import machine_utilization
from streamlit.testing.v1 import AppTest


class FullUtilizationTests(unittest.TestCase):
    def setUp(self):
        self.recipe = dict(recipe_id="final", recipe_name="final", craft_time=Decimal(6),
                           device_id="device", device_name="device",
                           output_quantity=Decimal(1), probability=Decimal(1),
                           inputs=[("ore", Decimal(2))])
        self.recipes = {"final": self.recipe}

    def test_output_rounds_up_and_recalculates_materials(self):
        for requested, expected, count in [(11, 20, 2), (10, 10, 1), (1, 10, 1)]:
            rate, machines, materials = calculate_full_utilization("final", Decimal(requested), self.recipes, {})
            self.assertEqual(rate, expected)
            self.assertEqual(machines[0]["machine_count"], count)
            self.assertEqual(materials["ore"], expected * 2)
            self.assertEqual(machine_utilization(machines[0], self.recipe), 100)

    def test_input_respects_budget_and_low_supply(self):
        for supply, expected in [(50, 20), (40, 20), (10, 5)]:
            upper, _, _ = calculate_from_input("final", "ore", Decimal(supply), self.recipes, {})
            rate, machines, materials = calculate_full_utilization("final", upper, self.recipes, {}, input_item="ore")
            self.assertEqual(rate, expected)
            self.assertLessEqual(materials["ore"], supply)
            self.assertEqual(machine_utilization(machines[0], self.recipe), 50 if supply == 10 else 100)

    def test_probability_repeating_capacity_and_no_recipe(self):
        self.recipe["probability"] = Decimal("0.5")
        rate, machines, _ = calculate_full_utilization("final", Decimal(6), self.recipes, {})
        self.assertEqual(rate, 10)
        self.assertEqual(machine_utilization(machines[0], self.recipe), 100)
        self.recipe["craft_time"] = Decimal(7)
        rate, machines, _ = calculate_full_utilization("final", Decimal(10), self.recipes, {})
        self.assertEqual(machines[0]["machine_count"], 3)
        self.assertEqual(machine_utilization(machines[0], self.recipe), 100)
        rate, machines, materials = calculate_full_utilization("raw", Decimal(10), {}, {})
        self.assertEqual(machines, [])
        self.assertEqual(materials, {"raw": Decimal(10)})

    def test_ui_output_input_and_disable(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "src" / "streamlit_app.py")).run()
        app.selectbox(key="target_item").select("coke").run()
        app.number_input(key="output_rate").set_value(11.0).run()
        app.checkbox(key="optimize_final").check().run()
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        self.assertTrue(any("20.00 個/分" in s.value for s in app.subheader))
        self.assertEqual(app.dataframe[1].value.iloc[0]["設備稼働率（%）"], 100)
        app.radio(key="calculation_mode").set_value("入力指定").run()
        app.selectbox(key="input_item").select("coal").run()
        app.number_input(key="input_rate").set_value(25.0).run()
        self.assertFalse(app.exception)
        self.assertTrue(any("20.00 個/分" in s.value for s in app.subheader))
        self.assertTrue(any("未使用量：5.00" in c.value for c in app.caption))
        app.checkbox(key="optimize_final").uncheck().run()
        self.assertTrue(any("25.00 個/分" in s.value for s in app.subheader))


if __name__ == "__main__":
    unittest.main()
