from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from passlib.context import CryptContext
import jwt, os
from datetime import datetime, timedelta
from .models import Student
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ─────────────────────────────────────────────
# Database connection
DB_USER = os.getenv("POSTGRES_USER", "student")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "secure_password")
DB_HOST = os.getenv("DB_HOST", "postgres")
DB_NAME = os.getenv("POSTGRES_DB", "academic_helper")
DB_PORT = os.getenv("DB_PORT", "5432")

SQLALCHEMY_DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
# ─────────────────────────────────────────────

router = APIRouter(prefix="/auth", tags=["Authentication"])
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
JWT_SECRET = os.getenv("JWT_SECRET_KEY", "replace_me")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# ─────────────── Schemas ────────────────
class RegisterSchema(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None

class LoginSchema(BaseModel):
    email: EmailStr
    password: str

# ─────────────── Helpers ────────────────
def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)

# ─────────────── Routes ────────────────
@router.post("/register")
def register_user(payload: RegisterSchema, db: Session = Depends(get_db)):
    existing = db.query(Student).filter(Student.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed_pw = pwd_ctx.hash(payload.password)
    user = Student(email=payload.email, password_hash=hashed_pw, full_name=payload.full_name)
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"message": "Registration successful", "user_id": user.id}

@router.post("/login")
def login_user(payload: LoginSchema, db: Session = Depends(get_db)):
    user = db.query(Student).filter(Student.email == payload.email).first()
    if not user or not pwd_ctx.verify(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token({"sub": user.email})
    return {"access_token": token, "token_type": "bearer"}
