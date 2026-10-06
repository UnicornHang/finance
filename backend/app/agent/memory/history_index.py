"""历史消息切段、指代启发、异步嵌入与按需召回。"""

import asyncio
import logging
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.policy import POLICY_RAG_MIN_SCORE
from app.core.database import async_session_factory
from app.models import MessageEmbedding
from app.services.rag_service import rag_service

logger = logging.getLogger(__name__)

# create_task 只被事件循环弱引用，留存任务避免嵌入中途被回收
_INDEX_TASKS: set[asyncio.Task[None]] = set()

_RECALL_SQL = text(
    """
SELECT e.message_id::text AS message_id,
       m.role AS role,
       to_char(m.created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI') AS created_at,
       e.content AS content,
       1 - (e.embedding <=> :emb::vector) AS score
FROM message_embeddings e
JOIN messages m ON m.id = e.message_id
WHERE e.tenant_id = CAST(:tenant_id AS uuid)
  AND e.session_id = CAST(:session_id AS uuid)
  AND e.embedding IS NOT NULL
ORDER BY e.embedding <=> :emb::vector
LIMIT 8
"""
)

_HITS = ("上次", "之前", "刚才", "前面", "那张", "那份", "那个", "先前", "上回", "还记得")
_SESSION_HITS = ("上次", "刚才", "那张", "那份", "上回", "还记得")
_POLICY_WORDS = ("制度", "规定", "政策")
_ACK = {"好的", "嗯", "谢谢", "好"}


def chunk_text(text: str, size: int = 500, step: int = 450) -> list[str]:
    """按固定窗口与步长切段，末段保留剩余字符。"""
    if len(text) <= size:
        return [text]
    parts: list[str] = []
    start = 0
    while True:
        parts.append(text[start : start + size])
        if start + size >= len(text):
            break
        start += step
    return parts


def looks_like_history_reference(text: str) -> bool:
    """本轮是否在指代本会话更早的原话。"""
    raw = (text or "").strip()
    if not raw:
        return False
    bare = raw.strip("。.!！ ")
    if bare in _ACK and not any(hit in raw for hit in _HITS):
        return False
    if not any(hit in raw for hit in _HITS):
        return False
    if any(word in raw for word in _POLICY_WORDS) and not any(hit in raw for hit in _SESSION_HITS):
        return False
    return True


def format_related_history(rows: list[dict]) -> str:
    """将召回行格式化为列表文本；无行时返回空字符串（不含标题）。"""
    if not rows:
        return ""
    lines = [
        f"- {row['created_at']} {row['role']}：{row['content']}"
        for row in rows
    ]
    return "\n".join(lines)


def filter_recall_rows(
    rows: list[dict],
    *,
    exclude_ids: set[str],
    limit: int,
    min_score: float,
) -> list[dict]:
    """丢掉窗口内 id 与低于阈值的行，按输入顺序留下前 limit 条。"""
    kept: list[dict] = []
    for row in rows:
        message_id = str(row.get("message_id", ""))
        if message_id in exclude_ids:
            continue
        try:
            score = float(row["score"])
        except (KeyError, TypeError, ValueError):
            continue
        if score < min_score:
            continue
        # 召回正文只保留 500 字，role 与 created_at 原样带上
        kept.append(
            {
                "message_id": message_id,
                "role": row.get("role"),
                "created_at": row.get("created_at"),
                "content": str(row.get("content") or "")[:500],
                "score": score,
            }
        )
        if len(kept) >= limit:
            break
    return kept


def _vector_literal(embedding: list[float]) -> str:
    """pgvector 绑定参数用的文本向量。"""
    return "[" + ",".join(str(value) for value in embedding) + "]"


async def recall_history(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    session_id: UUID,
    question: str,
    exclude_ids: set[str],
) -> str:
    """召回本会话窗口外片段。嵌入或查询失败时返回空字符串。

    查询放在 savepoint 里。失败只回滚该 savepoint，不回滚请求会话。
    """
    try:
        embedding = await rag_service.embed(question, db=db, tenant_id=tenant_id)
    except Exception:
        # 嵌入失败不使当前事务失效；回滚会过期本轮仍要读的 ORM 对象
        logger.exception("历史召回嵌入失败 session_id=%s", session_id)
        return ""
    # async with 才会真正进入 savepoint；异常退出只回滚这一层
    rows: list[dict] = []
    try:
        async with db.begin_nested():
            result = await db.execute(
                _RECALL_SQL,
                {
                    "emb": _vector_literal(embedding),
                    "tenant_id": str(tenant_id),
                    "session_id": str(session_id),
                },
            )
            rows = [dict(row) for row in result.mappings().all()]
    except Exception:
        logger.exception("历史召回查询失败 session_id=%s", session_id)
        return ""
    kept = filter_recall_rows(
        rows,
        exclude_ids=exclude_ids,
        limit=3,
        min_score=POLICY_RAG_MIN_SCORE,
    )
    return format_related_history(kept)


def schedule_message_index(
    message_id: UUID,
    session_id: UUID,
    tenant_id: UUID,
    role: str,
    content: str,
) -> None:
    """落库后调度嵌入。只索引 user/assistant 且不少于 20 字的消息，调用方不要 await。"""
    body = content or ""
    if role not in {"user", "assistant"} or len(body) < 20:
        return
    task = asyncio.create_task(
        _index_message(message_id, session_id, tenant_id, body)
    )
    _INDEX_TASKS.add(task)
    task.add_done_callback(_INDEX_TASKS.discard)


async def _index_message(
    message_id: UUID,
    session_id: UUID,
    tenant_id: UUID,
    content: str,
) -> None:
    """用独立会话切段并写入向量。已有 (message_id, chunk_index) 跳过，失败只记日志。"""
    try:
        chunks = chunk_text(content)
        async with async_session_factory() as db:
            vectors = await rag_service.embed_batch(
                chunks, db=db, tenant_id=tenant_id
            )
            if len(vectors) != len(chunks):
                logger.error(
                    "嵌入条数与切段不一致 message_id=%s chunks=%s vectors=%s",
                    message_id,
                    len(chunks),
                    len(vectors),
                )
                return
            found = await db.execute(
                select(MessageEmbedding.chunk_index).where(
                    MessageEmbedding.message_id == message_id
                )
            )
            existing = set(found.scalars().all())
            added = False
            for index, part in enumerate(chunks):
                if index in existing:
                    continue
                db.add(
                    MessageEmbedding(
                        tenant_id=tenant_id,
                        session_id=session_id,
                        message_id=message_id,
                        chunk_index=index,
                        content=part,
                        embedding=vectors[index],
                    )
                )
                added = True
            if added:
                await db.commit()
    except Exception:
        logger.exception("消息嵌入失败 message_id=%s", message_id)
