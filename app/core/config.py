"""Define and validate runtime configuration for the application.

Load environment-based settings for the FastAPI app, database, OpenAI access,
job-search integration, and object storage.
Validate provider-specific settings before the application tries to use the live job API.
"""

from __future__ import annotations

from pathlib import Path
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal, Self

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Store validated application settings loaded from environment variables.

     Provide a typed configuration object that other modules use to read runtime values such as
     provider selection, API credentials, HTTP client configuration, and timeout settings.
     """
    app_name: str = "AI Job Match & Application Copilot"
    debug: bool = True

    session_secret_key: str
    session_cookie_name: str = "ai_job_copilot_session"
    session_max_age_seconds: int = Field(default=60 * 60 * 8, gt=0)
    session_same_site: Literal["lax", "strict", "none"] = "lax"
    session_https_only: bool = False
    session_idle_timeout_seconds: int = Field(default=60 * 30, gt=0)
    session_absolute_timeout_seconds: int = Field(default=60 * 60 * 8, gt=0)

    database_url: str
    openai_api_key: str

    job_search_provider: Literal["fixture", "live"] = "fixture"
    job_api_base_url: str | None = None
    job_api_key: str | None = None
    job_api_host: str | None = None
    job_api_timeout_connect: float = Field(default=5.0, gt=0)
    job_api_timeout_read: float = Field(default=30.0, gt=0)
    job_api_timeout_write: float = Field(default=10.0, gt=0)
    job_api_timeout_pool: float = Field(default=5.0, gt=0)

    storage_endpoint_url: str | None = None
    storage_access_key: str = "minioadmin"
    storage_secret_key: str = "minioadmin"
    storage_bucket_name: str = "ai-job-copilot-documents"
    storage_region: str = "us-east-1"
    max_upload_size_bytes: int = Field(default=10 * 1024 * 1024, gt=0)

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @model_validator(mode="after")
    def validate_job_api_settings(self) -> Self:
        """Validate settings required by the live job-search provider.

        Ensure that the live provider configuration is complete before the
        dependency layer creates the HTTP client for the external job API.

        :return: The validated settings instance.
        :raises ValueError: If a required live-provider setting is missing.
        """
        if self.job_search_provider == "live":
            if not self.job_api_base_url:
                raise ValueError("JOB_API_BASE_URL must be set when JOB_SEARCH_PROVIDER='live'.")
            if not self.job_api_key:
                raise ValueError("JOB_API_KEY must be set when JOB_SEARCH_PROVIDER='live'.")
            if not self.job_api_host:
                raise ValueError("JOB_API_HOST must be set when JOB_SEARCH_PROVIDER='live'.")
        return self


settings = Settings()


