import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load environment variables
# load_dotenv(dotenv_path="api/DB/.env")
load_dotenv(dotenv_path="./api/.env")
DATABASE_URL = os.getenv("LOCAL_DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("LOCAL_DATABASE_URL is not set in the environment variables or .env file.")

engine = create_engine(DATABASE_URL)
#, connect_args={"check_same_thread": False}
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
