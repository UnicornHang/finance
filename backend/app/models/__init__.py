"""SQLAlchemy ORM 模型。"""

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 声明基类。"""

    pass


# ================ 枚举 ================

class UserRole(str, Enum):
    EMPLOYEE = "employee"
    FINANCE = "finance"
    ADMIN = "admin"


class InvoiceType(str, Enum):
    SPECIAL = "special"  # 专票
    GENERAL = "general"  # 普票
    ELECTRONIC = "electronic"


class RiskLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DocStatus(str, Enum):
    PENDING = "pending"
    INDEXING = "indexing"
    ACTIVE = "active"
    FAILED = "failed"
    DISABLED = "disabled"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


# ================ 用户 ================

class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    account: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    dept: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))


# ================ 会话 ================

class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    title: Mapped[str | None] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), onupdate=text("NOW()")
    )

    __table_args__ = (
        Index("idx_sessions_user", "tenant_id", "user_id", "updated_at"),
    )


# ================ 消息 ================

class Message(Base):
    __tablename__ = "messages"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    session_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    tool_calls: Mapped[dict | None] = mapped_column(JSONB)
    # 与本条 content 同时发出的图片/文件，不占用 tool_calls
    attachments: Mapped[list | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))

    __table_args__ = (
        Index("idx_messages_session", "session_id", "created_at"),
    )


# ================ 聊天附件 ================

class ChatFile(Base):
    """任意图片或文件。发送前 message_id 为空，发送后与那条消息绑定。不限于发票。"""

    __tablename__ = "chat_files"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    session_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL")
    )
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(300))
    content_type: Mapped[str | None] = mapped_column(String(120))
    size: Mapped[int | None] = mapped_column(Integer)
    # image 或 file，与后面判成发票/合同无关
    file_kind: Mapped[str] = mapped_column(String(20), default="file")
    intent: Mapped[str | None] = mapped_column(String(20))
    recognize_status: Mapped[str] = mapped_column(String(20), default="pending")
    recognize_error: Mapped[str | None] = mapped_column(Text)
    invoice_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"))
    contract_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("contracts.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), onupdate=text("NOW()")
    )

    __table_args__ = (
        Index("idx_chat_files_session", "session_id", "created_at"),
        Index("idx_chat_files_message", "message_id"),
    )


# ================ 会话记忆 ================

class SessionMemory(Base):
    __tablename__ = "session_memory"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_value: Mapped[dict] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), onupdate=text("NOW()")
    )


# ================ 消息向量 ================

class MessageEmbedding(Base):
    __tablename__ = "message_embeddings"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    embedding: Mapped[list[float]] = mapped_column(Vector(1536))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))


# ================ 发票 ================

class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    invoice_title: Mapped[str | None] = mapped_column(String(200))
    company: Mapped[str | None] = mapped_column(String(200))
    tax_id: Mapped[str | None] = mapped_column(String(50))
    invoice_code: Mapped[str | None] = mapped_column(String(50))
    invoice_number: Mapped[str | None] = mapped_column(String(50))
    invoice_date: Mapped[datetime | None] = mapped_column(Date)
    amount_excl_tax: Mapped[float | None] = mapped_column(Numeric(15, 2))
    tax_amount: Mapped[float | None] = mapped_column(Numeric(15, 2))
    amount_incl_tax: Mapped[float | None] = mapped_column(Numeric(15, 2))
    invoice_type: Mapped[str | None] = mapped_column(String(20))
    seller: Mapped[str | None] = mapped_column(String(200))
    buyer: Mapped[str | None] = mapped_column(String(200))
    remark: Mapped[str | None] = mapped_column(Text)

    file_url: Mapped[str | None] = mapped_column(String(500))
    file_hash: Mapped[str | None] = mapped_column(String(64))
    ocr_confidence: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default="active")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), onupdate=text("NOW()")
    )

    __table_args__ = (
        Index("idx_invoices_tenant_user", "tenant_id", "user_id", "created_at"),
        Index("idx_invoices_status", "tenant_id", "status"),
        UniqueConstraint(
            "tenant_id",
            "invoice_code",
            "invoice_number",
            name="uq_invoice_tenant_code_number",
        ),
    )


# ================ 合同 ================

class Contract(Base):
    __tablename__ = "contracts"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    contract_name: Mapped[str | None] = mapped_column(String(300))
    contract_no: Mapped[str | None] = mapped_column(String(100))
    party_a: Mapped[str | None] = mapped_column(String(200))
    party_b: Mapped[str | None] = mapped_column(String(200))
    sign_date: Mapped[datetime | None] = mapped_column(Date)
    effective_start: Mapped[datetime | None] = mapped_column(Date)
    effective_end: Mapped[datetime | None] = mapped_column(Date)
    amount: Mapped[float | None] = mapped_column(Numeric(18, 2))

    key_clauses: Mapped[str | None] = mapped_column(Text)
    review_result: Mapped[dict | None] = mapped_column(JSONB)
    risk_level: Mapped[str | None] = mapped_column(String(10))

    file_url: Mapped[str | None] = mapped_column(String(500))
    file_hash: Mapped[str | None] = mapped_column(String(64))
    parse_status: Mapped[str] = mapped_column(String(20), default="pending")
    status: Mapped[str] = mapped_column(String(20), default="active")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), onupdate=text("NOW()")
    )

    __table_args__ = (
        Index("idx_contracts_tenant_user", "tenant_id", "user_id", "created_at"),
        Index("idx_contracts_risk", "tenant_id", "risk_level"),
    )


# ================ 知识库文档 ================

class KbDocument(Base):
    __tablename__ = "kb_documents"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))  # NULL = 通用
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    doc_type: Mapped[str | None] = mapped_column(String(50))
    source_file: Mapped[str | None] = mapped_column(String(500))
    content: Mapped[str | None] = mapped_column(Text)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    embedding_model: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error_message: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    uploaded_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), onupdate=text("NOW()")
    )


class KbChunk(Base):
    __tablename__ = "kb_chunks"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    doc_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("kb_documents.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536))
    token_count: Mapped[int | None] = mapped_column(Integer)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))


# ================ LLM 配置 ================

class LlmConfig(Base):
    __tablename__ = "llm_configs"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    scene: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(50))
    api_key_encrypted: Mapped[str | None] = mapped_column(Text)
    base_url: Mapped[str | None] = mapped_column(String(300))
    temperature: Mapped[float] = mapped_column(Numeric(3, 2), default=0.7)
    max_tokens: Mapped[int] = mapped_column(Integer, default=2000)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=30)
    extra_params: Mapped[dict | None] = mapped_column(JSONB)
    system_prompt: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), onupdate=text("NOW()")
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "scene", name="uk_llm_tenant_scene"),
    )


# ================ 审计日志 ================

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    operation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(50))
    target_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    before_value: Mapped[dict | None] = mapped_column(JSONB)
    after_value: Mapped[dict | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(String(64))
    ua: Mapped[str | None] = mapped_column(String(500))
    result: Mapped[str | None] = mapped_column(String(20))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))

    __table_args__ = (
        Index("idx_audit_tenant_time", "tenant_id", "created_at"),
        Index("idx_audit_user", "tenant_id", "user_id", "created_at"),
        Index("idx_audit_target", "tenant_id", "target_type", "target_id"),
    )


# 导出供 Alembic 自动生成迁移使用
__all__ = [
    "Base",
    "User",
    "Session",
    "Message",
    "SessionMemory",
    "MessageEmbedding",
    "Invoice",
    "Contract",
    "KbDocument",
    "KbChunk",
    "LlmConfig",
    "AuditLog",
    "UserRole",
    "InvoiceType",
    "RiskLevel",
    "DocStatus",
    "MessageRole",
]