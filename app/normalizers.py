from __future__ import annotations

import re
from collections import defaultdict
from fractions import Fraction
from typing import Any

UNIT_WORDS = {
    "bag",
    "bags",
    "can",
    "cans",
    "clove",
    "cloves",
    "cup",
    "cups",
    "dash",
    "dashes",
    "g",
    "gallon",
    "gallons",
    "gram",
    "grams",
    "kg",
    "l",
    "lb",
    "lbs",
    "liter",
    "liters",
    "ml",
    "ounce",
    "ounces",
    "oz",
    "package",
    "packages",
    "pinch",
    "pinches",
    "pint",
    "pints",
    "pkg",
    "pound",
    "pounds",
    "quart",
    "quarts",
    "slice",
    "slices",
    "sprig",
    "sprigs",
    "tablespoon",
    "tablespoons",
    "tbsp",
    "teaspoon",
    "teaspoons",
    "tsp",
}

PLURAL_UNITS = {
    "bag": "bags",
    "can": "cans",
    "clove": "cloves",
    "cup": "cups",
    "dash": "dashes",
    "gallon": "gallons",
    "gram": "grams",
    "liter": "liters",
    "ounce": "ounces",
    "package": "packages",
    "pinch": "pinches",
    "pint": "pints",
    "pound": "pounds",
    "quart": "quarts",
    "slice": "slices",
    "sprig": "sprigs",
    "tablespoon": "tablespoons",
    "teaspoon": "teaspoons",
}

FRACTION_CHARS = {
    "¼": "1/4",
    "½": "1/2",
    "¾": "3/4",
    "⅓": "1/3",
    "⅔": "2/3",
    "⅛": "1/8",
    "⅜": "3/8",
    "⅝": "5/8",
    "⅞": "7/8",
}

CATEGORY_KEYWORDS = {
    "dairy": ["butter", "cheese", "milk", "cream", "yogurt", "mozzarella", "cheddar", "parmesan"],
    "produce": ["tomato", "onion", "garlic", "lettuce", "basil", "cilantro", "pepper", "carrot", "celery", "spinach", "lemon", "lime"],
    "meat": ["chicken", "beef", "pork", "bacon", "turkey", "sausage", "ham", "fish", "shrimp"],
    "bakery": ["bread", "bun", "roll", "tortilla", "baguette", "pita"],
    "pantry": ["flour", "sugar", "oil", "vinegar", "rice", "pasta", "salt", "pepper", "spice", "sauce", "beans", "broth"],
}


def normalize_recipe_payload(
    url: str,
    scraped_title: str,
    recipe_json: dict[str, Any] | None,
    llm_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    base = payload_from_schema(url, scraped_title, recipe_json)
    llm_payload = llm_payload or {}

    extraction = llm_payload.get("recipe") if "recipe" in llm_payload else llm_payload
    if isinstance(extraction, dict):
        for key in [
            "title",
            "cuisine",
            "prep_time",
            "cook_time",
            "total_time",
            "servings",
            "difficulty",
            "ingredients",
            "instructions",
        ]:
            value = extraction.get(key)
            if _has_value(value):
                base[key] = value

    nutrition = llm_payload.get("nutrition") or llm_payload.get("nutrition_estimate")
    if isinstance(nutrition, dict) and nutrition:
        base["nutrition_estimate"] = _normalize_nutrition(nutrition)

    substitutions = llm_payload.get("substitutions")
    if isinstance(substitutions, list) and substitutions:
        base["substitutions"] = [str(item).strip() for item in substitutions if str(item).strip()][:3]

    shopping_list = llm_payload.get("shopping_list")
    if isinstance(shopping_list, dict) and shopping_list:
        base["shopping_list"] = {
            str(category).strip().lower(): [str(item).strip() for item in items if str(item).strip()]
            for category, items in shopping_list.items()
            if isinstance(items, list)
        }

    related = llm_payload.get("related_recipes")
    if isinstance(related, list) and related:
        base["related_recipes"] = [str(item).strip() for item in related if str(item).strip()][:3]

    base["ingredients"] = normalize_ingredients(base.get("ingredients") or [])
    base["instructions"] = normalize_instructions(base.get("instructions") or [])
    base["servings"] = normalize_servings(base.get("servings"))
    base["difficulty"] = normalize_difficulty(base.get("difficulty"), base)

    if not base["shopping_list"]:
        base["shopping_list"] = build_shopping_list(base["ingredients"])
    if not _nutrition_complete(base["nutrition_estimate"]):
        base["nutrition_estimate"] = estimate_nutrition(base["ingredients"], base.get("servings") or 1)
    if len(base["substitutions"]) < 3:
        base["substitutions"] = generate_substitutions(base["ingredients"], base["substitutions"])
    if len(base["related_recipes"]) < 3:
        base["related_recipes"] = generate_related_recipes(base["title"], base["cuisine"], base["related_recipes"])

    return base


def payload_from_schema(url: str, scraped_title: str, recipe_json: dict[str, Any] | None) -> dict[str, Any]:
    recipe_json = recipe_json or {}
    nutrition = recipe_json.get("nutrition") if isinstance(recipe_json.get("nutrition"), dict) else {}

    return {
        "url": url,
        "title": _string_or_first(recipe_json.get("name")) or scraped_title or "Untitled recipe",
        "cuisine": _string_or_first(recipe_json.get("recipeCuisine")) or "unknown",
        "prep_time": humanize_duration(_string_or_first(recipe_json.get("prepTime"))) or "unknown",
        "cook_time": humanize_duration(_string_or_first(recipe_json.get("cookTime"))) or "unknown",
        "total_time": humanize_duration(_string_or_first(recipe_json.get("totalTime"))) or "unknown",
        "servings": normalize_servings(recipe_json.get("recipeYield")),
        "difficulty": "easy",
        "ingredients": normalize_ingredients(recipe_json.get("recipeIngredient") or []),
        "instructions": normalize_instructions(recipe_json.get("recipeInstructions") or []),
        "nutrition_estimate": _normalize_nutrition(
            {
                "calories": nutrition.get("calories") or nutrition.get("calorieContent") or "unknown",
                "protein": nutrition.get("proteinContent") or "unknown",
                "carbs": nutrition.get("carbohydrateContent") or "unknown",
                "fat": nutrition.get("fatContent") or "unknown",
            }
        ),
        "substitutions": [],
        "shopping_list": {},
        "related_recipes": [],
    }


def normalize_ingredients(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    normalized: list[dict[str, str]] = []
    for item in value:
        if isinstance(item, dict):
            quantity = str(item.get("quantity") or "").strip()
            unit = str(item.get("unit") or "").strip()
            name = str(item.get("item") or item.get("name") or "").strip()
            if name:
                normalized.append({"quantity": quantity, "unit": unit, "item": clean_item_name(name)})
            continue

        text = str(item or "").strip()
        if not text:
            continue
        normalized.append(parse_ingredient(text))
    return normalized


def parse_ingredient(text: str) -> dict[str, str]:
    clean = normalize_fraction_chars(re.sub(r"\s+", " ", text).strip())
    clean = re.sub(r"^\d+\)\s*", "", clean)
    tokens = clean.split()
    if not tokens:
        return {"quantity": "", "unit": "", "item": ""}

    quantity_tokens: list[str] = []
    index = 0
    while index < len(tokens) and _looks_like_quantity_token(tokens[index]):
        quantity_tokens.append(tokens[index])
        index += 1
        if index < len(tokens) and tokens[index].lower() in {"to", "-"}:
            quantity_tokens.append(tokens[index])
            index += 1

    unit = ""
    if index < len(tokens) and tokens[index].lower().rstrip(".") in UNIT_WORDS:
        unit = tokens[index].rstrip(".")
        index += 1

    item = " ".join(tokens[index:]).strip(" ,")
    if not item and unit:
        item = unit
        unit = ""

    return {
        "quantity": " ".join(quantity_tokens).strip(),
        "unit": unit,
        "item": clean_item_name(item or clean),
    }


def normalize_instructions(value: Any) -> list[str]:
    steps: list[str] = []
    if isinstance(value, str):
        chunks = re.split(r"(?<=[.!?])\s+(?=[A-Z])", value)
        steps.extend(chunk.strip() for chunk in chunks if chunk.strip())
    elif isinstance(value, list):
        for item in value:
            steps.extend(normalize_instructions(item))
    elif isinstance(value, dict):
        if value.get("@type") == "HowToSection":
            steps.extend(normalize_instructions(value.get("itemListElement") or []))
        else:
            text = value.get("text") or value.get("name")
            if text:
                steps.append(str(text).strip())
            steps.extend(normalize_instructions(value.get("itemListElement") or []))

    cleaned: list[str] = []
    for step in steps:
        step = re.sub(r"\s+", " ", step).strip()
        if step and step not in cleaned:
            cleaned.append(step)
    return cleaned


def build_shopping_list(ingredients: list[dict[str, str]]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for ingredient in ingredients:
        item = ingredient.get("item", "").strip()
        if not item:
            continue
        category = categorize_item(item)
        if item not in grouped[category]:
            grouped[category].append(item)
    return dict(sorted(grouped.items()))


def categorize_item(item: str) -> str:
    lowered = item.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return category
    return "pantry"


def estimate_nutrition(ingredients: list[dict[str, str]], servings: int) -> dict[str, Any]:
    score = sum(_ingredient_calorie_guess(item.get("item", "")) for item in ingredients)
    servings = max(servings or 1, 1)
    calories = max(round(score / servings), 120)
    protein = max(round(calories * 0.09 / 4), 4)
    carbs = max(round(calories * 0.43 / 4), 10)
    fat = max(round(calories * 0.35 / 9), 4)
    return {
        "calories": calories,
        "protein": f"{protein}g",
        "carbs": f"{carbs}g",
        "fat": f"{fat}g",
    }


def generate_substitutions(
    ingredients: list[dict[str, str]],
    existing: list[str] | None = None,
) -> list[str]:
    substitutions = list(existing or [])
    ingredient_text = " ".join(item.get("item", "").lower() for item in ingredients)

    candidates = []
    if "butter" in ingredient_text:
        candidates.append("Replace butter with olive oil for a dairy-free option.")
    if "white bread" in ingredient_text or "bread" in ingredient_text:
        candidates.append("Use whole wheat bread instead of white bread for more fiber.")
    if "cheese" in ingredient_text or "cheddar" in ingredient_text:
        candidates.append("Swap cheddar with mozzarella for a milder, stretchier cheese.")
    if "cream" in ingredient_text or "milk" in ingredient_text:
        candidates.append("Use unsweetened oat milk or coconut milk for a dairy-free version.")
    if "sugar" in ingredient_text:
        candidates.append("Reduce sugar slightly or use maple syrup for a less refined sweetener.")

    candidates.extend(
        [
            "Add extra vegetables to increase fiber and freshness.",
            "Use a lower-sodium broth or seasoning blend to reduce sodium.",
            "Choose gluten-free bread or pasta if serving someone avoiding gluten.",
        ]
    )

    for candidate in candidates:
        if candidate not in substitutions:
            substitutions.append(candidate)
        if len(substitutions) >= 3:
            break
    return substitutions[:3]


def generate_related_recipes(title: str, cuisine: str, existing: list[str] | None = None) -> list[str]:
    related = list(existing or [])
    lowered = title.lower()
    if "grilled cheese" in lowered:
        candidates = ["Tomato Soup", "French Onion Grilled Cheese", "Caprese Sandwich"]
    elif "soup" in lowered:
        candidates = ["Garlic Bread", "Green Salad", "Grilled Cheese Sandwich"]
    elif "pasta" in lowered:
        candidates = ["Caesar Salad", "Garlic Bread", "Roasted Vegetables"]
    else:
        cuisine_label = cuisine.title() if cuisine and cuisine != "unknown" else "Seasonal"
        candidates = [f"{cuisine_label} Side Salad", "Roasted Vegetables", "Simple Soup"]

    for candidate in candidates:
        if candidate not in related:
            related.append(candidate)
        if len(related) >= 3:
            break
    return related[:3]


def normalize_difficulty(value: Any, payload: dict[str, Any]) -> str:
    difficulty = str(value or "").strip().lower()
    if difficulty in {"easy", "medium", "hard"}:
        return difficulty

    step_count = len(payload.get("instructions") or [])
    ingredient_count = len(payload.get("ingredients") or [])
    total_minutes = duration_to_minutes(payload.get("total_time"))
    if total_minutes and total_minutes > 75 or step_count > 9 or ingredient_count > 12:
        return "hard"
    if total_minutes and total_minutes > 35 or step_count > 5 or ingredient_count > 8:
        return "medium"
    return "easy"


def normalize_servings(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, list):
        return normalize_servings(value[0]) if value else None
    if value is None:
        return None
    match = re.search(r"\d+", str(value))
    return int(match.group()) if match else None


def humanize_duration(value: str) -> str:
    if not value:
        return ""
    minutes = duration_to_minutes(value)
    if not minutes:
        return value
    hours, mins = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours} hr" if hours == 1 else f"{hours} hrs")
    if mins:
        parts.append(f"{mins} min" if mins == 1 else f"{mins} mins")
    return " ".join(parts) or "0 mins"


def duration_to_minutes(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    iso_match = re.fullmatch(
        r"P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?",
        text,
        flags=re.IGNORECASE,
    )
    if iso_match:
        days = int(iso_match.group("days") or 0)
        hours = int(iso_match.group("hours") or 0)
        minutes = int(iso_match.group("minutes") or 0)
        seconds = int(iso_match.group("seconds") or 0)
        return days * 1440 + hours * 60 + minutes + (1 if seconds else 0)

    hour_match = re.search(r"(\d+)\s*(?:hr|hour)", text, flags=re.IGNORECASE)
    minute_match = re.search(r"(\d+)\s*(?:min|minute)", text, flags=re.IGNORECASE)
    total = 0
    if hour_match:
        total += int(hour_match.group(1)) * 60
    if minute_match:
        total += int(minute_match.group(1))
    return total or None


def merge_shopping_lists(recipes: list[Any]) -> dict[str, list[str]]:
    grouped: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for recipe in recipes:
        ingredients = normalize_ingredients(recipe.ingredients or [])
        for ingredient in ingredients:
            item = ingredient.get("item", "").strip()
            if not item:
                continue
            category = categorize_item(item)
            key = item.lower()
            unit = canonical_unit(ingredient.get("unit", ""))
            current = grouped[category].setdefault(
                key,
                {"quantity": 0.0, "unit": unit, "item": item, "raw": []},
            )
            amount = quantity_to_float(ingredient.get("quantity", ""))
            if amount is not None and (not current["unit"] or current["unit"] == unit):
                current["quantity"] += amount
                current["unit"] = unit
            else:
                current["raw"].append(format_ingredient(ingredient))

    output: dict[str, list[str]] = {}
    for category, items in grouped.items():
        output[category] = []
        for data in items.values():
            if data["raw"]:
                output[category].extend(data["raw"])
            elif data["quantity"]:
                quantity = float_to_quantity(data["quantity"])
                unit = display_unit(data["unit"], data["quantity"])
                label = " ".join(part for part in [quantity, unit, data["item"]] if part).strip()
                output[category].append(label)
            else:
                output[category].append(data["item"])
        output[category] = sorted(dict.fromkeys(output[category]))
    return dict(sorted(output.items()))


def format_ingredient(ingredient: dict[str, str]) -> str:
    return " ".join(
        part for part in [ingredient.get("quantity", ""), ingredient.get("unit", ""), ingredient.get("item", "")] if part
    ).strip()


def canonical_unit(value: str) -> str:
    unit = str(value or "").strip().lower().rstrip(".")
    if unit.endswith("s") and unit[:-1] in PLURAL_UNITS:
        return unit[:-1]
    reverse = {plural: singular for singular, plural in PLURAL_UNITS.items()}
    return reverse.get(unit, unit)


def display_unit(unit: str, quantity: float) -> str:
    if not unit:
        return ""
    if abs(quantity - 1) < 0.0001:
        return unit
    return PLURAL_UNITS.get(unit, unit)


def quantity_to_float(value: str) -> float | None:
    text = normalize_fraction_chars(str(value or "").strip())
    if not text:
        return None
    text = text.replace("-", " to ")
    first = text.split(" to ")[0].strip()
    try:
        if " " in first:
            whole, fraction = first.split(" ", 1)
            return float(whole) + float(Fraction(fraction))
        if "/" in first:
            return float(Fraction(first))
        return float(first)
    except (ValueError, ZeroDivisionError):
        return None


def float_to_quantity(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    fraction = Fraction(value).limit_denominator(8)
    if fraction.numerator > fraction.denominator:
        whole = fraction.numerator // fraction.denominator
        remainder = Fraction(fraction.numerator % fraction.denominator, fraction.denominator)
        return f"{whole} {remainder}"
    return str(fraction)


def normalize_fraction_chars(value: str) -> str:
    for char, replacement in FRACTION_CHARS.items():
        value = value.replace(char, f" {replacement}")
    return re.sub(r"\s+", " ", value).strip()


def clean_item_name(value: str) -> str:
    value = re.sub(r"\([^)]*\)", "", value)
    value = re.sub(r"\b(chopped|diced|minced|sliced|melted|softened|divided|optional)\b", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+", " ", value)
    return value.strip(" ,")


def _looks_like_quantity_token(value: str) -> bool:
    text = value.strip().lower()
    return bool(
        re.fullmatch(r"\d+(?:\.\d+)?", text)
        or re.fullmatch(r"\d+/\d+", text)
        or text in {"a", "an", "one", "two", "three", "four", "pinch", "dash"}
    )


def _ingredient_calorie_guess(item: str) -> int:
    lowered = item.lower()
    if any(word in lowered for word in ["oil", "butter"]):
        return 240
    if any(word in lowered for word in ["cheese", "cream"]):
        return 220
    if "bread" in lowered:
        return 160
    if any(word in lowered for word in ["rice", "pasta", "flour", "sugar"]):
        return 180
    if any(word in lowered for word in ["chicken", "beef", "pork", "fish", "shrimp"]):
        return 260
    if any(word in lowered for word in ["tomato", "onion", "lettuce", "carrot", "spinach", "pepper"]):
        return 35
    return 60


def _normalize_nutrition(value: dict[str, Any]) -> dict[str, Any]:
    calories = value.get("calories") or value.get("calorieContent") or "unknown"
    calorie_match = re.search(r"\d+", str(calories))
    return {
        "calories": int(calorie_match.group()) if calorie_match else calories,
        "protein": str(value.get("protein") or value.get("proteinContent") or "unknown"),
        "carbs": str(value.get("carbs") or value.get("carbohydrateContent") or "unknown"),
        "fat": str(value.get("fat") or value.get("fatContent") or "unknown"),
    }


def _nutrition_complete(value: dict[str, Any]) -> bool:
    if not value:
        return False
    return all(str(value.get(key, "unknown")).lower() != "unknown" for key in ["calories", "protein", "carbs", "fat"])


def _string_or_first(value: Any) -> str:
    if isinstance(value, list):
        return _string_or_first(value[0]) if value else ""
    if isinstance(value, dict):
        return str(value.get("name") or value.get("text") or "").strip()
    return str(value or "").strip()


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and value.strip().lower() in {"", "unknown", "n/a", "null"}:
        return False
    if isinstance(value, (list, dict)) and not value:
        return False
    return True
