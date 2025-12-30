
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import engine, Base
from .routers import files, admin, projects, storage_admin # Added storage_admin

# Create DB Tables
Base.metadata.create_all(bind=engine)

app = FastAPI()

# CORS
origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(files.router, prefix="/session", tags=["Session"])
app.include_router(admin.router, prefix="/admin", tags=["Global Admin"])
app.include_router(storage_admin.router, prefix="/admin/storage", tags=["Storage Admin"]) # New
app.include_router(projects.router, prefix="/projects", tags=["Projects"])

@app.get("/")
def read_root():
    return {"status": "Solufuse Backend Running"}
