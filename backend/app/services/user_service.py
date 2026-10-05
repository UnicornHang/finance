"""用户管理服务（租户内 CRUD、角色、停用、密码重置）。"""

from __future__ import annotations

import secrets
import string
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError, ConflictError, NotFoundError
from app.core.security import hash_password
from app.models import User
from app.schemas import PasswordResetOut, UserCreate, UserOut, UserUpdate
from app.services.audit_service import write_audit_log

_TEMP_PASSWORD_ALPHABET = string.ascii_letters + string.digits + "!@#$%"


class UserService:
    """管理员用户管理：列表、创建、更新、停用、重置密码。"""

    def effective_status(self, user: User) -> str:
        """对外展示状态：停用优先，其次登录锁定，否则取库内 status。"""
        if user.status == "disabled":
            return "disabled"
        if self._is_temporarily_locked(user):
            return "locked"
        return user.status or "active"

    def to_out(self, user: User) -> UserOut:
        """序列化为不带密码哈希的用户 DTO。"""
        return UserOut(
            id=user.id,
            name=user.name,
            account=user.account,
            role=user.role,
            dept=user.dept,
            status=self.effective_status(user),
            created_at=user.created_at,
        )

    def _public_snapshot(self, user: User) -> dict[str, Any]:
        """审计用快照，不含密码。"""
        return self.to_out(user).model_dump(mode="json")

    async def list_users(self, db: AsyncSession, tenant_id: UUID) -> list[UserOut]:
        """列出当前租户全部用户，按创建时间倒序。"""
        result = await db.execute(
            select(User)
            .where(User.tenant_id == tenant_id)
            .order_by(User.created_at.desc())
        )
        return [self.to_out(row) for row in result.scalars().all()]

    async def create_user(
        self,
        db: AsyncSession,
        *,
        actor: User,
        payload: UserCreate,
        ip: str | None = None,
        ua: str | None = None,
    ) -> UserOut:
        """在当前租户创建用户。"""
        await self._ensure_account_unique(db, payload.account)
        row = User(
            tenant_id=actor.tenant_id,
            name=payload.name,
            account=payload.account,
            password_hash=hash_password(payload.password),
            role=payload.role,
            dept=payload.dept,
            status="active",
        )
        db.add(row)
        try:
            await db.flush()
        except IntegrityError as exc:
            await db.rollback()
            raise ConflictError("账号已存在", code="ACCOUNT_EXISTS") from exc

        await write_audit_log(
            db,
            tenant_id=actor.tenant_id,
            user_id=actor.id,
            operation_type="create_user",
            target_type="user",
            target_id=row.id,
            after=self._public_snapshot(row),
            ip=ip,
            ua=ua,
        )
        await db.commit()
        await db.refresh(row)
        return self.to_out(row)

    async def update_user(
        self,
        db: AsyncSession,
        *,
        actor: User,
        user_id: UUID,
        payload: UserUpdate,
        ip: str | None = None,
        ua: str | None = None,
    ) -> UserOut:
        """更新姓名、角色、部门、启用/停用；启用时同时解除登录锁定。"""
        row = await self._get_in_tenant(db, actor.tenant_id, user_id)
        before = self._public_snapshot(row)
        data = payload.model_dump(exclude_unset=True)

        if "role" in data and data["role"] != row.role:
            await self._guard_last_admin(
                db,
                tenant_id=actor.tenant_id,
                target=row,
                next_role=data["role"],
                next_status=data.get("status", row.status),
            )
        if "status" in data and data["status"] == "disabled":
            self._guard_self_disable(actor, row)
            await self._guard_last_admin(
                db,
                tenant_id=actor.tenant_id,
                target=row,
                next_role=data.get("role", row.role),
                next_status="disabled",
            )

        if "name" in data:
            row.name = data["name"]
        if "role" in data:
            row.role = data["role"]
        if "dept" in data:
            row.dept = data["dept"]
        if "status" in data:
            row.status = data["status"]
            if data["status"] == "active":
                row.failed_login_attempts = 0
                row.locked_until = None

        await db.flush()
        await write_audit_log(
            db,
            tenant_id=actor.tenant_id,
            user_id=actor.id,
            operation_type="update_user",
            target_type="user",
            target_id=row.id,
            before=before,
            after=self._public_snapshot(row),
            ip=ip,
            ua=ua,
        )
        await db.commit()
        await db.refresh(row)
        return self.to_out(row)

    async def reset_password(
        self,
        db: AsyncSession,
        *,
        actor: User,
        user_id: UUID,
        ip: str | None = None,
        ua: str | None = None,
    ) -> PasswordResetOut:
        """生成临时密码并覆盖哈希；同时清登录失败计数。"""
        row = await self._get_in_tenant(db, actor.tenant_id, user_id)
        temporary = self._generate_temporary_password()
        row.password_hash = hash_password(temporary)
        row.failed_login_attempts = 0
        row.locked_until = None
        await db.flush()
        await write_audit_log(
            db,
            tenant_id=actor.tenant_id,
            user_id=actor.id,
            operation_type="reset_password",
            target_type="user",
            target_id=row.id,
            after={"account": row.account},
            ip=ip,
            ua=ua,
        )
        await db.commit()
        return PasswordResetOut(user_id=row.id, temporary_password=temporary)

    async def disable_user(
        self,
        db: AsyncSession,
        *,
        actor: User,
        user_id: UUID,
        ip: str | None = None,
        ua: str | None = None,
    ) -> UserOut:
        """软删除：将状态改为停用，保留历史单据关联。"""
        return await self.update_user(
            db,
            actor=actor,
            user_id=user_id,
            payload=UserUpdate(status="disabled"),
            ip=ip,
            ua=ua,
        )

    async def _get_in_tenant(
        self, db: AsyncSession, tenant_id: UUID, user_id: UUID
    ) -> User:
        """按租户取用户，越权当不存在。"""
        row = await db.get(User, user_id)
        if row is None or row.tenant_id != tenant_id:
            raise NotFoundError("用户不存在")
        return row

    async def _ensure_account_unique(self, db: AsyncSession, account: str) -> None:
        """账号全局唯一（与现有表约束一致）。"""
        result = await db.execute(select(User.id).where(User.account == account).limit(1))
        if result.scalar_one_or_none() is not None:
            raise ConflictError("账号已存在", code="ACCOUNT_EXISTS")

    async def _guard_last_admin(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID,
        target: User,
        next_role: str,
        next_status: str,
    ) -> None:
        """禁止去掉租户内最后一个启用中的管理员。"""
        if target.role != "admin" or target.status != "active":
            return
        losing_admin = next_role != "admin" or next_status != "active"
        if not losing_admin:
            return
        count = await self._active_admin_count(db, tenant_id)
        if count <= 1:
            raise BusinessError("不能停用或降级租户内最后一名管理员", code="LAST_ADMIN")

    def _guard_self_disable(self, actor: User, target: User) -> None:
        """禁止管理员停用自己，避免锁死后台。"""
        if actor.id == target.id:
            raise BusinessError("不能停用当前登录账号", code="SELF_DISABLE")

    async def _active_admin_count(self, db: AsyncSession, tenant_id: UUID) -> int:
        """统计租户内启用状态的管理员数量。"""
        result = await db.execute(
            select(func.count())
            .select_from(User)
            .where(
                User.tenant_id == tenant_id,
                User.role == "admin",
                User.status == "active",
            )
        )
        return int(result.scalar_one())

    def _is_temporarily_locked(self, user: User) -> bool:
        """是否仍在登录锁定期内。"""
        if user.locked_until is None:
            return False
        locked_until = user.locked_until
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        return locked_until > datetime.now(timezone.utc)

    def _generate_temporary_password(self, length: int = 12) -> str:
        """生成一次性临时密码，满足最短 10 位。"""
        chars = [
            secrets.choice(string.ascii_uppercase),
            secrets.choice(string.ascii_lowercase),
            secrets.choice(string.digits),
            secrets.choice("!@#$%"),
        ]
        chars.extend(secrets.choice(_TEMP_PASSWORD_ALPHABET) for _ in range(length - 4))
        secrets.SystemRandom().shuffle(chars)
        return "".join(chars)


user_service = UserService()
