import json
from pathlib import Path

import pytest

from app import create_app


@pytest.fixture
def client():
    app = create_app("development")
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_index(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Breakline" in response.data


def test_forecast_selection(client):
    response = client.get("/?spot=trestles&date=2026-08-09")
    assert response.status_code == 200
    assert b"Lower Trestles" in response.data
    assert b"4\xe2\x80\x936 ft" in response.data


def test_about(client):
    response = client.get("/about")
    assert response.status_code == 200
    assert b"The ocean is complex" in response.data


def test_surf_spots_data_file():
    spots_path = Path(__file__).parent.parent / "data" / "surf_spots.json"
    with spots_path.open(encoding="utf-8") as spots_file:
        spots = json.load(spots_file)

    assert spots["huntington"]["name"] == "Huntington Beach"
