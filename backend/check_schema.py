from sqlalchemy import inspect, text

from repolens.db import engine

with engine.connect() as connection:
    tables = inspect(connection).get_table_names()
    print("Existing tables:", tables)

    if "alembic_version" in tables:
        revisions = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalars().all()

        print("Recorded migrations:", revisions)