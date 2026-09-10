"""
Application configuration loaded from environment variables.
All secrets MUST be provided via environment; never hardcoded.
"""
from typing import List
from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Financial Document Intelligence Platform"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # Database
    DATABASE_URL: str = "postgresql://docai:docai@localhost:5432/docai"

    # AI Provider
    AI_PROVIDER: str = "openai"          # openai | anthropic | google
    AI_MODEL: str = "gpt-4o"
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    AI_TIMEOUT_SECONDS: int = 120
    AI_MAX_RETRIES: int = 2

    # File upload limits
    MAX_FILE_SIZE_MB: int = 20
    MAX_PAGES: int = 3

    # Financial validation tolerances
    VALIDATION_ABS_TOLERANCE: float = 1.0     # absolute units
    VALIDATION_REL_TOLERANCE: float = 0.005   # 0.5 %

    # CORS
    CORS_ORIGINS: str = "*"

    @field_validator("CORS_ORIGINS")
    @classmethod
    def parse_cors(cls, v: str) -> List[str]:
        if v == "*":
            return ["*"]
        return [origin.strip() for origin in v.split(",")]

    model_config = {"env_file": (".env", "backend/.env"), "extra": "ignore"}


settings = Settings()
