"""附件去重：上传复用已有对象，定时清孤儿和历史重复副本。"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import ChatFile, Contract, Invoice
from app.services.storage_service import parse_s3_url, storage_service

logger = logging.getLogger(__name__)

# 对话附件对象：{tenant}/files/... ；知识库正文不走这条前缀
_CHAT_OBJECT_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/files/",
    re.IGNORECASE,
)


def canonical_object_key(tenant_id: UUID, file_hash: str, ext: str) -> str:
    """同一租户同一内容固定对象名，避免重复上传。"""
    suffix = ext if ext.startswith(".") else f".{ext}" if ext else ""
    return f"{tenant_id}/files/by-hash/{file_hash}{suffix}"


async def find_existing_url(
    db: AsyncSession,
    tenant_id: UUID,
    file_hash: str,
) -> str | None:
    """租户内已有相同 hash 的对象地址（库里有、且 MinIO 还在）。"""
    if not file_hash:
        return None
    urls: list[str] = []
    chat_url = (
        await db.execute(
            select(ChatFile.file_url)
            .where(ChatFile.tenant_id == tenant_id, ChatFile.file_hash == file_hash)
            .order_by(ChatFile.created_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if chat_url:
        urls.append(chat_url)

    inv_url = (
        await db.execute(
            select(Invoice.file_url)
            .where(
                Invoice.tenant_id == tenant_id,
                Invoice.file_hash == file_hash,
                Invoice.file_url.is_not(None),
            )
            .order_by(Invoice.created_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if inv_url:
        urls.append(inv_url)

    contract_url = (
        await db.execute(
            select(Contract.file_url)
            .where(
                Contract.tenant_id == tenant_id,
                Contract.file_hash == file_hash,
                Contract.file_url.is_not(None),
            )
            .order_by(Contract.created_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if contract_url:
        urls.append(contract_url)

    for url in urls:
        if url and storage_service.object_exists(url):
            return url
    return None


async def resolve_upload_url(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    file_hash: str,
    content: bytes,
    ext: str,
    content_type: str,
) -> tuple[str, bool]:
    """返回 (file_url, reused)。能复用就不写 MinIO。"""
    existing = await find_existing_url(db, tenant_id, file_hash)
    if existing:
        logger.info("upload reuse existing url tenant=%s hash=%s", tenant_id, file_hash[:12])
        return existing, True

    bucket = settings.minio_bucket_kb
    key = canonical_object_key(tenant_id, file_hash, ext)
    canonical = f"s3://{bucket}/{key}"
    if storage_service.object_exists(canonical):
        logger.info("upload reuse hash key tenant=%s hash=%s", tenant_id, file_hash[:12])
        return canonical, True

    url = storage_service.upload_file(
        bucket=bucket,
        object_name=key,
        data=content,
        content_type=content_type,
    )
    return url, False


async def collect_referenced_urls(db: AsyncSession) -> set[str]:
    """档案和附件仍指向的对象地址。"""
    urls: set[str] = set()
    for model in (ChatFile, Invoice, Contract):
        rows = (await db.execute(select(model.file_url))).scalars().all()
        for value in rows:
            if value:
                urls.add(value)
    return urls


def _is_chat_object(key: str) -> bool:
    """只清理对话附件前缀，躲开知识库其它对象。"""
    return bool(_CHAT_OBJECT_RE.match(key))


def _older_than(last_modified: Any, cutoff: datetime) -> bool:
    """MinIO last_modified 可能带 tz，统一成 UTC 再比。"""
    if last_modified is None:
        return False
    when = last_modified
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when < cutoff


async def cleanup_orphan_objects(
    db: AsyncSession,
    *,
    orphan_hours: int = 24,
) -> int:
    """删掉库里没人引用、且超过保留期的对话附件对象。"""
    referenced = await collect_referenced_urls(db)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=orphan_hours)
    deleted = 0
    buckets = [
        settings.minio_bucket_kb,
        settings.minio_bucket_invoice,
        settings.minio_bucket_contract,
    ]
    for bucket in buckets:
        for key, modified in storage_service.list_objects(bucket, prefix=""):
            if bucket == settings.minio_bucket_kb and not _is_chat_object(key):
                continue
            url = f"s3://{bucket}/{key}"
            if url in referenced:
                continue
            if not _older_than(modified, cutoff):
                continue
            try:
                storage_service.delete_file(bucket, key)
                deleted += 1
                logger.info("orphan object deleted %s", url)
            except Exception:
                logger.exception("orphan delete failed %s", url)
    return deleted


async def collapse_duplicate_urls(db: AsyncSession) -> int:
    """同一 hash 多份对象时，档案改指最先那份，其余可被孤儿清理删掉。"""
    updated = 0
    hash_to_urls: dict[tuple[UUID, str], list[str]] = {}

    def _add(tenant_id: UUID, file_hash: str | None, file_url: str | None) -> None:
        if not file_hash or not file_url:
            return
        hash_to_urls.setdefault((tenant_id, file_hash), [])
        if file_url not in hash_to_urls[(tenant_id, file_hash)]:
            hash_to_urls[(tenant_id, file_hash)].append(file_url)

    chat_rows = (
        await db.execute(select(ChatFile.tenant_id, ChatFile.file_hash, ChatFile.file_url))
    ).all()
    for tenant_id, file_hash, file_url in chat_rows:
        _add(tenant_id, file_hash, file_url)

    inv_rows = (
        await db.execute(select(Invoice.tenant_id, Invoice.file_hash, Invoice.file_url))
    ).all()
    for tenant_id, file_hash, file_url in inv_rows:
        _add(tenant_id, file_hash, file_url)

    contract_rows = (
        await db.execute(select(Contract.tenant_id, Contract.file_hash, Contract.file_url))
    ).all()
    for tenant_id, file_hash, file_url in contract_rows:
        _add(tenant_id, file_hash, file_url)

    for (tenant_id, file_hash), urls in hash_to_urls.items():
        if len(urls) < 2:
            continue
        canonical = next((url for url in urls if storage_service.object_exists(url)), urls[0])
        extras = [url for url in urls if url != canonical]
        if not extras:
            continue
        for model in (ChatFile, Invoice, Contract):
            result = await db.execute(
                update(model)
                .where(
                    model.tenant_id == tenant_id,
                    model.file_hash == file_hash,
                    model.file_url.in_(extras),
                )
                .values(file_url=canonical)
            )
            updated += result.rowcount or 0
        logger.info(
            "collapsed duplicate urls tenant=%s hash=%s keep=%s extras=%s",
            tenant_id,
            file_hash[:12],
            canonical,
            len(extras),
        )

    await db.commit()
    return updated


async def run_file_gc(*, orphan_hours: int = 24) -> dict[str, int]:
    """先合并重复引用，再删孤儿对象。"""
    from app.core.database import async_session_factory

    async with async_session_factory() as db:
        collapsed = await collapse_duplicate_urls(db)
        orphans = await cleanup_orphan_objects(db, orphan_hours=orphan_hours)
    return {"collapsed_rows": collapsed, "orphan_deleted": orphans}
