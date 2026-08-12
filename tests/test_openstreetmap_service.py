from unittest.mock import Mock, patch

from services.openstreetmap_service import OpenStreetMapService


def test_find_surf_spot_resolves_named_beach_and_caches_result():
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = [
        {
            "lat": "34.0523255",
            "lon": "-118.9615825",
            "category": "natural",
            "type": "beach",
            "name": "County Line Beach",
            "importance": 0.26,
            "osm_type": "way",
            "osm_id": 264378737,
            "address": {
                "city": "Old Malibu",
                "county": "Ventura County",
                "state": "California",
                "country": "United States",
            },
        }
    ]
    service = OpenStreetMapService(base_url="https://nominatim.test")

    with (
        patch("services.openstreetmap_service.requests.get", return_value=response) as get,
        patch("services.openstreetmap_service.time.sleep"),
    ):
        result = service.find_surf_spot("County Line")
        cached_result = service.find_surf_spot("County Line")

    assert result == cached_result
    assert result["name"] == "County Line Beach"
    assert result["latitude"] == 34.0523255
    assert result["longitude"] == -118.9615825
    assert result["region"] == (
        "Old Malibu, Ventura County, California, United States"
    )
    assert result["osm_url"] == "https://www.openstreetmap.org/way/264378737"
    get.assert_called_once()
    assert get.call_args.kwargs["params"]["q"] == "County Line Beach"
    assert get.call_args.kwargs["headers"]["User-Agent"].startswith("Breakline/")
