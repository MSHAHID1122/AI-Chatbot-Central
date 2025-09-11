from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from config import DATABASE_URL, DB_POOL_SIZE, DB_MAX_OVERFLOW

# Use the already-processed configuration from config.py
engine = create_engine(
    DATABASE_URL,
    pool_size=DB_POOL_SIZE,  # Use the integer value directly from config
    max_overflow=DB_MAX_OVERFLOW,  # Use the integer value directly from config
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)