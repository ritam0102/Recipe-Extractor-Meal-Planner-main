from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app import llm
from app.config import settings
from app.database import get_db, init_db
from app.schemas import ExtractRequest, MealPlanOut, MealPlanRequest, RecipeOut, RecipeSummary, UrlPreviewOut
from app.services import ScrapeError, build_meal_plan, extract_and_store_recipe, get_recipe, list_recipes, preview_recipe_url

app = FastAPI(title="Recipe Extractor & Meal Planner", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.post("/api/recipes/extract", response_model=RecipeOut)
def extract_recipe(request: ExtractRequest, db: Session = Depends(get_db)) -> RecipeOut:
    try:
        return extract_and_store_recipe(str(request.url), db)
    except ScrapeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except llm.LLMUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/recipes/preview", response_model=UrlPreviewOut)
def preview_recipe(request: ExtractRequest) -> UrlPreviewOut:
    try:
        return preview_recipe_url(str(request.url))
    except ScrapeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/recipes", response_model=list[RecipeSummary])
def recipe_history(db: Session = Depends(get_db)) -> list[RecipeSummary]:
    return list_recipes(db)


@app.get("/api/recipes/{recipe_id}", response_model=RecipeOut)
def recipe_details(recipe_id: int, db: Session = Depends(get_db)) -> RecipeOut:
    recipe = get_recipe(recipe_id, db)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe


@app.post("/api/meal-plan", response_model=MealPlanOut)
def meal_plan(request: MealPlanRequest, db: Session = Depends(get_db)) -> MealPlanOut:
    try:
        return build_meal_plan(request.recipe_ids, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


if settings.frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=settings.frontend_dir), name="static")


@app.get("/", include_in_schema=False)
def frontend() -> FileResponse:
    return FileResponse(settings.frontend_dir / "index.html")
