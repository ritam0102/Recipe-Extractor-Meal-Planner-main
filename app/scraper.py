from __future__ import annotations

import json
import re
from html import escape
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from app.config import settings


class ScrapeError(RuntimeError):
    pass


BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Upgrade-Insecure-Requests": "1",
}

BLOCKED_STATUS_CODES = {401, 402, 403, 429, 451}
READER_FALLBACK_PREFIX = "https://r.jina.ai/http://r.jina.ai/http://"


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

    blocked_error = ""
    try:
        response = requests.get(
            url,
            headers={**BROWSER_HEADERS, "Referer": f"{parsed.scheme}://{parsed.netloc}/"},
            timeout=settings.request_timeout_seconds,
        )
        if response.status_code in BLOCKED_STATUS_CODES:
            blocked_error = (
                "The recipe site blocked the hosted server request "
                f"({response.status_code} {response.reason}). "
            )
            raise requests.HTTPError(blocked_error)
        response.raise_for_status()
    except requests.RequestException as exc:
        fallback_html = fetch_reader_fallback(url)
        if fallback_html:
            return fallback_html
        if blocked_error:
            raise ScrapeError(
                f"{blocked_error} The reader fallback could not fetch this page. "
                "Try another public recipe URL, or run the app locally for this site."
            ) from exc
        raise ScrapeError(f"Could not fetch the recipe page: {exc}") from exc

    return response.text


def fetch_reader_fallback(url: str) -> str:
    try:
        response = requests.get(
            f"{READER_FALLBACK_PREFIX}{url}",
            headers={"User-Agent": BROWSER_HEADERS["User-Agent"], "Accept": "text/plain,*/*;q=0.8"},
            timeout=settings.request_timeout_seconds,
        )
        response.raise_for_status()
    except requests.RequestException:
        return ""

    text = response.text.strip()
    if not text:
        return ""
    return reader_markdown_to_html(url, text)


def reader_markdown_to_html(url: str, markdown: str) -> str:
    title = extract_reader_title(markdown) or "Untitled recipe"
    body = extract_reader_recipe_section(markdown)
    paragraphs = "\n".join(f"<p>{escape(line.strip())}</p>" for line in body.splitlines() if line.strip())
    return (
        "<html>"
        f"<head><title>{escape(title)}</title><meta name=\"description\" content=\"Recipe content from {escape(url)}\"></head>"
        f"<body><article><h1>{escape(title)}</h1>{paragraphs}</article></body>"
        "</html>"
    )


def extract_reader_title(markdown: str) -> str:
    match = re.search(r"^Title:\s*(.+)$", markdown, flags=re.MULTILINE)
    if match:
        return match.group(1).strip()
    match = re.search(r"^#\s+(.+)$", markdown, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def extract_reader_recipe_section(markdown: str) -> str:
    markers = [
        "\nPrep Time:",
        "\nCook Time:",
        "\nTotal Time:",
        "\nServings:",
        "\n## Ingredients",
        "\n## Directions",
        "\n## Instructions",
    ]
    starts = [index for marker in markers if (index := markdown.find(marker)) >= 0]
    if not starts:
        return markdown[: settings.max_scraped_chars]

    start = max(min(starts) - 1200, 0)
    relevant = markdown[start:]
    end_markers = ["\n## Nutrition Facts", "\n## Reviews", "\n## Photos", "\nYou may also like"]
    ends = [index for marker in end_markers if (index := relevant.find(marker)) > 0]
    if ends:
        relevant = relevant[: min(ends)]
    return relevant[: settings.max_scraped_chars]


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
