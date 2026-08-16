from functools import lru_cache

import requests


class WikipediaService:
    """Find a relevant Wikipedia article using the MediaWiki Action API."""

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

    def __init__(
        self,
        base_url="https://en.wikipedia.org",
        timeout=6,
        user_agent="Breakline/1.1 (https://brian.cikeys.com/)",
    ):
        self.api_url = f"{base_url.rstrip('/')}/w/api.php"
        self.timeout = timeout
        self.headers = {
            "User-Agent": user_agent,
            "Accept": "application/json",
        }

    @lru_cache(maxsize=128)
    def get_spot_info(self, surf_break=None, city=None):
        search_name = (surf_break or city or "").strip()
        if not search_name:
            return None

        context = "surf break beach" if surf_break else "coastal city beach surfing"
        try:
            pages = self._search(f"{search_name} {context}")
            return self._best_article(pages, search_name)
        except (requests.RequestException, TypeError, ValueError):
            return None

    def _search(self, query):
        response = requests.get(
            self.api_url,
            params={
                "action": "query",
                "format": "json",
                "formatversion": "2",
                "generator": "search",
                "gsrsearch": query,
                "gsrnamespace": "0",
                "gsrlimit": "8",
                "prop": "extracts|info",
                "exintro": "1",
                "explaintext": "1",
                "inprop": "url",
                "redirects": "1",
                "maxage": "86400",
                "smaxage": "86400",
            },
            headers=self.headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("error"):
            return []
        query_data = payload.get("query")
        if not isinstance(query_data, dict):
            return []
        pages = query_data.get("pages", [])
        return pages if isinstance(pages, list) else []

    def _best_article(self, pages, search_name):
        search_words = set(search_name.casefold().replace(",", " ").split())
        candidates = []

        for page in pages:
            if not isinstance(page, dict):
                continue
            title = str(page.get("title", "")).strip()
            extract = " ".join(str(page.get("extract", "")).split())
            url = page.get("fullurl")
            if not title or not extract or not url:
                continue

            relevance_text = f"{title} {extract}".casefold()
            title_words = set(title.casefold().replace(",", " ").split())
            if not any(word in relevance_text for word in search_words):
                continue
            if not any(term in relevance_text for term in self.RELEVANCE_TERMS):
                continue

            score = 4 * len(search_words & title_words)
            score += sum(term in relevance_text for term in self.RELEVANCE_TERMS)
            if title.casefold() == search_name.casefold():
                score += 10
            # Earlier MediaWiki search results win otherwise-equal scores.
            search_index = page.get("index", 999)
            candidates.append((score, -search_index, page, title, extract, url))

        if not candidates:
            return None

        _, _, page, title, summary, url = max(
            candidates, key=lambda item: item[:2]
        )
        if len(summary) > 900:
            summary = summary[:900].rsplit(" ", 1)[0] + "…"

        return {
            "title": title,
            "summary": summary,
            "url": url,
            "page_id": page.get("pageid"),
            "revision_id": page.get("lastrevid"),
            "revision_timestamp": None,
            "license_name": "CC BY-SA 4.0",
            "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
        }
