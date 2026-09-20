"""FastAPI 应用入口。"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app

from app.api.v1 import api_router
from app.config import settings
from app.core.exceptions import register_exception_handlers

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期。"""
    logger.info("app.starting", env=settings.app_env, version=settings.app_version)

    # 启动：初始化日志、Langfuse、数据库连接池等
    yield

    # 关闭：清理资源
    logger.info("app.shutdown")


def create_app() -> FastAPI:
    """工厂函数创建 FastAPI 实例。"""
    app = FastAPI(
        title="Finance AI Agent API",
        version=settings.app_version,
        description="企业财务 AI Agent 平台后端服务",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 异常处理
    register_exception_handlers(app)

    # Prometheus 指标端点
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    # 健康检查
    @app.get("/health", tags=["meta"])
    async def health():
        return {
            "status": "ok",
            "env": settings.app_env,
            "version": settings.app_version,
        }

    # 注册路由
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    return app


app = create_app()