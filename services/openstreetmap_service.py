import re
import threading
import time

import requests


class OpenStreetMapError(RuntimeError):
    """Raised when a surf spot cannot be resolved through OpenStreetMap."""


class OpenStreetMapService:
    """Policy-conscious client for user-triggered Nominatim place searches."""

    _cache = {}
    _request_lock = threading.Lock()
    _last_request_at = 0.0

    def __init__(
        self,
        base_url="https://nominatim.openstreetmap.org",
        user_agent="Breakline/1.0 (educational surf forecast app)",
        timeout=10,
    ):
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.timeout = timeout

    @staticmethod
    def _normalize(value):
        return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()

    @classmethod
    def _without_beach_suffix(cls, value):
        return re.sub(r"\s+beach$", "", cls._normalize(value)).strip()

    def _search(self, query):
        cache_key = (self.base_url, self._normalize(query))
        if cache_key in self._cache:
            return self._cache[cache_key]

        # The public Nominatim service permits at most one request per second
        # across the entire application, not one request per user.
        with self._request_lock:
            if cache_key in self._cache:
                return self._cache[cache_key]
            wait_for = 1.0 - (time.monotonic() - self._last_request_at)
            if wait_for > 0:
                time.sleep(wait_for)
            try:
                response = requests.get(
                    f"{self.base_url}/search",
                    headers={
                        "User-Agent": self.user_agent,
                        "Accept-Language": "en",
                    },
                    params={
                        "q": query,
                        "format": "jsonv2",
                        "addressdetails": 1,
                        "namedetails": 1,
                        "extratags": 1,
                        "limit": 10,
                    },
                    timeout=self.timeout,
                )
                response.raise_for_status()
                results = response.json()
            except (requests.RequestException, ValueError) as exc:
                raise OpenStreetMapError("The surf spot lookup failed") from exc
            finally:
                type(self)._last_request_at = time.monotonic()

            if not isinstance(results, list):
                raise OpenStreetMapError("OpenStreetMap returned an invalid response")
            self._cache[cache_key] = results
            return results

    def find_surf_spot(self, spot_name):
        normalized_spot = self._normalize(spot_name)
        if not normalized_spot:
            raise OpenStreetMapError("A surf spot name is required")

        candidates = self._search(f"{spot_name} Beach")
        match = self._best_match(candidates, normalized_spot)
        if match is None:
            candidates = self._search(spot_name)
            match = self._best_match(candidates, normalized_spot, require_surf_type=True)
        if match is None:
            raise OpenStreetMapError("No matching surf spot was found")

        try:
            latitude = float(match["lat"])
            longitude = float(match["lon"])
        except (KeyError, TypeError, ValueError) as exc:
            raise OpenStreetMapError("The matching place has no coordinates") from exc

        address = match.get("address") or {}
        region_parts = []
        for key in ("city", "town", "village", "county", "state", "country"):
            part = address.get(key)
            if part and part not in region_parts:
                region_parts.append(part)

        return {
            "name": match.get("name") or spot_name,
            "latitude": latitude,
            "longitude": longitude,
            "region": ", ".join(region_parts),
            "osm_url": (
                f"https://www.openstreetmap.org/{match.get('osm_type')}/"
                f"{match.get('osm_id')}"
            ),
        }

    def _best_match(self, candidates, normalized_spot, require_surf_type=False):
        ranked = []
        for candidate in candidates:
            name = candidate.get("name") or (candidate.get("namedetails") or {}).get(
                "name", ""
            )
            normalized_name = self._normalize(name)
            base_name = self._without_beach_suffix(name)
            category = candidate.get("category")
            place_type = candidate.get("type")
            extra_tags = candidate.get("extratags") or {}
            is_surf_type = (
                extra_tags.get("sport") == "surfing"
                or (category == "natural" and place_type in {"beach", "reef", "bay"})
            )

            if normalized_name != normalized_spot and base_name != normalized_spot:
                continue
            if require_surf_type and not is_surf_type:
                continue

            score = 0
            if normalized_name == normalized_spot:
                score += 5
            if base_name == normalized_spot:
                score += 4
            if extra_tags.get("sport") == "surfing":
                score += 5
            if category == "natural" and place_type == "beach":
                score += 3
            score += float(candidate.get("importance") or 0)
            ranked.append((score, candidate))

        return max(ranked, key=lambda item: item[0])[1] if ranked else None
