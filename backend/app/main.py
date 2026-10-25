"""FastAPI 应用入口。"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.v1 import api_router
from app.config import settings
from app.core.exceptions import register_exception_handlers

logger = structlog.get_logger()


def _metrics_authorized(request: Request) -> bool:
    """校验 /metrics 访问：Bearer token 或本机回环。"""
    if not settings.metrics_protected:
        return True
    token = (settings.metrics_token or "").strip()
    auth = request.headers.get("authorization") or ""
    if token and auth == f"Bearer {token}":
        return True
    # 无配置 token 时仅允许本机 scrape（Prometheus 同机 / 边车）
    client_host = request.client.host if request.client else ""
    if client_host in {"127.0.0.1", "::1", "localhost"}:
        return True
    if token:
        return False
    # 生产且无 token、非本机：拒绝，避免裸奔
    return settings.app_env != "production"


class MetricsProtectMiddleware(BaseHTTPMiddleware):
    """拦截 /metrics，未授权返回 401。"""

    async def dispatch(self, request: Request, call_next):
        if request.url.path.rstrip("/") == "/metrics":
            if not _metrics_authorized(request):
                return JSONResponse(
                    status_code=401,
                    content={"code": "UNAUTHORIZED", "message": "metrics 需要鉴权"},
                )
        return await call_next(request)


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
    # 生产环境关闭 Swagger / ReDoc，降低攻击面
    is_prod = settings.app_env == "production"
    app = FastAPI(
        title="Finance AI Agent API",
        version=settings.app_version,
        description="企业财务 AI Agent 平台后端服务",
        docs_url=None if is_prod else "/docs",
        redoc_url=None if is_prod else "/redoc",
        openapi_url=None if is_prod else f"{settings.api_v1_prefix}/openapi.json",
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
    app.add_middleware(MetricsProtectMiddleware)

    # 异常处理
    register_exception_handlers(app)

    @app.get("/metrics", include_in_schema=False)
    async def metrics(request: Request):
        """Prometheus 指标（由 MetricsProtectMiddleware 鉴权）。"""
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

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