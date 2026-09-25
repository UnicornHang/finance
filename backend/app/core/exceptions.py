"""统一异常处理。"""

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class BusinessError(Exception):
    """业务异常基类。"""

    code: str = "BUSINESS_ERROR"
    http_status: int = status.HTTP_400_BAD_REQUEST

    def __init__(self, message: str, code: str | None = None, http_status: int | None = None):
        self.message = message
        if code:
            self.code = code
        if http_status:
            self.http_status = http_status
        super().__init__(message)


class UnauthorizedError(BusinessError):
    code = "UNAUTHORIZED"
    http_status = status.HTTP_401_UNAUTHORIZED


class ForbiddenError(BusinessError):
    code = "FORBIDDEN"
    http_status = status.HTTP_403_FORBIDDEN


class NotFoundError(BusinessError):
    code = "NOT_FOUND"
    http_status = status.HTTP_404_NOT_FOUND


class ConflictError(BusinessError):
    code = "CONFLICT"
    http_status = status.HTTP_409_CONFLICT


class RateLimitError(BusinessError):
    code = "RATE_LIMIT"
    http_status = status.HTTP_429_TOO_MANY_REQUESTS


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理。"""

    @app.exception_handler(BusinessError)
    async def business_error_handler(request: Request, exc: BusinessError):
        return JSONResponse(
            status_code=exc.http_status,
            content={
                "code": exc.code,
                "message": exc.message,
                "path": str(request.url.path),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "code": "VALIDATION_ERROR",
                "message": "请求参数校验失败",
                # exc.errors() 里可能含 bytes（如 multipart 上传体），必须过 jsonable_encoder
                "errors": jsonable_encoder(exc.errors()),
                "path": str(request.url.path),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # 生产环境不暴露内部错误
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "code": "INTERNAL_ERROR",
                "message": "服务器内部错误",
                "path": str(request.url.path),
            },
        )