from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000
    ALLOWED_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://vguser:vgpass@localhost:5432/visionguard"

    # Redis
    REDIS_URL: str = "redis://:redispass@localhost:6379/0"

    # RabbitMQ
    RABBITMQ_URL: str = "amqp://vguser:vgpass@localhost:5672/visionguard"

    # MinIO
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET_SNAPSHOTS: str = "snapshots"
    MINIO_BUCKET_LOGOS: str = "logos"
    MINIO_BUCKET_REPORTS: str = "reports"
    MINIO_BUCKET_MODELS: str = "models"

    # JWT
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7


settings = Settings()
