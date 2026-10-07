"""审计日志：追加写入、按租户查询、管理员导出。

日志只追加。本模块不提供更新或删除。查询窗口固定为最近一年，
过期记录仍留在表里，不在接口中返回。
"""

import json
import logging
from datetime import date, datetime, time, timedelta, timezone
from io import BytesIO
from typing import Any
from uuid import UUID

from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError
from app.models import AuditLog, User

logger = logging.getLogger(__name__)

# 产品约定保留一年；接口不返回更早的记录
RETENTION_DAYS = 365
EXPORT_MAX_ROWS = 5000
_CN_TZ = timezone(timedelta(hours=8))

# 操作类型中文名。未登记的类型回退为原始枚举值。
OPERATION_LABELS: dict[str, str] = {
    "login": "登录",
    "login.failed": "登录失败",
    "login.locked": "登录锁定",
    "logout": "登出",
    "update_profile": "修改资料",
    "change_password": "修改密码",
    "create_user": "创建用户",
    "update_user": "更新用户",
    "reset_password": "重置密码",
    "update_invoice": "编辑发票",
    "confirm_invoice": "确认归档发票",
    "delete_invoice": "删除发票",
    "invoice.rerecognize": "重新识别发票",
    "contract.create_pending": "上传合同",
    "contract.confirm": "确认归档合同",
    "contract.rereview": "重新审查合同",
    "contract.delete": "删除合同",
    "file.download": "下载文件",
    "kb.upload": "上传知识库文档",
    "kb.delete": "删除知识库文档",
    "kb.reindex": "重建知识库索引",
    "kb.test_retrieve": "知识库检索测试",
    "llm.upsert": "更新 LLM 配置",
    "llm.delete": "删除 LLM 配置",
    "export.create": "创建导出任务",
    "export.succeeded": "导出成功",
    "export.failed": "导出失败",
    "export.download": "下载导出文件",
}

_EXPORT_HEADERS: tuple[str, ...] = (
    "时间",
    "操作人",
    "账号",
    "操作类型",
    "结果",
    "资源类型",
    "资源 ID",
    "IP",
    "摘要",
    "变更前",
    "变更后",
    "失败原因",
)


def operation_label(operation_type: str) -> str:
    """操作类型的展示名。"""
    return OPERATION_LABELS.get(operation_type, operation_type)


def retention_floor(now: datetime | None = None) -> datetime:
    """查询窗口起点：当前时间往前一年。"""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current - timedelta(days=RETENTION_DAYS)


def resolve_time_window(
    start_date: date | None,
    end_date: date | None,
    *,
    now: datetime | None = None,
) -> tuple[datetime, datetime | None]:
    """把日历日收成 [start, end)。

    日期按北京时间理解。start 不会早于一年保留期。
    end 为结束日次日 0 点，使结束日当天的记录被包含。
    """
    floor = retention_floor(now)
    start = _cn_day_start(start_date) if start_date else floor
    if start < floor:
        start = floor
    end: datetime | None = None
    if end_date:
        end = _cn_day_start(end_date + timedelta(days=1))
    return start, end


def summarize_audit(after: dict[str, Any] | None, error_message: str | None) -> str:
    """列表和导出用的一行摘要，不展开完整快照。"""
    if error_message:
        return error_message
    payload = after or {}
    for key in ("title", "filename", "account", "scene", "question"):
        value = payload.get(key)
        if value:
            text = str(value)
            return text if len(text) <= 80 else f"{text[:80]}…"
    return ""


async def write_audit_log(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID | None,
    operation_type: str,
    target_type: str | None = None,
    target_id: UUID | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    ip: str | None = None,
    ua: str | None = None,
    result: str = "success",
    error_message: str | None = None,
) -> None:
    """写入一条审计日志。`flush` 而非 `commit`，让调用方控制事务边界。"""
    log = AuditLog(
        tenant_id=tenant_id,
        user_id=user_id,
        operation_type=operation_type,
        target_type=target_type,
        target_id=target_id,
        before_value=before,
        after_value=after,
        ip=ip,
        ua=ua,
        result=result,
        error_message=error_message,
    )
    db.add(log)
    try:
        await db.flush()
    except Exception as exc:
        logger.warning(
            "audit log flush failed: %s (operation=%s target=%s)",
            exc,
            operation_type,
            target_id,
        )


async def list_audit_logs(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID | None = None,
    operation_type: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """分页列出当前租户最近一年内的审计日志。"""
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    where = _filters(
        tenant_id=tenant_id,
        user_id=user_id,
        operation_type=operation_type,
        start_date=start_date,
        end_date=end_date,
    )
    total = (
        await db.execute(select(func.count()).select_from(AuditLog).where(*where))
    ).scalar_one()
    stmt = (
        _joined_select()
        .where(*where)
        .order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(stmt)).all()
    return [_serialize_row(log, name, account) for log, name, account in rows], int(total)


async def list_operators(db: AsyncSession, tenant_id: UUID) -> list[dict[str, str]]:
    """筛选用的本租户用户。审计页只给管理员，这里直接列姓名和账号。"""
    result = await db.execute(
        select(User.id, User.name, User.account)
        .where(User.tenant_id == tenant_id)
        .order_by(User.name.asc())
    )
    return [
        {"id": str(row.id), "name": row.name, "account": row.account}
        for row in result.all()
    ]


async def export_audit_logs(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID | None = None,
    operation_type: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> bytes:
    """按当前筛选导出 xlsx。超过上限时拒绝，避免一次拉全表。"""
    where = _filters(
        tenant_id=tenant_id,
        user_id=user_id,
        operation_type=operation_type,
        start_date=start_date,
        end_date=end_date,
    )
    total = (
        await db.execute(select(func.count()).select_from(AuditLog).where(*where))
    ).scalar_one()
    if int(total) > EXPORT_MAX_ROWS:
        raise BusinessError(
            f"导出结果超过 {EXPORT_MAX_ROWS} 条，请缩小时间或操作类型范围",
            code="AUDIT_EXPORT_TOO_LARGE",
        )
    stmt = _joined_select().where(*where).order_by(AuditLog.created_at.desc())
    rows = (await db.execute(stmt)).all()
    return _build_workbook([_serialize_row(log, name, account) for log, name, account in rows])


def _filters(
    *,
    tenant_id: UUID,
    user_id: UUID | None,
    operation_type: str | None,
    start_date: date | None,
    end_date: date | None,
) -> list[Any]:
    """租户隔离 + 一年窗口 + 可选筛选。"""
    start, end = resolve_time_window(start_date, end_date)
    conditions: list[Any] = [
        AuditLog.tenant_id == tenant_id,
        AuditLog.created_at >= start,
    ]
    if end is not None:
        conditions.append(AuditLog.created_at < end)
    if user_id is not None:
        conditions.append(AuditLog.user_id == user_id)
    if operation_type:
        conditions.append(AuditLog.operation_type == operation_type)
    return conditions


def _joined_select():
    """日志行带上操作人姓名和账号。"""
    return select(AuditLog, User.name, User.account).outerjoin(
        User, User.id == AuditLog.user_id
    )


def _serialize_row(log: AuditLog, name: str | None, account: str | None) -> dict[str, Any]:
    """API 与导出共用的一行。"""
    return {
        "id": str(log.id),
        "user_id": str(log.user_id) if log.user_id else None,
        "user_name": name,
        "user_account": account,
        "operation_type": log.operation_type,
        "operation_label": operation_label(log.operation_type),
        "target_type": log.target_type,
        "target_id": str(log.target_id) if log.target_id else None,
        "before_value": log.before_value,
        "after_value": log.after_value,
        "summary": summarize_audit(log.after_value, log.error_message),
        "ip": log.ip,
        "ua": log.ua,
        "result": log.result,
        "error_message": log.error_message,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


def _build_workbook(rows: list[dict[str, Any]]) -> bytes:
    """内存中生成 xlsx。"""
    wb = Workbook()
    ws = wb.active
    ws.title = "审计日志"
    ws.append(list(_EXPORT_HEADERS))
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append(
            [
                _format_cn_time(row.get("created_at")),
                row.get("user_name") or "",
                row.get("user_account") or "",
                row.get("operation_label") or "",
                "成功" if row.get("result") == "success" else "失败" if row.get("result") else "",
                row.get("target_type") or "",
                row.get("target_id") or "",
                row.get("ip") or "",
                row.get("summary") or "",
                _json_cell(row.get("before_value")),
                _json_cell(row.get("after_value")),
                row.get("error_message") or "",
            ]
        )
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _cn_day_start(value: date) -> datetime:
    """日历日的北京时间 0 点。"""
    return datetime.combine(value, time.min, tzinfo=_CN_TZ)


def _format_cn_time(value: str | None) -> str:
    """导出时间列用北京时间。"""
    if not value:
        return ""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(_CN_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _json_cell(value: Any) -> str:
    """JSONB 快照写入单元格。空值留空。"""
    if not value:
        return ""
    return json.dumps(value, ensure_ascii=False, default=str)
