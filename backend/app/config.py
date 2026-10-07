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
    minio_bucket_exports: str = "exports"

    # ---- 异步导出 ----
    export_retention_days: int = 7
    export_max_inflight_per_user: int = 3

    # ---- JWT / 安全 ----
    jwt_secret: str = "change-me-to-a-32-char-secret"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7
    encryption_key: str = "change-me-base64-key"
    # 连续密码错误达到该次数后锁定账号
    login_max_failed_attempts: int = 5
    # 登录锁定时长（分钟）
    login_lockout_minutes: int = 30

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

    # ---- 公开财税检索（最新政策/税率，非企业知识库）----
    web_search_enabled: bool = False
    web_search_provider: Literal["bocha", "tavily"] = "bocha"
    web_search_api_key: str = ""
    web_search_base_url: str = ""
    web_search_timeout: int = 15
    web_search_max_results: int = 16
    # 检索命中后抓取前 N 条官方页面正文；0 = 只用不摘要
    web_search_fetch_pages: int = 2
    web_search_fetch_max_chars: int = 4000

    # ---- Embedding ----
    embedding_model: str = "text-embedding-3-small"
    embedding_api_key: str = ""
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_dimension: int = 1536

    # ---- RAG 混合检索 / Rerank ----
    rag_hybrid_enabled: bool = True
    # 每路召回条数 = top_k * multiplier，融合后再截断
    rag_retrieve_multiplier: int = 4
    rag_rrf_k: int = 60
    rag_rerank_enabled: bool = True
    rag_rerank_candidates: int = 20
    rerank_provider: Literal["dashscope", "cohere", "jina", "openai_compatible"] = (
        "dashscope"
    )
    rerank_model: str = "qwen3.7-text-rerank"
    rerank_api_key: str = ""
    rerank_base_url: str = ""
    rerank_timeout: int = 15
    rerank_max_doc_chars: int = 4000

    # ---- Milvus（企业级向量库，知识库主路径）----
    milvus_enabled: bool = True
    milvus_host: str = "127.0.0.1"
    milvus_port: int = 19530
    milvus_user: str = ""
    milvus_password: str = ""
    milvus_collection: str = "finance_kb_chunks"
    milvus_index_type: str = "IVF_FLAT"
    milvus_metric_type: str = "COSINE"
    milvus_nlist: int = 1024
    milvus_nprobe: int = 16
    # 是否同时把向量写入 Postgres（仅作 Milvus 故障降级备份，默认关闭）
    kb_store_pg_embedding: bool = False

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