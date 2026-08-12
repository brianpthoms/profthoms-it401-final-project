import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev")
    DATA_DIR = os.path.join(BASE_DIR, "data")

    # External API keys / service config
    APIFREAKS_API_KEY = os.environ.get("APIFREAKS_API_KEY")
    APIFREAKS_BASE_URL = os.environ.get(
        "APIFREAKS_BASE_URL", "https://api.apifreaks.com/v1.0"
    )
    NOMINATIM_BASE_URL = os.environ.get(
        "NOMINATIM_BASE_URL", "https://nominatim.openstreetmap.org"
    )
    NOMINATIM_USER_AGENT = os.environ.get(
        "NOMINATIM_USER_AGENT", "Breakline/1.0 (educational surf forecast app)"
    )
    WIKIPEDIA_API_URL = os.environ.get(
        "WIKIPEDIA_API_URL", "https://en.wikipedia.org/w/api.php"
    )
    AI_SERVICE_API_KEY = os.environ.get("AI_SERVICE_API_KEY")


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
