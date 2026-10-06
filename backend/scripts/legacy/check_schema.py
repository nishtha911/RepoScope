import sys
from pathlib import Path

# Add the 'backend' directory to sys.path
backend_dir = Path(__file__).resolve().parents[2]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
    
from sqlalchemy import inspect, text
from reposcope.db import engine

with engine.connect() as connection:
    tables = inspect(connection).get_table_names()
    print("Existing tables:", tables)

    if "alembic_version" in tables:
        revisions = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalars().all()

        print("Recorded migrations:", revisions)