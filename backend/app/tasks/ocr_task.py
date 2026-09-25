"""OCR Celery 任务。

异步流程：chat_stream 上传 MinIO → 触发 process_invoice_ocr.delay(...)
  → 下载 → 调用 OCR Provider → LLM 归一 → 写 Invoice(status='pending_review')

设计要点：
- Celery 任务本身是同步函数；内嵌 asyncio.run() 跑 async DB/IO
- max_retries=3 应对瞬时网络错误；去重冲突（ConflictError）不重试
- 不依赖 Redis pubsub：结果通过 Invoice 表 + 前端轮询 /preview/by-hash 拉取
"""

import asyncio
import logging
from io import BytesIO
from uuid import UUID

from celery.exceptions import MaxRetriesExceededError

from app.config import settings
from app.core.database import async_session_factory
from app.core.exceptions import ConflictError
from app.services.invoice_service import invoice_service
from app.services.invoice_vision_service import invoice_vision_service
from app.services.storage_service import storage_service
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _parse_s3_url(s3_url: str) -> tuple[str, str]:
    """s3://bucket/key → (bucket, key)"""
    if not s3_url.startswith("s3://"):
        raise ValueError(f"invalid s3 url: {s3_url}")
    rest = s3_url[len("s3://"):]
    bucket, _, key = rest.partition("/")
    if not bucket or not key:
        raise ValueError(f"invalid s3 url: {s3_url}")
    return bucket, key


def _download_from_minio(bucket: str, key: str) -> bytes:
    """从 MinIO 下载文件到 bytes。"""
    obj = storage_service.client.get_object(bucket_name=bucket, object_name=key)
    try:
        return obj.read()
    finally:
        obj.close()
        obj.release_conn()


async def _llm_normalize(ocr_result, user_message: str | None) -> dict:
    """可选：用 LLM 归一化 OCR 字段（把 OCR 输出映射到标准 Invoice 字段）。

    当 OCR Provider 直接产出 InvoiceOCRResult 完整字段时，可跳过此步骤。
    """
    # 简化：直接返回 OCR 字段，让 invoice_service.create_pending 接收
    return {
        "invoice_title": ocr_result.invoice_title,
        "company": ocr_result.company,
        "tax_id": ocr_result.tax_id,
        "invoice_code": ocr_result.invoice_code,
        "invoice_number": ocr_result.invoice_number,
        "invoice_date": ocr_result.invoice_date,
        "amount_excl_tax": ocr_result.amount_excl_tax,
        "tax_amount": ocr_result.tax_amount,
        "amount_incl_tax": ocr_result.amount_incl_tax,
        "invoice_type": ocr_result.invoice_type,
        "seller": ocr_result.seller,
        "buyer": ocr_result.buyer,
        "confidence": ocr_result.confidence,
    }


async def _run_ocr_pipeline(
    *,
    tenant_id: UUID,
    user_id: UUID,
    file_url: str,
    file_hash: str,
    user_message: str | None,
) -> None:
    """实际执行：下载 → 通用大模型识别 → 归一 → 写 Invoice。"""
    bucket, obj_key = _parse_s3_url(file_url)
    file_bytes = _download_from_minio(bucket, obj_key)
    logger.info("recognize task: downloaded %d bytes from s3://%s/%s", len(file_bytes), bucket, obj_key)

    async with async_session_factory() as db:
        ocr_result, _source = await invoice_vision_service.recognize(
            file_bytes,
            filename=obj_key.rsplit("/", 1)[-1],
            db=db,
            tenant_id=str(tenant_id),
        )
    logger.info(
        "LLM result: invoice_number=%s amount=%s confidence=%s",
        ocr_result.invoice_number, ocr_result.amount_incl_tax, ocr_result.confidence,
    )

    fields = await _llm_normalize(ocr_result, user_message)

    async with async_session_factory() as db:
        await invoice_service.create_pending(
            db,
            tenant_id=tenant_id,
            user_id=user_id,
            file_url=file_url,
            file_hash=file_hash,
            **fields,
        )
        await db.commit()
        logger.info("Invoice saved (pending_review) for tenant=%s hash=%s", tenant_id, file_hash)


@celery_app.task(
    bind=True,
    name="app.tasks.ocr_task.process_invoice_ocr",
    max_retries=3,
    default_retry_delay=10,
)
def process_invoice_ocr(
    self,
    *,
    tenant_id: str,
    user_id: str,
    file_url: str,
    file_hash: str,
    user_message: str | None = None,
):
    """Celery 入口：异步 OCR 任务。"""
    try:
        asyncio.run(_run_ocr_pipeline(
            tenant_id=UUID(tenant_id),
            user_id=UUID(user_id),
            file_url=file_url,
            file_hash=file_hash,
            user_message=user_message,
        ))
    except ConflictError as exc:
        # 重复发票：不重试，前端轮询会拿到已存在的记录
        logger.info("OCR task: duplicate invoice (%s) — skipping", exc.code)
        return {"status": "duplicate", "code": exc.code}
    except Exception as exc:
        logger.exception("OCR task failed (attempt %s)", self.request.retries)
        # 业务异常 → 重试；超过 max_retries 后让 Celery 标记 FAILED
        try:
            raise self.retry(exc=exc, countdown=10 * (self.request.retries + 1))
        except MaxRetriesExceededError:
            logger.error("OCR task: max retries exceeded, giving up: %s", exc)
            return {"status": "failed", "error": str(exc)}

    return {"status": "ok"}