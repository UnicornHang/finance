"""OCR 异步任务。"""

from app.tasks.celery_app import celery_app
from app.services.ocr_service import get_ocr_service


@celery_app.task(bind=True, max_retries=3)
def ocr_task(self, session_id: str, file_url: str, user_id: str):
    """异步 OCR 识别，结果回写 session。"""
    import asyncio

    async def _run():
        ocr = get_ocr_service()
        # TODO: 下载文件 → OCR → 写回 session → WebSocket 通知
        result = await ocr.recognize_invoice(b"")
        return result

    try:
        return asyncio.run(_run())
    except Exception as exc:
        self.retry(exc=exc, countdown=2 ** self.request.retries)