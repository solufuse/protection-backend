
import uvicorn
from app.main import app

# Point d'entrée principal
if __name__ == "__main__":
    # [CONFIG] Lancement sur le Port 80 (Standard HTTP)
    # Note: Sur une machine locale Linux, le port 80 nécessite souvent 'sudo'.
    # Dans Docker/Dokploy, c'est géré automatiquement.
    uvicorn.run(app, host="0.0.0.0", port=80)
