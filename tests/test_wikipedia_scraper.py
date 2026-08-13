from services.wikipedia_scraper import WikipediaScraper


class FakeResponse:
    def __init__(self, text, url, status_code=200):
        self.text = text
        self.url = url
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(response=self)


SEARCH_HTML = """
<ul class="mw-search-results">
  <li class="mw-search-result">
    <div class="mw-search-result-heading"><a href="/wiki/Bodysurfing">Bodysurfing</a></div>
    <div>General information about riding waves.</div>
  </li>
  <li class="mw-search-result">
    <div class="mw-search-result-heading"><a href="/wiki/The_Wedge_(surfing)">The Wedge (surfing)</a></div>
    <div>The Wedge is a surf break and beach in Newport Beach.</div>
  </li>
</ul>
"""

ARTICLE_HTML = """
<h1 id="firstHeading">The Wedge (surfing)</h1>
<div id="mw-content-text"><div class="mw-parser-output">
  <p>The Wedge is a renowned surf break located at the southeastern tip of the Balboa Peninsula in Newport Beach, California.</p>
  <p>It is known for powerful waves created when incoming swell reflects from the nearby rock jetty.</p>
</div></div>
"""


def test_scrapes_best_matching_article(monkeypatch):
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append({"url": url, "params": params, "headers": headers})
        if params:
            return FakeResponse(SEARCH_HTML, "https://en.wikipedia.org/w/index.php")
        return FakeResponse(ARTICLE_HTML, url)

    monkeypatch.setattr("services.wikipedia_scraper.requests.get", fake_get)
    result = WikipediaScraper().get_spot_info(surf_break="The Wedge")

    assert result["title"] == "The Wedge (surfing)"
    assert "renowned surf break" in result["summary"]
    assert result["url"] == "https://en.wikipedia.org/wiki/The_Wedge_(surfing)"
    assert calls[0]["headers"]["User-Agent"].startswith("Breakline/")


def test_returns_none_when_no_relevant_article(monkeypatch):
    monkeypatch.setattr(
        "services.wikipedia_scraper.requests.get",
        lambda *args, **kwargs: FakeResponse(
            "<p>No search results</p>", "https://en.wikipedia.org/w/index.php"
        ),
    )

    assert WikipediaScraper().get_spot_info(city="Nowhere") is None


def test_supports_nested_wikipedia_article_paragraphs(monkeypatch):
    nested_article = """
    <h1 id="firstHeading">The Wedge (surfing)</h1>
    <div id="mw-content-text"><section><div>
      <p>The Wedge is a renowned surf break located at the southeastern tip of the Balboa Peninsula in Newport Beach, California.</p>
      <p>Its powerful waves form when incoming ocean swell reflects from the nearby rock jetty.</p>
    </div></section></div>
    """

    def fake_get(url, params=None, headers=None, timeout=None):
        if params:
            return FakeResponse(SEARCH_HTML, "https://en.wikipedia.org/w/index.php")
        return FakeResponse(nested_article, url)

    monkeypatch.setattr("services.wikipedia_scraper.requests.get", fake_get)

    result = WikipediaScraper().get_spot_info(surf_break="The Wedge")
    assert result["title"] == "The Wedge (surfing)"
