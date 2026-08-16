from services.wikipedia_service import WikipediaService


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(response=self)

    def json(self):
        return self.payload


SEARCH_RESPONSE = {
    "query": {
        "pages": [
            {
                "pageid": 1,
                "index": 1,
                "title": "Bodysurfing",
                "extract": "Bodysurfing is the art and sport of riding a wave without a board.",
                "fullurl": "https://en.wikipedia.org/wiki/Bodysurfing",
            },
            {
                "pageid": 2,
                "lastrevid": 98765,
                "index": 2,
                "title": "The Wedge (surfing)",
                "extract": (
                    "The Wedge is a renowned surf break at the southeastern tip of "
                    "the Balboa Peninsula in Newport Beach, California. It is known "
                    "for powerful waves created by the nearby rock jetty."
                ),
                "fullurl": "https://en.wikipedia.org/wiki/The_Wedge_(surfing)",
            },
        ]
    }
}


def test_fetches_best_matching_article_from_api(monkeypatch):
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append({"url": url, "params": params, "headers": headers})
        return FakeResponse(SEARCH_RESPONSE)

    monkeypatch.setattr("services.wikipedia_service.requests.get", fake_get)
    result = WikipediaService().get_spot_info(surf_break="The Wedge")

    assert result["title"] == "The Wedge (surfing)"
    assert "renowned surf break" in result["summary"]
    assert result["url"] == "https://en.wikipedia.org/wiki/The_Wedge_(surfing)"
    assert result["page_id"] == 2
    assert result["revision_id"] == 98765
    assert result["revision_timestamp"] is None
    assert result["license_name"] == "CC BY-SA 4.0"
    assert len(calls) == 1
    assert calls[0]["url"] == "https://en.wikipedia.org/w/api.php"
    assert calls[0]["params"]["generator"] == "search"
    assert calls[0]["params"]["prop"] == "extracts|info"
    assert calls[0]["params"]["maxage"] == "86400"
    assert calls[0]["headers"]["Accept"] == "application/json"


def test_returns_none_when_no_relevant_article(monkeypatch):
    monkeypatch.setattr(
        "services.wikipedia_service.requests.get",
        lambda *args, **kwargs: FakeResponse({"query": {"pages": []}}),
    )

    assert WikipediaService().get_spot_info(city="Nowhere") is None


def test_returns_none_for_api_error_payload(monkeypatch):
    monkeypatch.setattr(
        "services.wikipedia_service.requests.get",
        lambda *args, **kwargs: FakeResponse(
            {"error": {"code": "badrequest", "info": "Invalid request"}}
        ),
    )

    assert WikipediaService().get_spot_info(city="Nowhere") is None


def test_returns_none_for_malformed_api_response(monkeypatch):
    monkeypatch.setattr(
        "services.wikipedia_service.requests.get",
        lambda *args, **kwargs: FakeResponse({"query": {"pages": {}}}),
    )

    assert WikipediaService().get_spot_info(city="Nowhere") is None


def test_truncates_long_api_extract(monkeypatch):
    payload = {
        "query": {
            "pages": [
                {
                    "index": 1,
                    "title": "Long Beach",
                    "extract": "Long Beach is a coastal city with ocean waves. " * 30,
                    "fullurl": "https://en.wikipedia.org/wiki/Long_Beach,_California",
                }
            ]
        }
    }
    monkeypatch.setattr(
        "services.wikipedia_service.requests.get",
        lambda *args, **kwargs: FakeResponse(payload),
    )

    result = WikipediaService().get_spot_info(city="Long Beach")
    assert len(result["summary"]) <= 901
    assert result["summary"].endswith("…")
