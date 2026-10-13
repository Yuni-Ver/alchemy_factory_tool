
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://alchemy-factory-codex.com"
RECIPES_URL = f"{BASE_URL}/ja/recipes/"

# プロジェクトルート
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = PROJECT_ROOT / "data" / "raw" / "recipes.json"


def get_id_from_url(url: str) -> str:
    """URLの最後の部分をIDとして取得する。"""
    return urlparse(url).path.rstrip("/").split("/")[-1]



def parse_items(recipe_element, section: str) -> list[dict]:
    """入力素材または出力アイテムを抽出する。"""
    items = []

    for element in recipe_element.select(f".{section} .recipe-item"):
        link = element.select_one("a.item-link")

        if link is None:
            continue

        parent = link.parent
        text_before_link = ""

        for child in parent.contents:
            if child is link:
                break
            if isinstance(child, str):
                text_before_link += child

        # 数量（小数に対応）
        quantity_match = re.search(
            r"(\d+(?:\.\d+)?)\s*x",
            text_before_link,
        )

        if quantity_match is None:
            raise ValueError(
                f"数量を取得できません: {link.get_text(strip=True)}"
            )

        item_data = {
            "item_id": get_id_from_url(link["href"]),
            "item_name": link.get_text(strip=True),
            "quantity": float(quantity_match.group(1)),
        }

        # 出力確率
        if section == "outputs":
            probability = 1.0
            percentage = element.select_one(".percentage")

            if percentage:
                probability_match = re.search(
                    r"(\d+(?:\.\d+)?)\s*%",
                    percentage.get_text(strip=True),
                )

                if probability_match is None:
                    raise ValueError(
                        f"確率を取得できません: {link.get_text(strip=True)}"
                    )

                probability = float(probability_match.group(1)) / 100

            item_data["probability"] = probability

        items.append(item_data)

    return items

def parse_recipe(recipe_element) -> dict:
    """レシピ1件を辞書に変換する。"""
    title_link = recipe_element.select_one(
        "a.recipe-title-link"
    )

    if title_link is None:
        raise ValueError("レシピ名が見つかりません")

    recipe_id = get_id_from_url(title_link["href"])
    recipe_name = (
        title_link.get_text(strip=True)
        .removeprefix("レシピ:")
        .strip()
    )

    # 製作時間
    details = recipe_element.select_one(".recipe-details")
    if details is None:
        raise ValueError(f"詳細情報がありません: {recipe_id}")

    time_match = re.search(
        r"時間:\s*(\d+(?:\.\d+)?)\s*s",
        details.get_text(" ", strip=True),
    )

    if time_match is None:
        raise ValueError(f"製作時間を取得できません: {recipe_id}")

    craft_time = float(time_match.group(1))

    # 設備
    device_link = details.select_one('a[href*="/device/"]')

    device_id = (
        get_id_from_url(device_link["href"])
        if device_link
        else None
    )

    device_name = (
        device_link.get_text(strip=True)
        if device_link
        else None
    )

    return {
        "recipe_id": recipe_id,
        "recipe_name": recipe_name,
        "url": urljoin(BASE_URL, title_link["href"]),
        "craft_time_seconds": craft_time,
        "device_id": device_id,
        "device_name": device_name,
        "inputs": parse_items(recipe_element, "ingredients"),
        "outputs": parse_items(recipe_element, "outputs"),
    }


def main():
    response = requests.get(RECIPES_URL, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    parsed_recipes = [
        parse_recipe(element)
        for element in soup.select("div.recipe")
    ]

    unique_recipes = {}

    for recipe in parsed_recipes:
        recipe_id = recipe["recipe_id"]

        if recipe_id not in unique_recipes:
            unique_recipes[recipe_id] = recipe
            continue

        if unique_recipes[recipe_id] != recipe:
            raise ValueError(
                f"同じIDで異なるレシピを検出: {recipe_id}"
            )

        print(f"重複をスキップ: {recipe_id}")

    recipes = list(unique_recipes.values())

    print(f"抽出件数: {len(parsed_recipes)}")
    print(f"重複排除後: {len(recipes)}")

    # レシピIDの重複検証
    recipe_ids = [r["recipe_id"] for r in recipes]

    from collections import Counter

    counts = Counter(recipe_ids)

    duplicates = {
        recipe_id: count
        for recipe_id, count in counts.items()
        if count > 1
    }

    if duplicates:
        print(f"重複レシピ数: {len(duplicates)}")

        for recipe_id, count in duplicates.items():
            print(f"  {recipe_id}: {count}件")

            for recipe in recipes:
                if recipe["recipe_id"] == recipe_id:
                    print(
                        f"    名前: {recipe['recipe_name']}, "
                        f"設備: {recipe['device_name']}, "
                        f"入力: {recipe['inputs']}, "
                        f"出力: {recipe['outputs']}"
                    )

        raise ValueError("レシピIDが重複しています")

    # JSONファイルへ保存
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(recipes, f, ensure_ascii=False, indent=2)

    print(f"取得レシピ数: {len(recipes)}")
    print(f"保存先: {OUTPUT_PATH}")

    # 幽暗胞子を確認
    gloom_spores = next(
        (r for r in recipes if r["recipe_id"] == "gloom-spores"),
        None,
    )

    if gloom_spores:
        print("\n--- 幽暗胞子 ---")
        print(json.dumps(gloom_spores, ensure_ascii=False, indent=2))

    coke = next(
        r for r in recipes
        if r["recipe_id"] == "coke-and-charcoal"
    )

    print("\n--- コークス ---")
    print(json.dumps(coke, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()