
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# [context:config] : Database URL. Defaults to a local SQLite file if not provided.
# In production, set DATABASE_URL env var to: postgresql://user:pass@host/db
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./storage.db")

# [decision:logic] : SQLite needs "check_same_thread=False" to work with FastAPI's async nature.
connect_args = {}
if "sqlite" in SQLALCHEMY_DATABASE_URL:
    connect_args = {"check_same_thread": False}

# [structure:engine] : The main entry point to the database.
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args=connect_args
)

# [structure:session] : Factory to create new database sessions for each request.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# [structure:orm] : Base class for all DB models (User, Project, etc.)
Base = declarative_base()

# [+] [INFO] Dependency to be used in FastAPI routes to get a DB session.
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
