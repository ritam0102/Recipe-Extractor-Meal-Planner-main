from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from app.config import settings


class ScrapeError(RuntimeError):
    pass


@dataclass
class ScrapedPage:
    url: str
    title: str
    raw_html: str
    text: str
    recipe_json: dict[str, Any] | None


@dataclass
class UrlPreview:
    url: str
    title: str
    site_name: str
    description: str
    image: str | None


def scrape_recipe_page(url: str) -> ScrapedPage:
    response_text = fetch_page_html(url)
    soup = BeautifulSoup(response_text, "html.parser")
    recipe_json = extract_recipe_json_ld(soup)
    title = extract_title(soup, recipe_json)
    page_text = extract_visible_text(soup)

    if recipe_json:
        schema_text = recipe_json_to_text(recipe_json)
        page_text = f"{schema_text}\n\n{page_text}"

    return ScrapedPage(
        url=url,
        title=title,
        raw_html=response_text,
        text=page_text[: settings.max_scraped_chars],
        recipe_json=recipe_json,
    )


def preview_recipe_page(url: str) -> UrlPreview:
    response_text = fetch_page_html(url)
    soup = BeautifulSoup(response_text, "html.parser")
    recipe_json = extract_recipe_json_ld(soup)
    title = extract_title(soup, recipe_json)
    description = extract_meta_content(soup, "description") or extract_meta_property(soup, "og:description")
    site_name = extract_meta_property(soup, "og:site_name") or urlparse(url).netloc
    image = extract_meta_property(soup, "og:image")
    return UrlPreview(
        url=url,
        title=title,
        site_name=site_name or "unknown",
        description=description or "unknown",
        image=image,
    )


def fetch_page_html(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ScrapeError("Please provide a valid HTTP or HTTPS recipe URL.")

    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36 RecipeExtractor/1.0"
                )
            },
            timeout=settings.request_timeout_seconds,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ScrapeError(f"Could not fetch the recipe page: {exc}") from exc

    return response.text


def extract_recipe_json_ld(soup: BeautifulSoup) -> dict[str, Any] | None:
    for script in soup.find_all("script", type=lambda value: value and "ld+json" in value):
        raw = script.string or script.get_text()
        if not raw or not raw.strip():
            continue

        for candidate in _load_json_candidates(raw):
            recipe = _find_recipe(candidate)
            if recipe:
                return recipe
    return None


def _load_json_candidates(raw: str) -> list[Any]:
    cleaned = raw.strip()
    candidates: list[Any] = []
    try:
        candidates.append(json.loads(cleaned))
        return candidates
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    index = 0
    while index < len(cleaned):
        try:
            obj, end = decoder.raw_decode(cleaned[index:])
            candidates.append(obj)
            index += end
        except json.JSONDecodeError:
            index += 1
    return candidates


def _find_recipe(value: Any) -> dict[str, Any] | None:
    if isinstance(value, list):
        for item in value:
            recipe = _find_recipe(item)
            if recipe:
                return recipe
        return None

    if not isinstance(value, dict):
        return None

    type_value = value.get("@type") or value.get("type")
    types = type_value if isinstance(type_value, list) else [type_value]
    if any(str(item).lower() == "recipe" for item in types if item):
        return value

    graph = value.get("@graph")
    if graph:
        recipe = _find_recipe(graph)
        if recipe:
            return recipe

    for child in value.values():
        recipe = _find_recipe(child)
        if recipe:
            return recipe
    return None


def extract_title(soup: BeautifulSoup, recipe_json: dict[str, Any] | None) -> str:
    if recipe_json:
        title = _string_or_first(recipe_json.get("name"))
        if title:
            return title

    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        return og_title["content"].strip()

    if soup.title and soup.title.string:
        return soup.title.string.strip()

    h1 = soup.find("h1")
    if h1:
        return h1.get_text(" ", strip=True)
    return "Untitled recipe"


def extract_meta_content(soup: BeautifulSoup, name: str) -> str:
    tag = soup.find("meta", attrs={"name": name})
    return tag["content"].strip() if tag and tag.get("content") else ""


def extract_meta_property(soup: BeautifulSoup, property_name: str) -> str:
    tag = soup.find("meta", property=property_name)
    return tag["content"].strip() if tag and tag.get("content") else ""


def extract_visible_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "form", "nav", "header", "footer"]):
        tag.decompose()

    root = soup.find("article") or soup.find("main") or soup.body or soup
    parts: list[str] = []
    previous = ""
    for piece in root.stripped_strings:
        clean = re.sub(r"\s+", " ", piece).strip()
        if not clean or clean == previous:
            continue
        if len(clean) > 240 and not any(mark in clean for mark in [".", ",", ";", ":"]):
            continue
        parts.append(clean)
        previous = clean
    return "\n".join(parts)


def recipe_json_to_text(recipe_json: dict[str, Any]) -> str:
    lines: list[str] = []
    for key in ["name", "description", "recipeCuisine", "prepTime", "cookTime", "totalTime", "recipeYield"]:
        value = recipe_json.get(key)
        if value:
            lines.append(f"{key}: {_string_or_first(value)}")

    ingredients = recipe_json.get("recipeIngredient") or []
    if ingredients:
        lines.append("ingredients:")
        lines.extend(f"- {item}" for item in ingredients if item)

    instructions = recipe_json.get("recipeInstructions") or []
    normalized_steps = _instruction_texts(instructions)
    if normalized_steps:
        lines.append("instructions:")
        lines.extend(f"{index}. {step}" for index, step in enumerate(normalized_steps, start=1))
    return "\n".join(lines)


def _instruction_texts(value: Any) -> list[str]:
    steps: list[str] = []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        for item in value:
            steps.extend(_instruction_texts(item))
        return steps
    if isinstance(value, dict):
        if value.get("@type") == "HowToSection":
            return _instruction_texts(value.get("itemListElement") or [])
        text = value.get("text") or value.get("name")
        if text:
            steps.append(str(text).strip())
        steps.extend(_instruction_texts(value.get("itemListElement") or []))
    return steps


def _string_or_first(value: Any) -> str:
    if isinstance(value, list):
        return _string_or_first(value[0]) if value else ""
    if isinstance(value, dict):
        return str(value.get("name") or value.get("text") or "").strip()
    return str(value or "").strip()
