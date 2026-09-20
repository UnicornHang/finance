"""合同审查异步任务。"""

from app.tasks.celery_app import celery_app


@celery_app.task(bind=True, max_retries=3)
def contract_review_task(self, session_id: str, file_url: str, tenant_id: str, user_id: str):
    """异步合同审查。"""
    import asyncio
    from app.services.contract_service import review_contract

    async def _run():
        # TODO: 解析 PDF → 审查 → 写回 session → WebSocket 通知
        return await review_contract("", tenant_id, db=None)

    try:
        return asyncio.run(_run())
    except Exception as exc:
        self.retry(exc=exc, countdown=2 ** self.request.retries)