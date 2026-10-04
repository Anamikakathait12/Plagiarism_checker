import os
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(BASE_DIR, ".env"))

INSTANCE_DIR = os.path.join(BASE_DIR, "instance")


class Config:
    # Secrets come from the environment (.env locally). Never hardcode them.
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

    # Runtime data lives in instance/ (git-ignored): database + student uploads
    DATABASE = os.getenv("DATABASE_PATH", os.path.join(INSTANCE_DIR, "database.db"))
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", os.path.join(INSTANCE_DIR, "uploads"))
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB per upload
