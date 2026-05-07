from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal, init_db
from app.models import Recipe

SAMPLES = [
    ROOT / "sample_data" / "grilled_cheese_output.json",
    ROOT / "sample_data" / "tomato_soup_output.json",
]


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        for path in SAMPLES:
            payload = json.loads(path.read_text(encoding="utf-8"))
            recipe = db.query(Recipe).filter(Recipe.url == payload["url"]).one_or_none()
            if recipe is None:
                recipe = Recipe(url=payload["url"])
                db.add(recipe)
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
            recipe.raw_html = "<html><body>Seeded sample data for screenshots and demos.</body></html>"
            recipe.scraped_text = "Seeded sample data for screenshots and demos."
            recipe.raw_llm_output = {}
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
