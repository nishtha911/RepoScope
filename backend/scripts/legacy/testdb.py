import sys
from pathlib import Path

# Add the 'backend' directory to sys.path
backend_dir = Path(__file__).resolve().parents[2]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from sqlalchemy import text
from reposcope.db.session import engine

with engine.connect() as connection: #import the engine directly and obtain a connection to db
    version = connection.execute( #.execute sends this query to db and gets result object
        text("SHOW server_version") # basically "SHOW server_version;" in SQL terms
    ).scalar_one() #return one value not the entire result row

    print("Database connected")
    print("PostgreSQL:", version)