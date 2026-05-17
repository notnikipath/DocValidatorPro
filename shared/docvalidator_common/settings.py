from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "docvalidator-service"
    service_port: int = 8500
    environment: str = "dev"

    postgres_dsn: str = Field(default="postgresql+psycopg://docvalidator:docvalidator@postgres:5432/docvalidator")
    clickhouse_dsn: str = Field(default="clickhouse://default:@clickhouse:9000/default")
    minio_endpoint: str = Field(default="http://minio:9000")
    minio_access_key: str = Field(default="docvalidator")
    minio_secret_key: str = Field(default="docvalidator123")

    rabbitmq_url: str = Field(default="amqp://guest:guest@rabbitmq:5672/")
    kafka_bootstrap_servers: str = Field(default="redpanda:9092")
    redis_url: str = Field(default="redis://redis:6379/0")

    jwt_secret: str = Field(default="docvalidator-dev-secret")
    encryption_key: str = Field(default="docvalidator-dev-encryption-key")
    token_exp_minutes: int = 240

    data_ingestion_service_url: str = Field(default="http://data-ingestion-service:8501")
    validation_service_url: str = Field(default="http://validation-service:8502")
    comparison_service_url: str = Field(default="http://comparison-service:8503")
    analytics_service_url: str = Field(default="http://analytics-service:8504")
    quality_service_url: str = Field(default="http://quality-service:8505")
    export_service_url: str = Field(default="http://export-service:8506")
    storage_service_url: str = Field(default="http://storage-service:8507")
    notification_service_url: str = Field(default="http://notification-service:8508")
    api_gateway_url: str = Field(default="http://api-gateway:8500")

    target_validation_accuracy: float = 0.99
    target_error_recall: float = 0.95
    target_doc_processing_seconds: float = 5.0
    target_docs_per_hour: int = 1000

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
