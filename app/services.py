from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import llm
from app.models import Recipe
from app.normalizers import merge_shopping_lists, normalize_recipe_payload
from app.scraper import ScrapeError, preview_recipe_page, scrape_recipe_page


def extract_and_store_recipe(url: str, db: Session) -> Recipe:
    scraped = scrape_recipe_page(url)
    llm_payload = llm.generate_recipe_payload(scraped.url, scraped.text, scraped.recipe_json)
    payload = normalize_recipe_payload(scraped.url, scraped.title, scraped.recipe_json, llm_payload)
    raw_llm = llm_payload.get("raw", {}) if isinstance(llm_payload, dict) else {}

    recipe = db.scalar(select(Recipe).where(Recipe.url == scraped.url))
    if recipe is None:
        recipe = Recipe(url=scraped.url)
        db.add(recipe)

    apply_recipe_payload(recipe, payload, scraped.raw_html, scraped.text, raw_llm)
    db.commit()
    db.refresh(recipe)
    return recipe


def apply_recipe_payload(
    recipe: Recipe,
    payload: dict[str, Any],
    raw_html: str,
    scraped_text: str,
    raw_llm_output: dict[str, Any],
) -> None:
    recipe.title = payload["title"]
    recipe.cuisine = payload["cuisine"]
    recipe.prep_time = payload["prep_time"]
    recipe.cook_time = payload["cook_time"]
    recipe.total_time = payload["total_time"]
    recipe.servings = payload["servings"]
    recipe.difficulty = payload["difficulty"]
    recipe.ingredients = payload["ingredients"]
    recipe.instructions = payload["instructions"]
    recipe.nutrition_estimate = payload["nutrition_estimate"]
    recipe.substitutions = payload["substitutions"]
    recipe.shopping_list = payload["shopping_list"]
    recipe.related_recipes = payload["related_recipes"]
    recipe.raw_html = raw_html
    recipe.scraped_text = scraped_text
    recipe.raw_llm_output = raw_llm_output


def preview_recipe_url(url: str) -> dict[str, Any]:
    return preview_recipe_page(url).__dict__


def list_recipes(db: Session) -> list[Recipe]:
    return list(db.scalars(select(Recipe).order_by(Recipe.created_at.desc(), Recipe.id.desc())).all())


def get_recipe(recipe_id: int, db: Session) -> Recipe | None:
    return db.get(Recipe, recipe_id)


def build_meal_plan(recipe_ids: list[int], db: Session) -> dict[str, Any]:
    recipes = list(db.scalars(select(Recipe).where(Recipe.id.in_(recipe_ids))).all())
    found_ids = {recipe.id for recipe in recipes}
    missing = [recipe_id for recipe_id in recipe_ids if recipe_id not in found_ids]
    if missing:
        raise ValueError(f"Recipe ids not found: {', '.join(str(item) for item in missing)}")

    recipes.sort(key=lambda recipe: recipe_ids.index(recipe.id))
    deterministic_list = merge_shopping_lists(recipes)
    recipe_json = [
        {
            "id": recipe.id,
            "title": recipe.title,
            "ingredients": recipe.ingredients,
            "shopping_list": recipe.shopping_list,
        }
        for recipe in recipes
    ]
    llm_payload = llm.generate_meal_plan_with_llm(recipe_json) or {}
    combined = llm_payload.get("combined_shopping_list") if isinstance(llm_payload, dict) else None
    notes = llm_payload.get("notes") if isinstance(llm_payload, dict) else None

    return {
        "recipe_ids": recipe_ids,
        "recipes": recipes,
        "combined_shopping_list": combined if isinstance(combined, dict) and combined else deterministic_list,
        "notes": notes if isinstance(notes, list) else ["Quantities are merged when units and item names match exactly."],
        "raw_llm_output": llm_payload,
    }


__all__ = ["ScrapeError", "build_meal_plan", "extract_and_store_recipe", "get_recipe", "list_recipes", "preview_recipe_url"]
