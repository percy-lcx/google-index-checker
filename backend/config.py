import os
from dotenv import load_dotenv

load_dotenv()

GSC_PROPERTY_URL = os.getenv("GSC_PROPERTY_URL", "https://www.tmgm.com/")
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "./credentials.json")
TOKEN_PATH = os.getenv("TOKEN_PATH", "./token.json")
API_DELAY_MS = int(os.getenv("API_DELAY_MS", "200"))
CONCURRENCY_LIMIT = int(os.getenv("CONCURRENCY_LIMIT", "5"))
DAILY_QUOTA_LIMIT = int(os.getenv("DAILY_QUOTA_LIMIT", "2000"))
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "90"))
DATABASE_PATH = os.getenv("DATABASE_PATH", "./indexation.db")
