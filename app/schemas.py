from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class ExtractRequest(BaseModel):
    url: HttpUrl


class Ingredient(BaseModel):
    quantity: str = ""
    unit: str = ""
    item: str


class NutritionEstimate(BaseModel):
    calories: int | str = "unknown"
    protein: str = "unknown"
    carbs: str = "unknown"
    fat: str = "unknown"


class RecipeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    title: str
    cuisine: str
    prep_time: str
    cook_time: str
    total_time: str
    servings: int | None
    difficulty: str
    ingredients: list[Ingredient] = Field(default_factory=list)
    instructions: list[str] = Field(default_factory=list)
    nutrition_estimate: NutritionEstimate = Field(default_factory=NutritionEstimate)
    substitutions: list[str] = Field(default_factory=list)
    shopping_list: dict[str, list[str]] = Field(default_factory=dict)
    related_recipes: list[str] = Field(default_factory=list)
    created_at: datetime


class UrlPreviewOut(BaseModel):
    url: str
    title: str
    site_name: str = "unknown"
    description: str = "unknown"
    image: str | None = None


class RecipeSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    title: str
    cuisine: str
    difficulty: str
    created_at: datetime


class MealPlanRequest(BaseModel):
    recipe_ids: list[int] = Field(..., min_length=3, max_length=5)

    @field_validator("recipe_ids")
    @classmethod
    def unique_recipe_ids(cls, value: list[int]) -> list[int]:
        deduped = list(dict.fromkeys(value))
        if len(deduped) != len(value):
            raise ValueError("recipe_ids must be unique")
        return value


class MealPlanOut(BaseModel):
    recipe_ids: list[int]
    recipes: list[RecipeSummary]
    combined_shopping_list: dict[str, list[str]]
    notes: list[str] = Field(default_factory=list)
    raw_llm_output: dict[str, Any] = Field(default_factory=dict)
