import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from recipe_search import search_recipes
from streamlit.testing.v1 import AppTest


class RecipeSearchTests(unittest.TestCase):
    def test_search_fields_normalization_and_multiple_outputs(self):
        recipe = dict(recipe_id="coke-and-charcoal", recipe_name="コークスと木炭",
                      device_id="furnace", device_name="炉", craft_time=Decimal(6),
                      inputs=[("powder", Decimal(6))],
                      output_quantity=Decimal(1), probability=Decimal("0.5"))
        options = {"coke": [recipe], "charcoal": [{**recipe, "output_quantity": Decimal(2)}]}
        names = {"coke": "コークス", "charcoal": "木炭", "powder": "木炭粉末"}
        for query in ("木炭粉末 炉", "ＣＯＫＥ", "コークス", "木炭", "FURNACE", ""):
            with self.subTest(query=query):
                result = search_recipes(options, names, query)
                self.assertEqual(len(result), 1)
                self.assertEqual(len(result[0]["outputs"]), 2)
        self.assertEqual(search_recipes(options, names, "木炭 存在しない"), [])
        self.assertNotIn("outputs", recipe)

    def test_search_and_apply_without_changing_calculation_mode(self):
        script = str(Path(__file__).resolve().parents[1] / "src" / "streamlit_app.py")
        app = AppTest.from_file(script).run()
        app.text_input(key="recipe_query").set_value("coke-and-charcoal").run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.selectbox(key="search_choice").options), 2)
        app.selectbox(key="search_choice").select(("coke-and-charcoal", "coke")).run()
        app.button(key="apply_recipe_search").click().run()
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        self.assertEqual(app.selectbox(key="target_item").value, "coke")
        self.assertEqual(app.selectbox(key="recipe:coke").value, "coke-and-charcoal")
        app.radio(key="calculation_mode").set_value("入力指定").run()
        app.button(key="apply_recipe_search").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.radio(key="calculation_mode").value, "入力指定")
        app.text_input(key="recipe_query").set_value("no-such-recipe-123456").run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.button), 0)
        self.assertEqual(app.selectbox(key="target_item").value, "coke")
        app.text_input(key="recipe_query").set_value("").run()
        self.assertFalse(app.exception)


if __name__ == "__main__":
    unittest.main()
