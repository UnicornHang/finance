"""附件 hash 去重与孤儿清理。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.config import settings
from app.models import ChatFile, Session, User
from app.services.file_gc import (
    canonical_object_key,
    cleanup_orphan_objects,
    collapse_duplicate_urls,
    resolve_upload_url,
)


async def _admin_and_session(db_session) -> tuple[User, Session]:
    """测试用管理员和会话。"""
    user = (await db_session.execute(select(User).where(User.account == "admin"))).scalars().first()
    assert user is not None
    session = Session(tenant_id=user.tenant_id, user_id=user.id, title="file-gc")
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return user, session


@pytest.mark.asyncio
async def test_resolve_upload_url_reuses_existing(db_session):
    """库里已有相同 hash 且对象仍在时，不再 put MinIO。"""
    user, session = await _admin_and_session(db_session)
    file_hash = "a" * 64
    existing = f"s3://{settings.minio_bucket_kb}/{user.tenant_id}/files/by-hash/{file_hash}.pdf"
    row = ChatFile(
        tenant_id=user.tenant_id,
        user_id=user.id,
        session_id=session.id,
        file_url=existing,
        file_hash=file_hash,
        original_filename="old.pdf",
        recognize_status="succeeded",
    )
    db_session.add(row)
    await db_session.commit()

    with (
        patch("app.services.file_gc.storage_service.object_exists", return_value=True),
        patch("app.services.file_gc.storage_service.upload_file") as upload,
    ):
        url, reused = await resolve_upload_url(
            db_session,
            tenant_id=user.tenant_id,
            file_hash=file_hash,
            content=b"%PDF",
            ext=".pdf",
            content_type="application/pdf",
        )
    assert reused is True
    assert url == existing
    upload.assert_not_called()

    await db_session.delete(row)
    await db_session.delete(session)
    await db_session.commit()


@pytest.mark.asyncio
async def test_resolve_upload_url_writes_hash_key(db_session):
    """没有可复用对象时写入 by-hash 路径。"""
    tenant_id = uuid4()
    file_hash = "b" * 64
    expected_key = canonical_object_key(tenant_id, file_hash, ".pdf")
    expected_url = f"s3://{settings.minio_bucket_kb}/{expected_key}"

    with (
        patch("app.services.file_gc.storage_service.object_exists", return_value=False),
        patch(
            "app.services.file_gc.storage_service.upload_file",
            return_value=expected_url,
        ) as upload,
    ):
        url, reused = await resolve_upload_url(
            db_session,
            tenant_id=tenant_id,
            file_hash=file_hash,
            content=b"%PDF",
            ext=".pdf",
            content_type="application/pdf",
        )
    assert reused is False
    assert url == expected_url
    upload.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_orphan_deletes_old_unreferenced():
    """超过保留期且库中无引用的对话附件会被删。"""
    tenant = uuid4()
    old_key = f"{tenant}/files/by-hash/{'c' * 64}.pdf"
    kb_doc = f"{tenant}/kb/policy.pdf"
    old_time = datetime.now(timezone.utc) - timedelta(hours=48)

    with (
        patch("app.services.file_gc.collect_referenced_urls", return_value=set()),
        patch(
            "app.services.file_gc.storage_service.list_objects",
            side_effect=lambda bucket, prefix="": (
                [(old_key, old_time), (kb_doc, old_time)]
                if bucket == settings.minio_bucket_kb
                else []
            ),
        ),
        patch("app.services.file_gc.storage_service.delete_file") as delete_file,
    ):
        deleted = await cleanup_orphan_objects(None, orphan_hours=24)  # type: ignore[arg-type]

    assert deleted == 1
    delete_file.assert_called_once_with(settings.minio_bucket_kb, old_key)


@pytest.mark.asyncio
async def test_collapse_duplicate_urls_rewrites_to_canonical(db_session):
    """同一 hash 多条 URL 时改写成仍存在的那份。"""
    user, session = await _admin_and_session(db_session)
    file_hash = "d" * 64
    keep = f"s3://{settings.minio_bucket_kb}/{user.tenant_id}/files/by-hash/{file_hash}.pdf"
    extra = f"s3://{settings.minio_bucket_kb}/{user.tenant_id}/files/{uuid4()}.pdf"
    rows = [
        ChatFile(
            tenant_id=user.tenant_id,
            user_id=user.id,
            session_id=session.id,
            file_url=keep,
            file_hash=file_hash,
            recognize_status="succeeded",
        ),
        ChatFile(
            tenant_id=user.tenant_id,
            user_id=user.id,
            session_id=session.id,
            file_url=extra,
            file_hash=file_hash,
            recognize_status="succeeded",
        ),
    ]
    db_session.add_all(rows)
    await db_session.commit()

    with patch(
        "app.services.file_gc.storage_service.object_exists",
        side_effect=lambda url: url == keep,
    ):
        updated = await collapse_duplicate_urls(db_session)

    assert updated >= 1
    refreshed = (
        await db_session.execute(select(ChatFile).where(ChatFile.file_hash == file_hash))
    ).scalars().all()
    assert all(item.file_url == keep for item in refreshed)

    for item in refreshed:
        await db_session.delete(item)
    await db_session.delete(session)
    await db_session.commit()
