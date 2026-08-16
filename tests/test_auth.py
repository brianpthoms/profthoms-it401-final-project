import pytest
from flask import redirect

from app import create_app
from models import db
from models.user import User


@pytest.fixture
def auth_app():
    app = create_app(
        "development",
        {
            "TESTING": True,
            "DATABASE_ENABLED": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "SQLALCHEMY_ENGINE_OPTIONS": {},
            "GOOGLE_CLIENT_ID": "test-client-id",
            "GOOGLE_CLIENT_SECRET": "test-client-secret",
            "GOOGLE_OAUTH_ENABLED": True,
        },
    )
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def test_google_login_redirects_to_provider(auth_app, monkeypatch):
    google = auth_app.extensions["google_oauth_client"]
    captured = {}

    def fake_authorize_redirect(redirect_uri, **kwargs):
        captured["redirect_uri"] = redirect_uri
        captured.update(kwargs)
        return redirect("https://accounts.google.com/o/oauth2/v2/auth")

    monkeypatch.setattr(google, "authorize_redirect", fake_authorize_redirect)
    response = auth_app.test_client().get("/login/google")

    assert response.status_code == 302
    assert response.location.startswith("https://accounts.google.com/")
    assert captured["redirect_uri"] == "http://localhost/auth/google/callback"
    assert captured["prompt"] == "select_account"


def test_google_callback_creates_user_and_profile(auth_app, monkeypatch):
    google = auth_app.extensions["google_oauth_client"]
    monkeypatch.setattr(
        google,
        "authorize_access_token",
        lambda: {
            "userinfo": {
                "sub": "google-user-123",
                "email": "surfer@example.com",
                "email_verified": True,
                "name": "Sample Surfer",
                "picture": "https://example.com/avatar.png",
            }
        },
    )
    client = auth_app.test_client()
    response = client.get("/auth/google/callback", follow_redirects=True)

    assert response.status_code == 200
    assert b"Sample Surfer" in response.data
    assert b"No forecast requests yet" in response.data
    with auth_app.app_context():
        user = db.session.execute(db.select(User)).scalar_one()
        assert user.google_sub == "google-user-123"
        assert user.email == "surfer@example.com"


def test_unverified_google_email_is_rejected(auth_app, monkeypatch):
    google = auth_app.extensions["google_oauth_client"]
    monkeypatch.setattr(
        google,
        "authorize_access_token",
        lambda: {
            "userinfo": {
                "sub": "google-user-123",
                "email": "surfer@example.com",
                "email_verified": False,
            }
        },
    )
    response = auth_app.test_client().get(
        "/auth/google/callback", follow_redirects=True
    )

    assert b"Google sign-in could not be completed" in response.data
    with auth_app.app_context():
        assert db.session.execute(db.select(User)).scalar_one_or_none() is None


def test_profile_requires_login(auth_app):
    response = auth_app.test_client().get("/profile")
    assert response.status_code == 302
    assert "/login/google" in response.location


def test_logout_clears_session(auth_app):
    with auth_app.app_context():
        user = User(
            google_sub="google-user-123",
            email="surfer@example.com",
            display_name="Sample Surfer",
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    client = auth_app.test_client()
    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True

    response = client.post("/logout", follow_redirects=True)
    assert response.status_code == 200
    assert b"You have been signed out" in response.data
    assert b"Sign in with Google" in response.data
