import pytest
import requests

from app.scraper import ScrapeError, fetch_page_html


class FakeResponse:
    def __init__(self, status_code=200, reason="OK", text="<html>Recipe</html>"):
        self.status_code = status_code
        self.reason = reason
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} {self.reason}")


def test_fetch_page_html_uses_browser_headers(monkeypatch):
    captured = {}

    def fake_get(url, headers, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("app.scraper.requests.get", fake_get)

    html = fetch_page_html("https://example.com/recipe")

    assert html == "<html>Recipe</html>"
    assert "Mozilla/5.0" in captured["headers"]["User-Agent"]
    assert captured["headers"]["Accept-Language"] == "en-US,en;q=0.9"
    assert captured["headers"]["Referer"] == "https://example.com/"


def test_fetch_page_html_explains_blocked_hosted_requests(monkeypatch):
    def fake_get(url, headers, timeout):
        return FakeResponse(status_code=402, reason="Payment Required")

    monkeypatch.setattr("app.scraper.requests.get", fake_get)

    with pytest.raises(ScrapeError, match="blocked the hosted server request"):
        fetch_page_html("https://example.com/recipe")


def test_fetch_page_html_uses_reader_fallback_after_block(monkeypatch):
    calls = []

    def fake_get(url, headers, timeout):
        calls.append(url)
        if len(calls) == 1:
            return FakeResponse(status_code=402, reason="Payment Required")
        return FakeResponse(
            text=(
                "Title: Grilled Cheese Sandwich\n\n"
                "Navigation text\n\n"
                "Cook Time:\n10 mins\n\n"
                "Servings:\n2\n\n"
                "## Ingredients\n"
                "* 4 slices white bread\n"
                "* 3 tablespoons butter\n"
                "* 2 slices Cheddar cheese\n\n"
                "## Directions\n"
                "1. Gather all ingredients.\n"
                "2. Cook until cheese is melted.\n"
            )
        )

    monkeypatch.setattr("app.scraper.requests.get", fake_get)

    html = fetch_page_html("https://example.com/recipe")

    assert calls[0] == "https://example.com/recipe"
    assert calls[1] == "https://r.jina.ai/http://r.jina.ai/http://https://example.com/recipe"
    assert "<title>Grilled Cheese Sandwich</title>" in html
    assert "4 slices white bread" in html
    assert "Cook until cheese is melted" in html
