from datetime import date, datetime
import json
from pathlib import Path

from flask import render_template, request


def load_surf_spots(data_dir):
    spots_path = Path(data_dir) / "surf_spots.json"
    with spots_path.open(encoding="utf-8") as spots_file:
        return json.load(spots_file)


def register_routes(app):
    surf_spots = load_surf_spots(app.config["DATA_DIR"])

    @app.route("/")
    def index():
        spot_key = request.args.get("spot", "huntington")
        spot = surf_spots.get(spot_key, surf_spots["huntington"])

        requested_date = request.args.get("date", date.today().isoformat())
        try:
            forecast_date = datetime.strptime(requested_date, "%Y-%m-%d").date()
        except ValueError:
            forecast_date = date.today()

        return render_template(
            "index.html",
            spots=surf_spots,
            selected_spot=spot_key if spot_key in surf_spots else "huntington",
            spot=spot,
            forecast_date=forecast_date,
            today=date.today().isoformat(),
        )

    @app.route("/about")
    def about():
        return render_template("about.html")
