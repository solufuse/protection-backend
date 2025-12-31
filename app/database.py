
import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# --- CONFIGURATION PERSISTANTE ---
# Au lieu de mettre la DB dans le dossier courant (qui est effacé à chaque deploy),
# on la met dans /app/storage qui est un Volume Docker persistant.

PERSISTENT_DIR = "/app/storage"

# Création du dossier si nécessaire (pour éviter crash au démarrage)
if not os.path.exists(PERSISTENT_DIR):
    os.makedirs(PERSISTENT_DIR, exist_ok=True)

# Le fichier s'appelle maintenant protection.db et est stocké en sécurité
SQLALCHEMY_DATABASE_URL = f"sqlite:///{PERSISTENT_DIR}/protection.db"

# connect_args={"check_same_thread": False} est nécessaire pour SQLite
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency standard pour récupérer la DB dans les routes
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
