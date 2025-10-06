from fastapi import FastAPI
from .models import Base
from sqlalchemy import create_engine
from . import auth
from . import upload
from . import analyze

import os

app = FastAPI(title="Academic Assignment Helper")
app.include_router(auth.router)
app.include_router(upload.router)
app.include_router(analyze.router)

# Database connection string
DB_USER = os.getenv("POSTGRES_USER", "student")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "secure_password")
DB_HOST = os.getenv("DB_HOST", "postgres")
DB_NAME = os.getenv("POSTGRES_DB", "academic_helper")
DB_PORT = os.getenv("DB_PORT", "5432")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(DATABASE_URL)

# Create tables automatically when container starts
Base.metadata.create_all(engine)

@app.get("/")
def home():
    return {"message": "Academic Assignment Helper backend is running!"}
