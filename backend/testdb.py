from sqlalchemy import text

from repolens.db import engine

with engine.connect() as connection: #import the engine directly and obtain a connection to db
    version = connection.execute( #.execute sends this query to db and gets result object
        text("SHOW server_version") # basically "SHOW server_version;" in SQL terms
    ).scalar_one() #return one value not the entire result row

    print("Database connected")
    print("PostgreSQL:", version)