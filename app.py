import os

import click
from flask import Flask
from sqlalchemy import inspect, text

from config import config
from models import db
from routes.auth import register_auth_routes
from routes.main import register_routes


def upgrade_database_schema():
    """Apply small, idempotent schema upgrades not handled by create_all()."""
    inspector = inspect(db.engine)
    table_names = inspector.get_table_names()
    if "surf_forecasts" not in table_names:
        return

    columns = {column["name"] for column in inspector.get_columns("surf_forecasts")}
    unique_names = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("surf_forecasts")
    }
    needs_hourly_upgrade = (
        "forecast_hour" not in columns
        or "uq_surf_forecasts_beach_date" in unique_names
        or "uq_surf_forecasts_beach_date_hour" not in unique_names
    )
    if not needs_hourly_upgrade:
        return
    if db.engine.dialect.name != "mysql":
        raise RuntimeError("The hourly schema upgrade currently supports MySQL only.")

    with db.engine.begin() as connection:
        if "forecast_hour" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE surf_forecasts "
                    "ADD COLUMN forecast_hour SMALLINT NOT NULL DEFAULT 0 "
                    "AFTER forecast_date"
                )
            )
        if "uq_surf_forecasts_beach_date" in unique_names:
            connection.execute(
                text(
                    "ALTER TABLE surf_forecasts "
                    "DROP INDEX uq_surf_forecasts_beach_date"
                )
            )
        if "uq_surf_forecasts_beach_date_hour" not in unique_names:
            connection.execute(
                text(
                    "ALTER TABLE surf_forecasts ADD CONSTRAINT "
                    "uq_surf_forecasts_beach_date_hour "
                    "UNIQUE (beach_id, forecast_date, forecast_hour)"
                )
            )


def create_app(config_name=None, test_config=None):
    config_name = config_name or os.environ.get("FLASK_ENV", "default")

    app = Flask(__name__)
    app.config.from_object(config[config_name])
    if test_config:
        app.config.update(test_config)

    db.init_app(app)

    register_auth_routes(app)
    register_routes(app)

    @app.cli.command("init-db")
    def init_db_command():
        """Create the configured database tables."""
        if not app.config["DATABASE_ENABLED"]:
            raise click.UsageError(
                "Database credentials are not configured. Add DB_NAME, "
                "DB_USERNAME, and DB_PASSWORD to .env first."
            )
        db.create_all()
        upgrade_database_schema()
        click.echo("Initialized the Breakline database.")

    @app.cli.command("upgrade-db")
    def upgrade_db_command():
        """Upgrade existing Breakline tables to the current schema."""
        if not app.config["DATABASE_ENABLED"]:
            raise click.UsageError(
                "Database credentials are not configured. Add DB_NAME, "
                "DB_USERNAME, and DB_PASSWORD to .env first."
            )
        db.create_all()
        upgrade_database_schema()
        click.echo("Upgraded the Breakline database schema.")

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=app.config.get("DEBUG", False))
