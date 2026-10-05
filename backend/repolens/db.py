from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from repolens.config import DATABASE_URL
#we are using sqlalchemy because it allows us to work with database records as python objects.
#sqlalchhemy has an ORM (object relational manager) this can translate python commands directly to SQL queries
#example:
"""repo = Repository(
    full_name="nishtha911/RepoScope",
    remote_url="https://github.com/nishtha911/RepoScope.git",
)

session.add(repo)
session.commit()
"""
#this will be converted into db commands by sqlalchemy

engine = create_engine(DATABASE_URL, pool_pre_ping=True) #engine is basically a interface between the actual DB and python code
#engines can be used directly to interact with db or can be used in a session

SessionLocal = sessionmaker(bind=engine, autoflush=False)
#sessionLocal is bascially a "factory" to create sessions. we bind the engine to it to access the DB, autoflush false means do not automatically commit changes to DB after every change
#sessions are used to commit a group of changes at once using python objects. Sessions use the ORM layer to interact with DB. engine interacts with DB directly

#alembic is used to run migrations and manage different DB versions
#its not compulsary to use alembic but isme ek sath sab hojata hai