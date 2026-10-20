from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)

# Import model classes after creating db so SQLAlchemy discovers their tables.
from models.beach import Beach  # noqa: E402, F401
from models.surf_forecast import SurfForecast  # noqa: E402, F401
from models.wikipedia_spot_info import WikipediaSpotInfo  # noqa: E402, F401
from models.forecast_intelligence import ForecastIntelligence  # noqa: E402, F401
from models.surf_spot import SurfSpot, SurfSpotAlias  # noqa: E402, F401
from models.user import User  # noqa: E402, F401
from models.forecast_request import ForecastRequest  # noqa: E402, F401
from models.forecast_feedback import ForecastFeedback  # noqa: E402, F401
from models.history_search import (  # noqa: E402, F401
    HistorySearch,
    HistorySearchInteraction,
)
