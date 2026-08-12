import re

import requests


class WikipediaError(RuntimeError):
    """Raised when Wikipedia content cannot be retrieved."""


class WikipediaService:
    """Retrieve short, plain-text surf spot summaries through MediaWiki."""

    _cache = {}

    def __init__(
        self,
        base_url="https://en.wikipedia.org/w/api.php",
        user_agent="Breakline/1.0 (educational surf forecast app)",
        timeout=8,
    ):
        self.base_url = base_url
        self.user_agent = user_agent
        self.timeout = timeout

    @staticmethod
    def _normalize(value):
        return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()

    def find_spot_summary(self, spot_name, region=""):
        cache_key = (
            "v2",
            self.base_url,
            self._normalize(spot_name),
            self._normalize(region),
        )
        if cache_key in self._cache:
            return self._cache[cache_key]

        pages = self._request_pages({"titles": spot_name, "redirects": 1})
        exact_page = next(
            (
                page
                for page in pages
                if not page.get("missing") and page.get("extract", "").strip()
            ),
            None,
        )

        if exact_page is not None:
            summary = self._format_page(exact_page)
            self._cache[cache_key] = summary
            return summary

        # Keep fallback terms concise. Full address strings can push the exact
        # surf spot article below unrelated regional results.
        pages = self._request_pages(
            {
                "generator": "search",
                "gsrsearch": f'intitle:"{spot_name}" surfing',
                "gsrnamespace": 0,
                "gsrlimit": 10,
            }
        )
        normalized_spot = self._normalize(spot_name)
        ranked = []
        for page in pages:
            title = page.get("title", "")
            extract = page.get("extract", "").strip()
            normalized_title = self._normalize(title)
            if not extract or normalized_spot not in normalized_title:
                continue
            score = 2 if normalized_title == normalized_spot else 1
            if "surf" in extract.casefold() or "beach" in normalized_title:
                score += 2
            ranked.append((score, page))

        if not ranked:
            self._cache[cache_key] = None
            return None

        summary = self._format_page(max(ranked, key=lambda item: item[0])[1])
        self._cache[cache_key] = summary
        return summary

    def _request_pages(self, lookup_params):
        params = {
            "action": "query",
            "prop": "extracts|info",
            "exintro": 1,
            "explaintext": 1,
            "exsentences": 3,
            "inprop": "url",
            "format": "json",
            "formatversion": 2,
        }
        params.update(lookup_params)
        try:
            response = requests.get(
                self.base_url,
                headers={"User-Agent": self.user_agent},
                params=params,
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise WikipediaError("The Wikipedia lookup failed") from exc

        return payload.get("query", {}).get("pages", [])

    @staticmethod
    def _format_page(page):
        return {
            "title": page["title"],
            "extract": page["extract"].strip(),
            "url": page.get("fullurl")
            or f"https://en.wikipedia.org/wiki/{page['title'].replace(' ', '_')}",
        }
