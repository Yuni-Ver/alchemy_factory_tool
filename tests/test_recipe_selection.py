import sys
from io import BytesIO
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import duckdb
from streamlit.testing.v1 import AppTest
from calculate_production import DB_PATH, calculate_production, load_data
from recipe_graph import build_recipe_graph, machine_utilization
from number_display import format_display, truncate_display
from recipe_graph import render_recipe_graph
from PIL import Image
from streamlit.runtime.media_file_manager import MediaFileManager


class RecipeSelectionTests(unittest.TestCase):
    def test_png_is_generated_only_on_download(self):
        script = str(Path(__file__).resolve().parents[1] / "src" / "streamlit_app.py")
        register = MediaFileManager.add_deferred
        with patch("recipe_graph.render_recipe_graph", wraps=render_recipe_graph) as render:
            with patch.object(MediaFileManager, "add_deferred", autospec=True,
                              side_effect=register) as deferred:
                app = AppTest.from_file(script).run()
                self.assertFalse(app.exception)
                render.assert_not_called()
                app.selectbox[0].select("coke").run()
                render.assert_not_called()
                manager, callback = deferred.call_args.args[:2]
                file_id = app.get("download_button")[0].proto.deferred_file_id
                url = manager.execute_deferred(file_id)
                self.assertTrue(url.endswith(".png"))
                render.assert_called_once()
                first_source = render.call_args.args[0]
                app.selectbox(key="recipe:coke").select("coke-and-charcoal").run()
                self.assertEqual(render.call_count, 1)
                manager = deferred.call_args.args[0]
                manager.execute_deferred(app.get("download_button")[0].proto.deferred_file_id)
                self.assertEqual(render.call_count, 2)
                self.assertNotEqual(first_source, render.call_args.args[0])

    def test_graph_png_rendering(self):
        with duckdb.connect(str(DB_PATH), read_only=True) as con:
            recipes, names = load_data(con)
        machines, materials = calculate_production("coke", Decimal(10), recipes, names)
        source = build_recipe_graph(machines, materials, recipes, names, "coke")
        png = render_recipe_graph(source)
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        with Image.open(BytesIO(png)) as image:
            self.assertEqual(image.format, "PNG")
            self.assertGreater(image.width, 100)
            self.assertGreater(image.height, 100)
            image.verify()

    def test_truncated_display_preserves_calculation(self):
        self.assertEqual(format_display(Decimal("1.239")), "1.23")
        self.assertEqual(format_display(Decimal("0.009")), "0.00")
        self.assertEqual(format_display(Decimal("1234.999"), grouped=True), "1,234.99")
        recipe = dict(recipe_id="test", recipe_name="test", craft_time=Decimal("60.009"),
                      device_id="assembler", device_name="assembler",
                      inputs=[("ore", Decimal("0.33333"))],
                      output_quantity=Decimal(1), probability=Decimal(1))
        machines, materials = calculate_production("final", Decimal("1.999"),
                                                   {"final": recipe}, {})
        self.assertEqual(machines[0]["target_rate"], Decimal("1.999"))
        self.assertEqual(machines[0]["machine_count"], 2)
        self.assertEqual(materials["ore"], Decimal("0.66632667"))
        self.assertEqual(truncate_display(materials["ore"]), Decimal("0.66"))
        graph = build_recipe_graph(machines, materials, {"final": recipe}, {}, "final")
        for label in ("1.99 個/分", "0.66 個/分", "入力1 0.33 個/分", "60.00 秒/回", "99.96%"):
            self.assertIn(label, graph)

    def test_selected_chain_calculation_and_graph(self):
        def recipe(name, time, inputs, quantity=1, probability=1):
            return dict(recipe_id=name, recipe_name=name, craft_time=Decimal(time),
                        device_id=name, device_name=name, inputs=inputs,
                        output_quantity=Decimal(quantity), probability=Decimal(probability))

        names = {i: i for i in ("final", "middle", "ore", "wood")}
        selected = {
            "final": recipe("final-alt", 30, [("middle", Decimal(2))]),
            "middle": recipe("middle-alt", 15, [("wood", Decimal(3))], 2, "0.5"),
        }
        machines, materials = calculate_production("final", Decimal(3), selected, names)
        self.assertEqual(materials, {"wood": Decimal(18)})
        self.assertEqual([m["machine_count"] for m in machines], [2, 2])
        self.assertEqual(machine_utilization(machines[0], selected["final"]), Decimal(75))
        self.assertEqual(machine_utilization(machines[1], selected["middle"]), Decimal(75))
        graph = build_recipe_graph(machines, materials, selected, names, "final")
        self.assertIn("middle-alt", graph)
        self.assertIn("18.00", graph)
        self.assertNotIn('item:ore', graph)
        selected["middle"]["inputs"] = [("final", Decimal(1))]
        with self.assertRaises(ValueError):
            calculate_production("final", Decimal(3), selected, names)

    def test_database_candidates_and_legacy_default(self):
        with duckdb.connect(str(DB_PATH), read_only=True) as con:
            options, names = load_data(con, all_recipes=True)
            defaults, _ = load_data(con)
            count = con.execute("SELECT count(*) FROM recipe_outputs").fetchone()[0]
        self.assertEqual(sum(map(len, options.values())), count)
        self.assertTrue(any(len(v) > 1 for v in options.values()))
        for item, recipes in options.items():
            self.assertEqual(defaults[item], recipes[0])

    def test_live_selection_and_intermediate_recalculation(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "src" / "streamlit_app.py")).run()
        self.assertFalse(app.exception)
        app.selectbox[0].select("coke").run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.get("image")), 0)
        self.assertEqual(len(app.get("graphviz_chart")), 1)
        self.assertEqual(len(app.get("download_button")), 1)
        self.assertEqual(app.selectbox(key="recipe:coke").value, "coke")
        before = [frame.value.to_json() for frame in app.dataframe]
        app.selectbox(key="recipe:coke").select("coke-and-charcoal").run()
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        self.assertNotEqual(before, [frame.value.to_json() for frame in app.dataframe])
        intermediates = [s for s in app.selectbox if s.key == "recipe:plank"]
        self.assertTrue(intermediates)
        selector = intermediates[0]
        current_index = selector.index
        selector.select_index((current_index + 1) % len(selector.options)).run()
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        app.selectbox[0].select("copper-ingot").run()
        app.selectbox(key="recipe:copper-ingot").select("copper-ingot-2").run()
        self.assertFalse(app.exception)
        self.assertTrue(app.error)
        app.selectbox(key="recipe:copper-ingot").select("copper-ingot").run()
        self.assertFalse(app.error)
        app.selectbox[0].select("coke").run()
        self.assertEqual(app.selectbox(key="recipe:coke").value, "coke-and-charcoal")


if __name__ == "__main__":
    unittest.main()
