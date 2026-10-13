
import json
from pathlib import Path

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = PROJECT_ROOT / "data" / "raw" / "recipes.json"
DB_PATH = PROJECT_ROOT / "database" / "alchemy.duckdb"


def create_tables(con):
    """テーブルを作成する。"""

    con.execute("""
        CREATE TABLE IF NOT EXISTS items (
            item_id VARCHAR PRIMARY KEY,
            item_name VARCHAR NOT NULL
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            device_id VARCHAR PRIMARY KEY,
            device_name VARCHAR NOT NULL
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS recipes (
            recipe_id VARCHAR PRIMARY KEY,
            recipe_name VARCHAR NOT NULL,
            craft_time_seconds DOUBLE NOT NULL,
            device_id VARCHAR,
            url VARCHAR,
            FOREIGN KEY (device_id) REFERENCES devices(device_id)
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS recipe_inputs (
            recipe_id VARCHAR NOT NULL,
            item_id VARCHAR NOT NULL,
            quantity DECIMAL(18, 6) NOT NULL,
            PRIMARY KEY (recipe_id, item_id),
            FOREIGN KEY (recipe_id) REFERENCES recipes(recipe_id),
            FOREIGN KEY (item_id) REFERENCES items(item_id)
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS recipe_outputs (
            recipe_id VARCHAR NOT NULL,
            item_id VARCHAR NOT NULL,
            quantity DECIMAL(18, 6) NOT NULL,
            probability DOUBLE NOT NULL,
            PRIMARY KEY (recipe_id, item_id),
            FOREIGN KEY (recipe_id) REFERENCES recipes(recipe_id),
            FOREIGN KEY (item_id) REFERENCES items(item_id)
        )
    """)


def import_recipes(con, recipes):
    """JSONのレシピデータをDBへ登録する。"""

    # アイテム・設備マスタ
    items = {}
    devices = {}

    for recipe in recipes:
        if recipe["device_id"]:
            devices[recipe["device_id"]] = recipe["device_name"]

        for item in recipe["inputs"] + recipe["outputs"]:
            items[item["item_id"]] = item["item_name"]

    # 既存データを削除（子テーブルから）
    con.execute("DELETE FROM recipe_inputs")
    con.execute("DELETE FROM recipe_outputs")
    con.execute("DELETE FROM recipes")
    con.execute("DELETE FROM items")
    con.execute("DELETE FROM devices")

    # マスタ登録
    con.executemany(
        "INSERT INTO items VALUES (?, ?)",
        [(item_id, name) for item_id, name in items.items()],
    )

    con.executemany(
        "INSERT INTO devices VALUES (?, ?)",
        [(device_id, name) for device_id, name in devices.items()],
    )

    # レシピ登録
    con.executemany(
        """
        INSERT INTO recipes
        (recipe_id, recipe_name, craft_time_seconds, device_id, url)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (
                r["recipe_id"],
                r["recipe_name"],
                r["craft_time_seconds"],
                r["device_id"],
                r["url"],
            )
            for r in recipes
        ],
    )

    # 入力素材登録
    inputs = [
        (r["recipe_id"], i["item_id"], i["quantity"])
        for r in recipes
        for i in r["inputs"]
    ]

    con.executemany(
        """
        INSERT INTO recipe_inputs
        (recipe_id, item_id, quantity)
        VALUES (?, ?, ?)
        """,
        inputs,
    )

    # 出力素材登録
    outputs = [
        (
            r["recipe_id"],
            o["item_id"],
            o["quantity"],
            o["probability"],
        )
        for r in recipes
        for o in r["outputs"]
    ]

    con.executemany(
        """
        INSERT INTO recipe_outputs
        (recipe_id, item_id, quantity, probability)
        VALUES (?, ?, ?, ?)
        """,
        outputs,
    )

    return len(items), len(devices), len(inputs), len(outputs)


def main():
    if not JSON_PATH.exists():
        raise FileNotFoundError(f"JSONが見つかりません: {JSON_PATH}")

    with JSON_PATH.open(encoding="utf-8") as f:
        recipes = json.load(f)

    # DB格納前の基本的な検証
    recipe_ids = [r["recipe_id"] for r in recipes]

    if len(recipe_ids) != len(set(recipe_ids)):
        raise ValueError("レシピIDが重複しています")

    for recipe in recipes:
        if recipe["craft_time_seconds"] <= 0:
            raise ValueError(f"製作時間が不正: {recipe['recipe_id']}")

        for item in recipe["inputs"] + recipe["outputs"]:
            if item["quantity"] <= 0:
                raise ValueError(f"数量が不正: {recipe['recipe_id']}")

        for output in recipe["outputs"]:
            if not 0 < output["probability"] <= 1:
                raise ValueError(f"確率が不正: {recipe['recipe_id']}")

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(DB_PATH))

    try:
        con.execute("BEGIN TRANSACTION")

        create_tables(con)
        counts = import_recipes(con, recipes)

        con.execute("COMMIT")

        print("DB登録成功！")
        print(f"レシピ: {len(recipes)}件")
        print(f"アイテム: {counts[0]}件")
        print(f"設備: {counts[1]}件")
        print(f"入力素材: {counts[2]}件")
        print(f"出力素材: {counts[3]}件")
        print(f"保存先: {DB_PATH}")

    except Exception:
        con.execute("ROLLBACK")
        raise

    finally:
        con.close()


if __name__ == "__main__":
    main()
