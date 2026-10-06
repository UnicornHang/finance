"""用户认证服务。"""

import math
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import AccountLockedError, BusinessError, UnauthorizedError
from app.core.security import hash_password, verify_password
from app.models import User
from app.schemas import PasswordChange, ProfileUpdate
from app.services.audit_service import write_audit_log


class AuthService:
    """用户认证 + 查询。"""

    async def authenticate(self, db: AsyncSession, account: str, password: str) -> User:
        """验证账号密码，返回用户对象。

        连续输错达到阈值后锁定一段时间。对「用户不存在」和「密码错误」
        返回相同文案，避免账号枚举；锁定后返回独立提示。
        """
        result = await db.execute(
            select(User).where(User.account == account).with_for_update()
        )
        user = result.scalar_one_or_none()

        if user is None:
            raise UnauthorizedError("账号或密码错误")

        self._release_expired_lock(user)

        if self._is_temporarily_locked(user):
            await db.commit()
            raise AccountLockedError(self._lock_error_message(user))

        if not verify_password(password, user.password_hash or ""):
            newly_locked = self._apply_failed_attempt(user)
            await db.commit()
            if newly_locked:
                raise AccountLockedError(self._lock_error_message(user))
            raise UnauthorizedError("账号或密码错误")

        if user.status != "active":
            raise UnauthorizedError("账号已停用，请联系管理员")

        self._clear_lock_state(user)
        await db.commit()
        return user

    async def get_by_id(self, db: AsyncSession, user_id: UUID) -> User | None:
        """根据 ID 查询用户。"""
        return await db.get(User, user_id)

    async def update_profile(
        self,
        db: AsyncSession,
        *,
        user: User,
        payload: ProfileUpdate,
        ip: str | None = None,
        ua: str | None = None,
    ) -> User:
        """更新当前用户姓名、部门；不改账号、角色、状态。"""
        data = payload.model_dump(exclude_unset=True)
        if not data:
            return user

        before = {"name": user.name, "dept": user.dept}
        if "name" in data:
            user.name = data["name"]
        if "dept" in data:
            user.dept = data["dept"]
        await db.flush()
        await write_audit_log(
            db,
            tenant_id=user.tenant_id,
            user_id=user.id,
            operation_type="update_profile",
            target_type="user",
            target_id=user.id,
            before=before,
            after={"name": user.name, "dept": user.dept},
            ip=ip,
            ua=ua,
        )
        await db.commit()
        await db.refresh(user)
        return user

    async def change_password(
        self,
        db: AsyncSession,
        *,
        user: User,
        payload: PasswordChange,
        ip: str | None = None,
        ua: str | None = None,
    ) -> None:
        """校验旧密码后写入新哈希；错误旧密码返回 400，避免前端把会话清掉。"""
        if not verify_password(payload.old_password, user.password_hash or ""):
            raise BusinessError("当前密码不正确", code="WRONG_PASSWORD")
        if verify_password(payload.new_password, user.password_hash or ""):
            raise BusinessError("新密码不能与当前密码相同", code="PASSWORD_UNCHANGED")

        user.password_hash = hash_password(payload.new_password)
        user.failed_login_attempts = 0
        user.locked_until = None
        await db.flush()
        await write_audit_log(
            db,
            tenant_id=user.tenant_id,
            user_id=user.id,
            operation_type="change_password",
            target_type="user",
            target_id=user.id,
            after={"account": user.account},
            ip=ip,
            ua=ua,
        )
        await db.commit()

    def _utcnow(self) -> datetime:
        """当前 UTC 时间。"""
        return datetime.now(timezone.utc)

    def _as_aware_utc(self, value: datetime) -> datetime:
        """将数据库时间统一为 aware UTC，便于比较。"""
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _is_temporarily_locked(self, user: User) -> bool:
        """判断账号是否仍在登录锁定期内。"""
        if user.locked_until is None:
            return False
        return self._as_aware_utc(user.locked_until) > self._utcnow()

    def _release_expired_lock(self, user: User) -> None:
        """锁定已过期则清零计数，允许重新登录。"""
        if user.locked_until is None:
            return
        if self._as_aware_utc(user.locked_until) > self._utcnow():
            return
        self._clear_lock_state(user)

    def _clear_lock_state(self, user: User) -> None:
        """登录成功或锁定期满后复位失败计数。"""
        user.failed_login_attempts = 0
        user.locked_until = None

    def _apply_failed_attempt(self, user: User) -> bool:
        """记录一次密码错误；达到阈值则写入锁定截止时间。

        Returns:
            本次失败是否刚好触发锁定。
        """
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        if user.failed_login_attempts < settings.login_max_failed_attempts:
            return False
        user.locked_until = self._utcnow() + timedelta(
            minutes=settings.login_lockout_minutes
        )
        return True

    def _lock_error_message(self, user: User) -> str:
        """锁定提示，附剩余分钟数。"""
        minutes = settings.login_lockout_minutes
        if user.locked_until is not None:
            remaining = self._as_aware_utc(user.locked_until) - self._utcnow()
            minutes = max(1, math.ceil(remaining.total_seconds() / 60))
        return f"登录失败次数过多，账号已锁定，请 {minutes} 分钟后再试"


auth_service = AuthService()
