"""Pydantic schemas（请求/响应 DTO）。"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

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

_USER_ROLES = frozenset({"employee", "finance", "admin"})
_USER_STATUSES = frozenset({"active", "disabled"})


def _normalize_optional_text(value: str | None) -> str | None:
    """空白部门视为未填写。"""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    account: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=10, max_length=72)
    role: str
    dept: str | None = Field(default=None, max_length=100)

    @field_validator("name", "account")
    @classmethod
    def strip_required(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("不能为空")
        return stripped

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        if value not in _USER_ROLES:
            raise ValueError("角色必须是 employee / finance / admin")
        return value

    @field_validator("dept")
    @classmethod
    def validate_dept(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    role: str | None = None
    dept: str | None = Field(default=None, max_length=100)
    status: str | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("姓名不能为空")
        return stripped

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in _USER_ROLES:
            raise ValueError("角色必须是 employee / finance / admin")
        return value

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in _USER_STATUSES:
            raise ValueError("状态必须是 active / disabled")
        return value

    @field_validator("dept")
    @classmethod
    def validate_dept(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)


class UserOut(BaseSchema):
    id: UUID
    name: str
    account: str
    role: str
    dept: str | None
    status: str
    created_at: datetime


class PasswordResetOut(BaseModel):
    """重置密码后仅返回一次临时密码。"""

    user_id: UUID
    temporary_password: str


class ProfileUpdate(BaseModel):
    """当前用户更新自己的姓名/部门；账号与角色不可改。"""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    dept: str | None = Field(default=None, max_length=100)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("姓名不能为空")
        return stripped

    @field_validator("dept")
    @classmethod
    def validate_dept(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)


class PasswordChange(BaseModel):
    """当前用户修改登录密码。"""

    old_password: str = Field(min_length=1, max_length=72)
    new_password: str = Field(min_length=10, max_length=72)


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