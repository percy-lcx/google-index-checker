import os
from dotenv import load_dotenv

load_dotenv()

GSC_PROPERTY_URL = os.getenv("GSC_PROPERTY_URL", "https://www.tmgm.com/")
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "./credentials.json")
TOKEN_PATH = os.getenv("TOKEN_PATH", "./token.json")
CONCURRENCY_LIMIT = int(os.getenv("CONCURRENCY_LIMIT", "10"))
MAX_REQUESTS_PER_MINUTE = int(os.getenv("MAX_REQUESTS_PER_MINUTE", "600"))
DAILY_QUOTA_LIMIT = int(os.getenv("DAILY_QUOTA_LIMIT", "2000"))
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "90"))
DATABASE_PATH = os.getenv("DATABASE_PATH", "./indexation.db")
PROFILES_CONFIG_PATH = os.getenv("PROFILES_CONFIG_PATH", "./profiles.json")
