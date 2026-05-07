# Recipe Extractor & Meal Planner

A complete FastAPI recipe extraction app with a minimal two-tab frontend, PostgreSQL persistence, BeautifulSoup scraping, and LangChain prompt templates for Gemini.

## Features

- Extracts recipe content from recipe blog URLs using BeautifulSoup.
- Uses schema.org JSON-LD when available for cleaner extraction.
- Calls Gemini through LangChain when `GOOGLE_API_KEY` or `GEMINI_API_KEY` is configured.
- Requires Gemini-generated outputs in assignment mode with `REQUIRE_LLM=true`.
- Stores every processed recipe in a database.
- Stores raw HTML and scraped text for auditability.
- Shows URL preview, saved recipes, a details modal, and an optional meal planner with combined shopping lists.

## Project Structure

```text
app/                 FastAPI backend
frontend/            Static HTML/CSS/JS UI served by FastAPI
prompts/             LangChain prompt templates
sample_data/         Example URLs and JSON API outputs
screenshots/         Required UI screenshots
tests/               Lightweight parser tests
docker-compose.yml   Local PostgreSQL service
```

## Setup

1. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

2. Start PostgreSQL:

```bash
docker compose up -d postgres
```

3. Copy `.env.example` to `.env` and fill in values:

```bash
copy .env.example .env
```

For final assignment runs, set either `GOOGLE_API_KEY` or `GEMINI_API_KEY`. With `REQUIRE_LLM=true`, recipe extraction returns an error if Gemini is not configured, ensuring generated outputs come from the LLM.

4. Run the app:

```bash
uvicorn app.main:app --reload
```

5. Optional: seed two sample recipes for demos and screenshots:

```bash
python scripts/seed_sample_data.py
```

6. Open the UI:

[http://127.0.0.1:8000](http://127.0.0.1:8000)

If `DATABASE_URL` is not set, the app uses a local SQLite database for quick demos. Set `DATABASE_URL` to the PostgreSQL URL from `.env.example` for the required PostgreSQL deployment path.

## API Endpoints

- `POST /api/recipes/extract`

```json
{ "url": "https://www.allrecipes.com/recipe/23891/grilled-cheese-sandwich/" }
```

- `POST /api/recipes/preview`

```json
{ "url": "https://www.allrecipes.com/recipe/23891/grilled-cheese-sandwich/" }
```

Returns URL metadata for the preview card before extraction.

- `GET /api/recipes`

Returns saved recipe history.

- `GET /api/recipes/{id}`

Returns the full saved recipe.

- `POST /api/meal-plan`

```json
{ "recipe_ids": [1, 2, 3] }
```

Returns a combined shopping list grouped by category.

## Testing

```bash
pytest
```

## Screenshots

The required screenshots are saved in `screenshots/`:

- `extract_recipe_page.png`
- `history_view.png`
- `details_modal.png`


The prompts instruct the LLM to ground its output in scraped page text and available schema.org data, return strict JSON only, avoid inventing missing timings or ingredients, and mark uncertain fields as `"unknown"` where appropriate.


##Working ScreenShots:
<img width="1440" height="1100" alt="extract_recipe_page" src="https://github.com/user-attachments/assets/635b18bd-4146-4bf1-a689-a22134fe18b6" />
<img width="1440" height="1100" alt="history_view" src="https://github.com/user-attachments/assets/735da471-33f0-4edb-8b38-f5e0e07e4ca7" />
<img width="1440" height="1100" alt="extract_recipe_page" src="https://github.com/user-attachments/assets/76cc4ff7-f0ed-4885-b880-c93c3afbb825" />

