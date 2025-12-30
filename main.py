
from app.main import app

# Ce bloc permet de lancer le serveur localement avec 'python main.py'
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
