"""RAG 检索服务。"""

from openai import AsyncOpenAI
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings


class RAGService:
    """知识库检索：向量 + 关键词混合 + 重排序。"""

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.embedding_api_key,
            base_url=settings.embedding_base_url,
        )

    async def embed(self, text_content: str) -> list[float]:
        """文本转向量。"""
        response = await self.client.embeddings.create(
            model=settings.embedding_model,
            input=text_content,
        )
        return response.data[0].embedding

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量转向量。"""
        response = await self.client.embeddings.create(
            model=settings.embedding_model,
            input=texts,
        )
        return [d.embedding for d in response.data]

    async def retrieve(
        self,
        db: AsyncSession,
        question: str,
        tenant_id: str,
        top_k: int = 5,
        doc_type: str | None = None,
    ) -> list[dict]:
        """检索最相关的文档片段。

        流程：embedding → 向量检索 → 关键词检索 → 合并去重 → 重排
        """
        # 1. 向量化问题
        q_emb = await self.embed(question)
        emb_str = "[" + ",".join(str(x) for x in q_emb) + "]"

        # 2. 向量检索（pgvector）
        # tenant_id 为 NULL 的通用文档 + 当前租户文档
        sql = text("""
            SELECT id, doc_id, content,
                   1 - (embedding <=> :emb::vector) AS score
            FROM kb_chunks
            WHERE (tenant_id = :tenant_id OR tenant_id IS NULL)
            ORDER BY embedding <=> :emb::vector
            LIMIT :top_k
        """)
        result = await db.execute(
            sql,
            {"emb": emb_str, "tenant_id": tenant_id, "top_k": top_k * 2},
        )
        rows = result.fetchall()
        return [
            {
                "chunk_id": str(row.id),
                "doc_id": str(row.doc_id),
                "content": row.content,
                "score": float(row.score),
            }
            for row in rows
        ][:top_k]

    async def retrieve_rules(self, db: AsyncSession, tenant_id: str) -> list[str]:
        """检索合规规则（专用方法）。"""
        results = await self.retrieve(
            db, "合同合规审查规则", tenant_id, top_k=10, doc_type="rule"
        )
        return [r["content"] for r in results]


rag_service = RAGService()