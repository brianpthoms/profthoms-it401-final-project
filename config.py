import os
from urllib.parse import quote_plus

from dotenv import load_dotenv


load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def database_url():
    configured_url = os.environ.get("DATABASE_URL")
    if configured_url:
        return configured_url

    username = quote_plus(os.environ.get("DB_USERNAME", "breakline_user"))
    password = quote_plus(os.environ.get("DB_PASSWORD", "replace-with-db-password"))
    host = os.environ.get("DB_HOST", "brian.cikeys.com")
    port = os.environ.get("DB_PORT", "3306")
    database = quote_plus(os.environ.get("DB_NAME", "breakline"))
    return f"mysql+pymysql://{username}:{password}@{host}:{port}/{database}"


def database_is_configured():
    return bool(
        os.environ.get("DATABASE_URL")
        or (
            os.environ.get("DB_NAME")
            and os.environ.get("DB_USERNAME")
            and os.environ.get("DB_PASSWORD")
        )
    )


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev")
    DATA_DIR = os.path.join(BASE_DIR, "data")

    # External API keys / service config
    API_KEY = os.environ.get("API_KEY")
    AI_SERVICE_API_KEY = os.environ.get("AI_SERVICE_API_KEY")
    APIFREAKS_API_KEY = os.environ.get("APIFREAKS_API_KEY")
    APIFREAKS_BASE_URL = os.environ.get(
        "APIFREAKS_BASE_URL", "https://api.apifreaks.com/v1.0"
    )
    WIKIPEDIA_BASE_URL = os.environ.get(
        "WIKIPEDIA_BASE_URL", "https://en.wikipedia.org"
    )
    WIKIPEDIA_USER_AGENT = os.environ.get(
        "WIKIPEDIA_USER_AGENT",
        "Breakline/1.1 (https://brian.cikeys.com/; educational surf forecast)",
    )
    WIKIPEDIA_CACHE_DAYS = int(os.environ.get("WIKIPEDIA_CACHE_DAYS", "30"))
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
    GOOGLE_OAUTH_ENABLED = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SQLALCHEMY_DATABASE_URI = database_url()
    DATABASE_ENABLED = database_is_configured()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
