from datetime import date, time
from math import isfinite
from urllib.parse import urlparse

from authlib.integrations.flask_client import OAuth
from authlib.integrations.base_client.errors import OAuthError
from flask import abort, flash, redirect, render_template, request, session, url_for
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from models import db
from models.forecast_request import ForecastRequest
from models.forecast_feedback import ForecastFeedback
from models.user import User, utc_now
from services.request_history_repository import (
    TIME_PERIODS,
    calculate_distance_miles,
    count_forecast_requests,
    search_forecast_requests,
)
from services.search_analytics_repository import (
    get_owned_history_search,
    history_search_matches,
    record_history_interaction,
    record_history_search,
)
from services.wikipedia_repository import get_wikipedia_info


login_manager = LoginManager()
login_manager.login_view = "google_login"
login_manager.login_message = "Sign in with Google to view your profile."


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


def _safe_local_path(value):
    if not value:
        return None
    parsed = urlparse(value)
    return value if not parsed.scheme and not parsed.netloc and value.startswith("/") else None


def _parse_filter_date(value):
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Enter valid forecast dates.") from exc


def _positive_integer(value):
    try:
        parsed = int(value)
        return parsed if parsed > 0 else None
    except (TypeError, ValueError):
        return None


def register_auth_routes(app):
    login_manager.init_app(app)
    oauth = OAuth(app)
    google = oauth.register(
        name="google",
        client_id=app.config.get("GOOGLE_CLIENT_ID"),
        client_secret=app.config.get("GOOGLE_CLIENT_SECRET"),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    app.extensions["google_oauth_client"] = google

    @app.route("/login/google")
    def google_login():
        if current_user.is_authenticated:
            return redirect(url_for("profile"))
        if not app.config["GOOGLE_OAUTH_ENABLED"]:
            flash("Google sign-in is not configured yet.", "error")
            return redirect(url_for("index"))

        next_path = _safe_local_path(request.args.get("next"))
        if next_path:
            session["post_login_next"] = next_path
        redirect_uri = url_for("google_callback", _external=True)
        return google.authorize_redirect(redirect_uri, prompt="select_account")

    @app.route("/auth/google/callback")
    def google_callback():
        if not app.config["GOOGLE_OAUTH_ENABLED"]:
            flash("Google sign-in is not configured yet.", "error")
            return redirect(url_for("index"))

        try:
            token = google.authorize_access_token()
            userinfo = token.get("userinfo") or {}
            google_sub = userinfo.get("sub")
            email = userinfo.get("email")
            if not google_sub or not email or userinfo.get("email_verified") is not True:
                raise ValueError("Google did not return a verified identity.")

            user = db.session.scalar(
                select(User).where(User.google_sub == google_sub)
            )
            if user is None:
                user = User(
                    google_sub=google_sub,
                    email=email,
                    display_name=userinfo.get("name") or email,
                )
                db.session.add(user)

            user.email = email
            user.display_name = userinfo.get("name") or user.display_name
            user.avatar_url = userinfo.get("picture")
            user.last_login_at = utc_now()
            db.session.commit()
            login_user(user)
        except (OAuthError, SQLAlchemyError, ValueError, KeyError):
            db.session.rollback()
            app.logger.warning("Google sign-in failed.", exc_info=True)
            flash("Google sign-in could not be completed. Please try again.", "error")
            return redirect(url_for("index"))

        destination = _safe_local_path(session.pop("post_login_next", None))
        return redirect(destination or url_for("profile"))

    @app.post("/logout")
    @login_required
    def logout():
        logout_user()
        session.pop("post_login_next", None)
        flash("You have been signed out.", "success")
        return redirect(url_for("index"))

    @app.route("/profile")
    @login_required
    def profile():
        history_total_count = count_forecast_requests(current_user.id)
        filter_names = (
            "spot",
            "date_from",
            "date_to",
            "time_period",
            "latitude",
            "longitude",
            "radius",
        )
        search_submitted = any(
            name in request.args for name in (*filter_names, "sort")
        )
        page = _positive_integer(request.args.get("page")) or 1
        filters = {
            "spot": request.args.get("spot", "").strip(),
            "date_from": request.args.get("date_from", "").strip(),
            "date_to": request.args.get("date_to", "").strip(),
            "time_period": request.args.get("time_period", "").strip().lower(),
            "latitude": request.args.get("latitude", "").strip(),
            "longitude": request.args.get("longitude", "").strip(),
            "radius": request.args.get("radius", "").strip(),
            "location_label": request.args.get("location_label", "").strip(),
        }
        if not filters["latitude"] or not filters["longitude"]:
            filters["location_label"] = ""
        sort_order = request.args.get("sort", "recent").strip().lower()
        filter_error = None
        field_errors = {}
        parsed_date_from = None
        parsed_date_to = None
        parsed_latitude = None
        parsed_longitude = None
        parsed_radius = None

        has_filter_values = any(filters[name] for name in filter_names)
        if search_submitted and not has_filter_values and sort_order == "recent":
            filter_error = "Enter at least one search filter."

        if len(filters["spot"]) > 150:
            field_errors["spot"] = "Use 150 characters or fewer."
        if filters["time_period"] and filters["time_period"] not in TIME_PERIODS:
            field_errors["time_period"] = "Choose a listed time of day."
        if sort_order not in ("recent", "spot_asc"):
            field_errors["sort"] = "Choose a listed sort order."
        if len(filters["location_label"]) > 250:
            field_errors["location"] = "Current location name is invalid."
        location_values = (
            filters["latitude"],
            filters["longitude"],
            filters["radius"],
        )
        if any(location_values):
            if not filters["latitude"] or not filters["longitude"]:
                field_errors["location"] = "Choose Use my location first."
            else:
                try:
                    parsed_latitude = float(filters["latitude"])
                    parsed_longitude = float(filters["longitude"])
                    if (
                        not isfinite(parsed_latitude)
                        or not isfinite(parsed_longitude)
                        or not -90 <= parsed_latitude <= 90
                        or not -180 <= parsed_longitude <= 180
                    ):
                        raise ValueError
                except ValueError:
                    field_errors["location"] = "Current location coordinates are invalid."
            if not filters["radius"]:
                field_errors["radius"] = "Choose a search radius."
            else:
                try:
                    parsed_radius = float(filters["radius"])
                    if not isfinite(parsed_radius) or not 1 <= parsed_radius <= 100:
                        raise ValueError
                except ValueError:
                    field_errors["radius"] = "Enter a radius from 1 to 100 miles."
        if filters["date_from"]:
            try:
                parsed_date_from = _parse_filter_date(filters["date_from"])
            except ValueError:
                field_errors["date_from"] = "Enter a valid start date."
        if filters["date_to"]:
            try:
                parsed_date_to = _parse_filter_date(filters["date_to"])
            except ValueError:
                field_errors["date_to"] = "Enter a valid end date."
        if (
            parsed_date_from
            and parsed_date_to
            and parsed_date_from > parsed_date_to
        ):
            field_errors["date_to"] = "End date must be on or after start date."

        if field_errors:
            filter_error = "Review the highlighted search fields."

        active_filters = {key: value for key, value in filters.items() if value}
        if sort_order != "recent":
            active_filters["sort"] = sort_order

        search_event = None
        requested_search_id = _positive_integer(request.args.get("search_id"))
        if filter_error is None and requested_search_id is not None:
            try:
                candidate = get_owned_history_search(
                    requested_search_id, current_user.id
                )
                if candidate and history_search_matches(
                    candidate,
                    spot_query=filters["spot"] or None,
                    date_from=parsed_date_from,
                    date_to=parsed_date_to,
                    time_period=filters["time_period"] or None,
                    radius_miles=parsed_radius,
                    sort_order=sort_order,
                ):
                    search_event = candidate
                    active_filters["search_id"] = candidate.id
            except SQLAlchemyError:
                db.session.rollback()
                app.logger.warning("Search analytics could not be read.", exc_info=True)

        history = []
        pagination = None
        search_recall_percent = None
        if filter_error is None:
            pagination = search_forecast_requests(
                current_user.id,
                spot=filters["spot"] or None,
                date_from=parsed_date_from,
                date_to=parsed_date_to,
                time_period=filters["time_period"] or None,
                latitude=parsed_latitude,
                longitude=parsed_longitude,
                radius_miles=parsed_radius,
                sort_order=sort_order,
                page=page,
            )
            if pagination.total and page > pagination.pages:
                return redirect(
                    url_for(
                        "profile",
                        page=pagination.pages,
                        _anchor="history-results",
                        **active_filters,
                    )
                )
            history = pagination.items
            if search_submitted and history_total_count:
                search_recall_percent = (
                    pagination.total / history_total_count * 100
                )

            try:
                if search_event is not None and "page" in request.args:
                    record_history_interaction(
                        current_user.id,
                        "page_view",
                        search_id=search_event.id,
                        page_number=page,
                    )
                elif search_event is None and search_submitted:
                    search_event = record_history_search(
                        current_user.id,
                        spot_query=filters["spot"] or None,
                        date_from=parsed_date_from,
                        date_to=parsed_date_to,
                        time_period=filters["time_period"] or None,
                        radius_miles=parsed_radius,
                        sort_order=sort_order,
                        result_count=pagination.total,
                    )
                    active_filters["search_id"] = search_event.id
            except SQLAlchemyError:
                db.session.rollback()
                app.logger.warning("Search analytics could not be saved.", exc_info=True)

        pagination_links = []
        history_distances = {}
        if (
            parsed_latitude is not None
            and parsed_longitude is not None
            and parsed_radius is not None
        ):
            for history_item in history:
                beach = history_item.beach
                if beach is not None:
                    history_distances[history_item.id] = calculate_distance_miles(
                        parsed_latitude,
                        parsed_longitude,
                        beach.latitude,
                        beach.longitude,
                    )
        if pagination and pagination.pages > 1:
            pagination_links = [
                (
                    page_number,
                    url_for(
                        "profile",
                        page=page_number,
                        _anchor="history-results",
                        **active_filters,
                    )
                    if page_number
                    else None,
                )
                for page_number in pagination.iter_pages(
                    left_edge=1, left_current=1, right_current=2, right_edge=1
                )
            ]

        return render_template(
            "profile.html",
            history=history,
            history_distances=history_distances,
            show_distances=bool(history_distances),
            search_event_id=search_event.id if search_event else None,
            pagination=pagination,
            pagination_links=pagination_links,
            active_filters=active_filters,
            filters=filters,
            sort_order=sort_order,
            filter_error=filter_error,
            field_errors=field_errors,
            has_filters=has_filter_values,
            search_submitted=search_submitted,
            history_total_count=history_total_count,
            search_recall_percent=search_recall_percent,
        )

    @app.route("/profile/history/<int:request_id>")
    @login_required
    def history_forecast(request_id):
        history_item = db.session.scalar(
            select(ForecastRequest).where(
                ForecastRequest.id == request_id,
                ForecastRequest.user_id == current_user.id,
            )
        )
        if history_item is None or history_item.forecast is None:
            abort(404)

        try:
            search_event = get_owned_history_search(
                _positive_integer(request.args.get("search_id")), current_user.id
            )
            record_history_interaction(
                current_user.id,
                "result_view",
                search_id=search_event.id if search_event else None,
                forecast_request_id=history_item.id,
                page_number=_positive_integer(request.args.get("page")),
                result_position=_positive_integer(request.args.get("position")),
            )
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.warning("Result interaction could not be saved.", exc_info=True)

        saved = history_item.forecast
        beach = history_item.beach or saved.beach
        raw_forecast = {
            "location": {
                "city": beach.city,
                "state_prov": beach.state_prov,
                "country_name": beach.country_name,
                "latitude": beach.latitude,
                "longitude": beach.longitude,
            },
            "conditions": {
                "wave_height_max": saved.wave_height_max,
                "wave_direction_dominant": saved.wave_direction_dominant,
                "wave_period_max": saved.wave_period_max,
                "swell_wave_height_max": saved.swell_wave_height_max,
                "swell_wave_direction_dominant": saved.swell_wave_direction_dominant,
                "swell_wave_period_max": saved.swell_wave_period_max,
                "wind_wave_height_max": saved.wind_wave_height_max,
            },
        }
        # Imported here to avoid coupling authentication setup to the main routes.
        from routes.main import present_forecast

        forecast = present_forecast(raw_forecast)
        display_name = history_item.surf_break_name or beach.name
        if history_item.surf_break_name:
            forecast["area_name"] = forecast["place_name"]
            forecast["surf_break"] = True
        forecast["place_name"] = display_name

        return render_template(
            "history_forecast.html",
            history_item=history_item,
            forecast=forecast,
            forecast_date=saved.forecast_date,
            forecast_time=time(hour=saved.forecast_hour),
            wikipedia_info=get_wikipedia_info(beach.id),
        )

    @app.post("/profile/history/<int:request_id>/feedback")
    @login_required
    def forecast_feedback(request_id):
        history_item = db.session.scalar(
            select(ForecastRequest).where(
                ForecastRequest.id == request_id,
                ForecastRequest.user_id == current_user.id,
            )
        )
        if history_item is None:
            abort(404)

        raw_rating = request.form.get("rating", "").strip()
        comment = request.form.get("comment", "").strip()
        try:
            rating = int(raw_rating)
        except ValueError:
            rating = 0

        if rating not in range(1, 6):
            flash("Choose a rating from 1 to 5.", "error")
            reopen_feedback = True
        elif len(comment) > 1000:
            flash("Feedback must be 1,000 characters or fewer.", "error")
            reopen_feedback = True
        else:
            reopen_feedback = False
            feedback = history_item.feedback
            if feedback is None:
                feedback = ForecastFeedback(forecast_request=history_item)
                db.session.add(feedback)
            feedback.rating = rating
            feedback.comment = comment or None
            try:
                db.session.commit()
                flash("Thanks—your forecast feedback was saved.", "success")
            except SQLAlchemyError:
                db.session.rollback()
                app.logger.warning("Forecast feedback could not be saved.", exc_info=True)
                flash("Your feedback could not be saved. Please try again.", "error")
                reopen_feedback = True

        destination = url_for(
            "history_forecast",
            request_id=history_item.id,
            **({"feedback": "open"} if reopen_feedback else {}),
        )
        return redirect(destination + "#forecast-feedback")
