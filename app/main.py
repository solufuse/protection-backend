
import asyncio
import os
import time
import shutil
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Routers
from app.routers import loadflow, files
# (Add projects router here later if needed)

app = FastAPI(title="Protection Backend", version="2.0.0")

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ROUTERS ---
app.include_router(loadflow.router)
app.include_router(files.router)

# --- GARBAGE COLLECTOR (CLEANER) ---
BASE_STORAGE = "/app/storage"
CLEANUP_INTERVAL_SECONDS = 3600  # Run every 1 hour
MAX_AGE_SECONDS = 86400          # 24 Hours

async def run_garbage_collector():
    """
    Background task that scans for folders marked with '.guest'
    and deletes files older than 24h.
    """
    while True:
        try:
            print("[CLEANER] Starting cleanup scan...")
            if os.path.exists(BASE_STORAGE):
                for uid in os.listdir(BASE_STORAGE):
                    user_path = os.path.join(BASE_STORAGE, uid)
                    marker_path = os.path.join(user_path, ".guest")
                    
                    # Only clean if it IS a guest folder
                    if os.path.isdir(user_path) and os.path.exists(marker_path):
                        now = time.time()
                        # Check folder age (or file ages)
                        # Strategy: If the folder itself is old, nuke it.
                        folder_mtime = os.path.getmtime(user_path)
                        
                        if (now - folder_mtime) > MAX_AGE_SECONDS:
                            print(f"[CLEANER] Deleting expired guest folder: {uid}")
                            shutil.rmtree(user_path)
                        else:
                            # Granular check: delete old files inside, keep folder
                            for f in os.listdir(user_path):
                                f_path = os.path.join(user_path, f)
                                if os.path.isfile(f_path) and (now - os.path.getmtime(f_path)) > MAX_AGE_SECONDS:
                                    os.remove(f_path)

            print("[CLEANER] Scan complete. Sleeping...")
        except Exception as e:
            print(f"[CLEANER] Error: {e}")
            
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)

@app.on_event("startup")
async def startup_event():
    # Start the cleaner loop in background
    asyncio.create_task(run_garbage_collector())

@app.get("/")
def home():
    return {"status": "Backend running", "service": "Protection API"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
