"""生産計算と同じレシピ情報を使ったキーワード検索。"""

import unicodedata


def normalize(value):
    return unicodedata.normalize("NFKC", str(value or "")).casefold()


def search_recipes(recipe_options, item_names, query):
    """レシピを出力ごとに重複させず、空白区切りの全語で検索する。"""
    recipes = {}
    for item_id, options in recipe_options.items():
        for recipe in options:
            entry = recipes.setdefault(recipe["recipe_id"], {**recipe, "outputs": []})
            entry["outputs"].append((item_id, recipe["output_quantity"], recipe["probability"]))
    tokens = normalize(query).split()
    results = []
    for entry in recipes.values():
        fields = [entry["recipe_id"], entry["recipe_name"], entry["device_id"], entry["device_name"]]
        for item_id, _ in entry["inputs"]:
            fields.extend((item_id, item_names.get(item_id)))
        for item_id, _, _ in entry["outputs"]:
            fields.extend((item_id, item_names.get(item_id)))
        text = " ".join(normalize(field) for field in fields)
        if all(token in text for token in tokens):
            results.append(entry)
    return sorted(results, key=lambda entry: entry["recipe_id"])
