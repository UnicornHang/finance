"""应用配置 - 通过环境变量加载，pydantic-settings 校验。"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- 通用 ----
    app_name: str = "finance-ai-agent"
    app_env: Literal["development", "staging", "production"] = "development"
    app_version: str = "0.1.0"
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"

    # ---- 数据库 ----
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "finance"
    postgres_password: str = "finance"
    postgres_db: str = "finance"
    database_url: str | None = None

    # ---- Redis ----
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_url: str | None = None

    # ---- MinIO ----
    minio_root_user: str = "minio_admin"
    minio_root_password: str = "minio_pass"
    minio_host: str = "localhost"
    minio_port: int = 9000
    minio_bucket_invoice: str = "invoices"
    minio_bucket_contract: str = "contracts"
    minio_bucket_kb: str = "knowledge-base"

    # ---- JWT / 安全 ----
    jwt_secret: str = "change-me-to-a-32-char-secret"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7
    encryption_key: str = "change-me-base64-key"

    # ---- LLM ----
    llm_chitchat_model: str = "gpt-4o-mini"
    llm_chitchat_api_key: str = ""
    llm_chitchat_base_url: str = "https://api.openai.com/v1"

    llm_policy_model: str = "gpt-4o"
    llm_policy_api_key: str = ""
    llm_policy_base_url: str = "https://api.openai.com/v1"

    llm_ocr_model: str = "gpt-4o"
    llm_ocr_api_key: str = ""
    llm_ocr_base_url: str = "https://api.openai.com/v1"

    llm_contract_model: str = "gpt-4o"
    llm_contract_api_key: str = ""
    llm_contract_base_url: str = "https://api.openai.com/v1"

    # ---- OCR ----
    ocr_provider: Literal["tencent", "aliyun", "paddle"] = "tencent"
    tencent_ocr_secret_id: str = ""
    tencent_ocr_secret_key: str = ""
    tencent_ocr_region: str = "ap-guangzhou"

    # ---- Embedding ----
    embedding_model: str = "text-embedding-3-small"
    embedding_api_key: str = ""
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_dimension: int = 1536

    # ---- Celery ----
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    celery_worker_concurrency: int = 2

    # ---- Langfuse（可选） ----
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # ---- 限流 ----
    rate_limit_per_user: str = "100/minute"
    rate_limit_per_tenant: str = "10000/hour"
    rate_limit_per_ip: str = "1000/minute"

    # ---- CORS ----
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    def model_post_init(self, __context) -> None:
        """自动拼接未显式设置的 URL。"""
        if not self.database_url:
            self.database_url = (
                f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
                f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
            )
        if not self.redis_url:
            self.redis_url = f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache
def get_settings() -> Settings:
    """单例配置。"""
    return Settings()


settings = get_settings()