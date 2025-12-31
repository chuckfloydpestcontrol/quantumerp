"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = "postgresql+asyncpg://quantum:quantum_secret_2024@localhost:5432/quantum_hub"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # AI Provider
    anthropic_api_key: str = ""

    # Application
    secret_key: str = "quantum_hub_secret_key_2024"
    debug: bool = True

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Feature Flags
    enable_parallel_quoting: bool = True
    enable_dynamic_entry: bool = True

    @property
    def sync_database_url(self) -> str:
        """Get synchronous database URL for Alembic."""
        return self.database_url.replace("+asyncpg", "")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
