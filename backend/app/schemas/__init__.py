"""Pydantic schemas（请求/响应 DTO）。"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ================ 通用 ================

class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


# ================ 认证 ================

class LoginRequest(BaseModel):
    account: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


# ================ 用户 ================

class UserCreate(BaseModel):
    name: str
    account: str
    password: str = Field(min_length=10)
    role: str
    dept: str | None = None


class UserUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    dept: str | None = None
    status: str | None = None


class UserOut(BaseSchema):
    id: UUID
    name: str
    account: str
    role: str
    dept: str | None
    status: str
    created_at: datetime


# ================ 会话 ================

class SessionCreate(BaseModel):
    title: str | None = None


class SessionUpdate(BaseModel):
    title: str | None = None


class SessionOut(BaseSchema):
    id: UUID
    title: str | None
    summary: str | None
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseSchema):
    id: UUID
    role: str
    content: str | None
    tool_calls: dict | None
    # 与 content 同一次发送的图片/文件
    attachments: list[dict] | None = None
    created_at: datetime


# ================ 发票 ================

class InvoiceCreate(BaseModel):
    invoice_title: str | None = None
    company: str | None = None
    tax_id: str | None = None
    invoice_code: str | None = None
    invoice_number: str | None = None
    invoice_date: datetime | None = None
    amount_excl_tax: float | None = None
    tax_amount: float | None = None
    amount_incl_tax: float | None = None
    invoice_type: str | None = None
    seller: str | None = None
    buyer: str | None = None
    remark: str | None = None
    file_url: str
    file_hash: str


class InvoiceUpdate(BaseModel):
    invoice_title: str | None = None
    company: str | None = None
    tax_id: str | None = None
    invoice_code: str | None = None
    invoice_number: str | None = None
    invoice_date: datetime | None = None
    amount_excl_tax: float | None = None
    tax_amount: float | None = None
    amount_incl_tax: float | None = None
    invoice_type: str | None = None
    seller: str | None = None
    buyer: str | None = None
    remark: str | None = None


class InvoiceOut(BaseSchema):
    id: UUID
    invoice_title: str | None
    company: str | None
    tax_id: str | None
    invoice_code: str | None
    invoice_number: str | None
    invoice_date: datetime | None
    amount_excl_tax: float | None
    tax_amount: float | None
    amount_incl_tax: float | None
    invoice_type: str | None
    seller: str | None
    buyer: str | None
    remark: str | None
    file_url: str | None
    status: str
    created_at: datetime


# ================ 合同 ================

class ContractOut(BaseSchema):
    id: UUID
    contract_name: str | None
    contract_no: str | None
    party_a: str | None
    party_b: str | None
    sign_date: datetime | None
    effective_start: datetime | None
    effective_end: datetime | None
    amount: float | None
    key_clauses: str | None
    review_result: dict | None
    risk_level: str | None
    status: str
    created_at: datetime


# ================ LLM 配置 ================

class LlmConfigOut(BaseSchema):
    id: UUID
    scene: str
    model: str
    provider: str | None
    base_url: str | None
    temperature: float
    max_tokens: int
    enabled: bool


class LlmConfigUpdate(BaseModel):
    model: str
    provider: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    enabled: bool | None = None


# ================ 知识库 ================

class KbDocumentOut(BaseSchema):
    id: UUID
    title: str
    doc_type: str | None
    status: str
    chunk_count: int
    version: int
    created_at: datetime