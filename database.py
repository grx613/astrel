from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# База — это просто файл astrel.db рядом с проектом
SQLALCHEMY_DATABASE_URL = "sqlite:///./astrel.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}  # нужно для SQLite + FastAPI
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
