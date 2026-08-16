from datetime import time
from urllib.parse import urlparse

from authlib.integrations.flask_client import OAuth
from authlib.integrations.base_client.errors import OAuthError
from flask import abort, flash, redirect, render_template, request, session, url_for
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from models import db
from models.forecast_request import ForecastRequest
from models.user import User, utc_now
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
        history = db.session.scalars(
            select(ForecastRequest)
            .where(ForecastRequest.user_id == current_user.id)
            .order_by(ForecastRequest.requested_at.desc())
            .limit(100)
        ).all()
        return render_template("profile.html", history=history)

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
