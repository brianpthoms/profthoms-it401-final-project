from functools import lru_cache
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


class WikipediaScraper:
    """Find and extract a short, attributed overview from Wikipedia HTML."""

    RELEVANCE_TERMS = {
        "beach",
        "break",
        "coast",
        "coastal",
        "ocean",
        "surf",
        "surfer",
        "surfing",
        "wave",
    }

    def __init__(self, base_url="https://en.wikipedia.org", timeout=6):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = {
            "User-Agent": "Breakline/1.0 (educational surf forecast project)",
            "Accept": "text/html,application/xhtml+xml",
        }

    @lru_cache(maxsize=128)
    def get_spot_info(self, surf_break=None, city=None):
        search_name = (surf_break or city or "").strip()
        if not search_name:
            return None

        context = "surf break beach" if surf_break else "coastal city beach surfing"
        try:
            article_url = self._find_article(f"{search_name} {context}", search_name)
            return self._scrape_article(article_url, search_name) if article_url else None
        except (requests.RequestException, ValueError):
            return None

    def _find_article(self, query, search_name):
        response = requests.get(
            f"{self.base_url}/w/index.php",
            params={
                "title": "Special:Search",
                "search": query,
                "fulltext": "1",
                "ns0": "1",
            },
            headers=self.headers,
            timeout=self.timeout,
        )
        response.raise_for_status()

        if "/wiki/" in urlparse(response.url).path and "Special:Search" not in response.url:
            return response.url if self._is_wikipedia_article(response.url) else None

        soup = BeautifulSoup(response.text, "html.parser")
        candidates = []
        search_words = set(search_name.casefold().replace(",", " ").split())
        for result in soup.select("li.mw-search-result")[:8]:
            link = result.select_one(".mw-search-result-heading a")
            if not link or not link.get("href"):
                continue
            url = urljoin(self.base_url, link["href"])
            if not self._is_wikipedia_article(url):
                continue

            title = link.get_text(" ", strip=True).casefold()
            result_text = result.get_text(" ", strip=True).casefold()
            title_words = set(title.replace(",", " ").split())
            score = 4 * len(search_words & title_words)
            score += sum(term in result_text for term in self.RELEVANCE_TERMS)
            if title == search_name.casefold():
                score += 10
            candidates.append((score, url))

        return max(candidates, default=(None, None))[1]

    def _scrape_article(self, article_url, search_name):
        response = requests.get(
            article_url,
            headers=self.headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        heading = soup.select_one("h1#firstHeading")
        paragraphs = []
        article_paragraphs = soup.select("#mw-content-text .mw-parser-output > p")
        if not article_paragraphs:
            article_paragraphs = soup.select("#mw-content-text p")
        for paragraph in article_paragraphs:
            for unwanted in paragraph.select("sup, style"):
                unwanted.decompose()
            text = " ".join(paragraph.get_text(" ", strip=True).split())
            if len(text) >= 80:
                paragraphs.append(text)
            if len(paragraphs) == 2:
                break

        if not heading or not paragraphs:
            return None

        combined_text = " ".join(paragraphs)
        relevance_text = f"{heading.get_text(' ', strip=True)} {combined_text}".casefold()
        search_words = set(search_name.casefold().replace(",", " ").split())
        if not any(word in relevance_text for word in search_words):
            return None
        if not any(term in relevance_text for term in self.RELEVANCE_TERMS):
            return None

        summary = combined_text
        if len(summary) > 900:
            summary = summary[:900].rsplit(" ", 1)[0] + "…"

        return {
            "title": heading.get_text(" ", strip=True),
            "summary": summary,
            "url": article_url,
        }

    def _is_wikipedia_article(self, url):
        parsed_url = urlparse(url)
        parsed_base = urlparse(self.base_url)
        return (
            parsed_url.scheme in ("http", "https")
            and parsed_url.netloc == parsed_base.netloc
            and parsed_url.path.startswith("/wiki/")
            and ":" not in parsed_url.path.removeprefix("/wiki/")
        )
