from app.normalizers import build_shopping_list, humanize_duration, merge_shopping_lists, normalize_ingredients


def test_parse_ingredient_separates_quantity_unit_and_item():
    ingredients = normalize_ingredients(["2 tbsp butter, softened", "4 slices white bread"])

    assert ingredients == [
        {"quantity": "2", "unit": "tbsp", "item": "butter"},
        {"quantity": "4", "unit": "slices", "item": "white bread"},
    ]


def test_humanize_iso_duration():
    assert humanize_duration("PT1H15M") == "1 hr 15 mins"
    assert humanize_duration("PT5M") == "5 mins"


def test_shopping_list_groups_known_categories():
    grouped = build_shopping_list(
        [
            {"quantity": "2", "unit": "tbsp", "item": "butter"},
            {"quantity": "4", "unit": "slices", "item": "white bread"},
            {"quantity": "1", "unit": "cup", "item": "tomatoes"},
        ]
    )

    assert grouped["dairy"] == ["butter"]
    assert grouped["bakery"] == ["white bread"]
    assert grouped["produce"] == ["tomatoes"]


def test_merge_shopping_lists_combines_matching_units():
    class Recipe:
        def __init__(self, ingredients):
            self.ingredients = ingredients

    merged = merge_shopping_lists(
        [
            Recipe([{"quantity": "2", "unit": "cups", "item": "tomatoes"}]),
            Recipe([{"quantity": "1", "unit": "cup", "item": "tomatoes"}]),
        ]
    )

    assert merged["produce"] == ["3 cups tomatoes"]
