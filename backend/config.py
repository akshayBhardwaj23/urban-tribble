from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./data/app.db"
    UPLOAD_DIR: str = "./data/uploads"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"
    MAX_FILE_SIZE_MB: int = 20
    # Per authenticated user (X-User-Email). In-memory; use proxy limits for multi-worker.
    UPLOAD_RATE_BURST_PER_MINUTE: int = 5
    UPLOAD_RATE_MAX_PER_HOUR: int = 30
    ALLOWED_EXTENSIONS: List[str] = [".xlsx", ".xls", ".csv", ".tsv"]
    # Comma-separated. Browsers reject Access-Control-Allow-Origin: * when credentials are used.
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
