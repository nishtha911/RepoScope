from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from repolens.config import DATABASE_URL


# Engine: manages database connectivity and connection pooling.
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

# Factory: creates individual database sessions.
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
)