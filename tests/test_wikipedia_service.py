from unittest.mock import Mock, patch

from services.wikipedia_service import WikipediaService


def test_find_spot_summary_uses_mediawiki_api_and_returns_plain_text():
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "query": {
            "pages": [
                {
                    "title": "County Line Beach",
                    "extract": "County Line Beach is a beach and popular surf spot.",
                    "fullurl": "https://en.wikipedia.org/wiki/County_Line_Beach",
                }
            ]
        }
    }
    service = WikipediaService(base_url="https://wikipedia.test/w/api.php")

    with patch("services.wikipedia_service.requests.get", return_value=response) as get:
        result = service.find_spot_summary("County Line Beach", "California")

    assert result["title"] == "County Line Beach"
    assert result["extract"] == "County Line Beach is a beach and popular surf spot."
    assert result["url"] == "https://en.wikipedia.org/wiki/County_Line_Beach"
    assert get.call_args.kwargs["params"]["titles"] == "County Line Beach"
    assert get.call_args.kwargs["params"]["redirects"] == 1
    assert get.call_args.kwargs["params"]["explaintext"] == 1
    assert get.call_args.kwargs["params"]["exsentences"] == 3
