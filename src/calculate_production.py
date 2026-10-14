
import argparse
from collections import defaultdict
from decimal import Decimal, ROUND_CEILING
from pathlib import Path

import duckdb
from number_display import format_display


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "database" / "alchemy.duckdb"


def dec(value) -> Decimal:
    """数値をDecimalに変換する。"""
    return Decimal(str(value))


def ceil_decimal(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def load_data(con, *, all_recipes=False):
    """DBのレシピ情報をPythonの辞書へ読み込む。"""

    recipe_rows = con.execute("""
        SELECT
            r.recipe_id,
            r.recipe_name,
            r.craft_time_seconds,
            r.device_id,
            d.device_name,
            o.item_id,
            o.quantity,
            o.probability
        FROM recipes r
        JOIN recipe_outputs o
          ON r.recipe_id = o.recipe_id
        LEFT JOIN devices d
          ON r.device_id = d.device_id
        ORDER BY r.recipe_id
    """).fetchall()

    input_rows = con.execute("""
        SELECT recipe_id, item_id, quantity
        FROM recipe_inputs
        ORDER BY recipe_id, item_id
    """).fetchall()

    item_rows = con.execute("""
        SELECT item_id, item_name
        FROM items
    """).fetchall()

    item_names = dict(item_rows)

    inputs_by_recipe = defaultdict(list)

    for recipe_id, item_id, quantity in input_rows:
        inputs_by_recipe[recipe_id].append(
            (item_id, dec(quantity))
        )

    # 全候補を保持し、既存CLIではrecipe_id順の最初を採用する。
    recipes_by_item = {}

    for row in recipe_rows:
        (
            recipe_id,
            recipe_name,
            craft_time,
            device_id,
            device_name,
            output_item,
            output_quantity,
            probability,
        ) = row

        recipes_by_item.setdefault(output_item, []).append(
            {
                "recipe_id": recipe_id,
                "recipe_name": recipe_name,
                "craft_time": dec(craft_time),
                "device_id": device_id,
                "device_name": device_name,
                "output_quantity": dec(output_quantity),
                "probability": dec(probability),
                "inputs": inputs_by_recipe[recipe_id],
            },
        )

    if not all_recipes:
        recipes_by_item = {item: options[0] for item, options in recipes_by_item.items()}
    return recipes_by_item, item_names


def calculate_production(
    item_id: str,
    target_per_minute: Decimal,
    recipes_by_item: dict,
    item_names: dict,
):
    """目標生産量から必要設備・素材を再帰的に計算する。"""

    # 同じレシピへの需要は最初に合算する
    demand = defaultdict(lambda: Decimal("0"))
    demand[item_id] = target_per_minute

    # 需要を原材料まで展開
    pending = [(item_id, target_per_minute, frozenset())]
    base_materials = defaultdict(lambda: Decimal("0"))

    while pending:
        current_item, required_rate, ancestors = pending.pop()

        if current_item in ancestors:
            raise ValueError(
                f"循環するレシピを検出: {current_item}"
            )

        recipe = recipes_by_item.get(current_item)

        if recipe is None:
            base_materials[current_item] += required_rate
            continue

        output_per_cycle = (
            recipe["output_quantity"]
            * recipe["probability"]
        )

        if output_per_cycle <= 0:
            raise ValueError(
                f"出力数量が不正: {recipe['recipe_id']}"
            )

        # 目標生産量を満たす理論上の稼働回数/分
        cycles_per_minute = (
            required_rate / output_per_cycle
        )

        for ingredient_id, quantity in recipe["inputs"]:
            ingredient_rate = cycles_per_minute * quantity

            demand[ingredient_id] += ingredient_rate

            pending.append(
                (
                    ingredient_id,
                    ingredient_rate,
                    ancestors | {current_item},
                )
            )

    # 設備数は同じレシピへの需要を合算してから計算
    machines = []

    for produced_item, rate in demand.items():
        recipe = recipes_by_item.get(produced_item)

        if recipe is None:
            continue

        output_per_minute = (
            Decimal("60")
            / recipe["craft_time"]
            * recipe["output_quantity"]
            * recipe["probability"]
        )

        machines.append(
            {
                "item_id": produced_item,
                "item_name": item_names.get(
                    produced_item, produced_item
                ),
                "recipe_id": recipe["recipe_id"],
                "device_name": recipe["device_name"],
                "target_rate": rate,
                "machine_count": ceil_decimal(
                    rate / output_per_minute
                ),
            }
        )

    return machines, base_materials


def main():
    parser = argparse.ArgumentParser(
        description="Alchemy Factory 生産ライン計算"
    )

    parser.add_argument(
        "item_id",
        help="生産したいアイテムID",
    )
    parser.add_argument(
        "rate",
        type=Decimal,
        help="目標生産量（個/分）",
    )

    args = parser.parse_args()

    if args.rate <= 0:
        parser.error("目標生産量は0より大きくしてください")

    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"DBが見つかりません: {DB_PATH}"
        )

    con = duckdb.connect(str(DB_PATH), read_only=True)

    try:
        recipes_by_item, item_names = load_data(con)
    finally:
        con.close()

    if args.item_id not in item_names:
        parser.error(f"未知のアイテムID: {args.item_id}")

    machines, materials = calculate_production(
        args.item_id,
        args.rate,
        recipes_by_item,
        item_names,
    )

    print(
        f"\n生産対象: {item_names[args.item_id]}"
        f" ({format_display(args.rate)}個/分)"
    )

    print("\n=== 必要設備 ===")
    for machine in sorted(
        machines,
        key=lambda x: x["recipe_id"],
    ):
        print(
            f"{machine['item_name']}: "
            f"{machine['device_name']} "
            f"{machine['machine_count']}台 "
            f"(必要量: {format_display(machine['target_rate'])}/分)"
        )

    print("\n=== 外部調達する原材料 ===")
    for material_id, rate in sorted(materials.items()):
        print(
            f"{item_names.get(material_id, material_id)}: "
            f"{format_display(rate)}/分"
        )


if __name__ == "__main__":
    main()
