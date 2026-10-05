"""后台数据概览聚合。

口径（Asia/Shanghai 自然日/自然月）：
- 只统计 status=active（已确认归档）
- 时间一律用确认归档时点 updated_at，与「今日归档 / 趋势图」同一套
- 本月发票总额 = 本月确认归档发票的含税金额合计（不论开票日期是否在本月）
- 本月合同 = 本月确认归档的合同份数（不论签署日期是否在本月）
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Contract, Invoice, KbChunk, KbDocument, Message, Session, User

DASHBOARD_TZ = ZoneInfo("Asia/Shanghai")
_ARCHIVE_OPS = ("confirm_invoice", "contract.confirm")


def _now() -> datetime:
    """当前上海时区时间。"""
    return datetime.now(DASHBOARD_TZ)


def _utc(dt: datetime) -> datetime:
    """转 UTC，供 timestamptz 比较。"""
    return dt.astimezone(timezone.utc)


def day_window(day: date) -> tuple[datetime, datetime]:
    """某自然日的 [start, end) UTC 窗口。"""
    start = datetime(day.year, day.month, day.day, tzinfo=DASHBOARD_TZ)
    return _utc(start), _utc(start + timedelta(days=1))


def month_window(year: int, month: int) -> tuple[datetime, datetime]:
    """某自然月的 [start, end) UTC 窗口。"""
    start = datetime(year, month, 1, tzinfo=DASHBOARD_TZ)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=DASHBOARD_TZ)
    else:
        end = datetime(year, month + 1, 1, tzinfo=DASHBOARD_TZ)
    return _utc(start), _utc(end)


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    """月份加减，返回 (year, month)。"""
    total = year * 12 + (month - 1) + delta
    return total // 12, total % 12 + 1


def delta_pct(current: float, previous: float) -> float | None:
    """环比百分比；上期为 0 时无法对比则返回 None。"""
    if previous == 0:
        return None
    return round((current - previous) / previous * 100, 1)


def _as_float(value: Decimal | float | int | None) -> float:
    """聚合结果转 float。"""
    if value is None:
        return 0.0
    return float(value)


def _shanghai_day_key(value: datetime | date | None) -> str | None:
    """把 timestamptz / date 归一成 Asia/Shanghai 的 YYYY-MM-DD。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        ts = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return ts.astimezone(DASHBOARD_TZ).date().isoformat()
    return value.isoformat()


def _kpi(
    value: float | int,
    previous: float | int | None,
    *,
    as_int: bool = False,
) -> dict[str, Any]:
    """KPI 卡片数据结构。previous 为 None 时不展示环比。"""
    cur = int(value) if as_int else round(_as_float(value), 2)
    if previous is None:
        return {"value": cur, "previous": None, "delta_pct": None}
    prev = int(previous) if as_int else round(_as_float(previous), 2)
    return {"value": cur, "previous": prev, "delta_pct": delta_pct(float(cur), float(prev))}


class DashboardService:
    """租户级看板查询。财务与管理员可见全量租户数据。"""

    async def overview(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID,
        days: int = 7,
    ) -> dict[str, Any]:
        """组装首页所需全部指标。"""
        days = 7 if days < 7 else 30 if days > 30 else days
        now = _now()
        today = now.date()
        yesterday = today - timedelta(days=1)
        month_start, month_end = month_window(now.year, now.month)
        prev_y, prev_m = shift_month(now.year, now.month, -1)
        prev_start, prev_end = month_window(prev_y, prev_m)

        today_inv = await self._count_archived(db, Invoice, tenant_id, *day_window(today))
        today_con = await self._count_archived(db, Contract, tenant_id, *day_window(today))
        yday_inv = await self._count_archived(db, Invoice, tenant_id, *day_window(yesterday))
        yday_con = await self._count_archived(db, Contract, tenant_id, *day_window(yesterday))

        month_amount = await self._invoice_amount(db, tenant_id, month_start, month_end)
        prev_amount = await self._invoice_amount(db, tenant_id, prev_start, prev_end)
        month_contracts = await self._count_contracts_in_period(db, tenant_id, month_start, month_end)
        prev_contracts = await self._count_contracts_in_period(db, tenant_id, prev_start, prev_end)

        high_risk = await self._count_high_risk(db, tenant_id)

        trend_start_day = today - timedelta(days=days - 1)
        trend = await self._archive_trend(db, tenant_id, trend_start_day, today)
        prev_trend_end = trend_start_day - timedelta(days=1)
        prev_trend_start = prev_trend_end - timedelta(days=days - 1)
        prev_trend = await self._archive_trend(db, tenant_id, prev_trend_start, prev_trend_end)
        trend_total = sum(p["invoices"] + p["contracts"] for p in trend)
        prev_trend_total = sum(p["invoices"] + p["contracts"] for p in prev_trend)

        finance = await self._finance_summary(db, tenant_id, month_start, month_end)
        activity = await self._activity(db, tenant_id, month_start, month_end)
        knowledge = await self._knowledge(db, tenant_id, month_start, month_end)
        risk_items = await self._risk_contracts(db, tenant_id)
        recent = await self._recent_archives(db, tenant_id)

        return {
            "timezone": "Asia/Shanghai",
            "generated_at": now.isoformat(),
            "days": days,
            "kpis": {
                "today_archived": _kpi(today_inv + today_con, yday_inv + yday_con, as_int=True),
                "month_invoice_amount": _kpi(month_amount, prev_amount),
                "month_contracts": _kpi(month_contracts, prev_contracts, as_int=True),
                "high_risk_contracts": _kpi(high_risk, None, as_int=True),
            },
            "trend": {
                "points": trend,
                "delta_pct": delta_pct(float(trend_total), float(prev_trend_total)),
            },
            "risk_contracts": risk_items,
            "recent_archives": recent,
            "activity": activity,
            "finance": finance,
            "knowledge": knowledge,
        }

    async def _count_archived(
        self,
        db: AsyncSession,
        model: type[Invoice] | type[Contract],
        tenant_id: UUID,
        start: datetime,
        end: datetime,
    ) -> int:
        """统计区间内确认归档数量。"""
        stmt = select(func.count()).select_from(model).where(
            model.tenant_id == tenant_id,
            model.status == "active",
            model.updated_at >= start,
            model.updated_at < end,
        )
        return int((await db.execute(stmt)).scalar_one() or 0)

    async def _invoice_amount(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        start: datetime,
        end: datetime,
    ) -> float:
        """区间内确认归档发票的含税合计。"""
        stmt = select(func.coalesce(func.sum(Invoice.amount_incl_tax), 0)).where(
            Invoice.tenant_id == tenant_id,
            Invoice.status == "active",
            Invoice.updated_at >= start,
            Invoice.updated_at < end,
        )
        return _as_float((await db.execute(stmt)).scalar_one())

    async def _count_contracts_in_period(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        start: datetime,
        end: datetime,
    ) -> int:
        """区间内确认归档合同份数。"""
        return await self._count_archived(db, Contract, tenant_id, start, end)

    async def _count_high_risk(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> int:
        """高风险已归档合同。无时间窗时统计存量。"""
        conditions = [
            Contract.tenant_id == tenant_id,
            Contract.status == "active",
            Contract.risk_level == "high",
        ]
        if start is not None and end is not None:
            conditions.extend([Contract.updated_at >= start, Contract.updated_at < end])
        stmt = select(func.count()).select_from(Contract).where(*conditions)
        return int((await db.execute(stmt)).scalar_one() or 0)

    async def _archive_trend(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        start_day: date,
        end_day: date,
    ) -> list[dict[str, Any]]:
        """按自然日拆分发票/合同归档量。"""
        start, _ = day_window(start_day)
        _, end = day_window(end_day)
        inv_map = await self._group_archived_days(db, Invoice, tenant_id, start, end)
        con_map = await self._group_archived_days(db, Contract, tenant_id, start, end)
        points: list[dict[str, Any]] = []
        cursor = start_day
        while cursor <= end_day:
            key = cursor.isoformat()
            points.append(
                {
                    "date": key,
                    "label": f"{cursor.month}/{cursor.day}",
                    "weekday": "周" + "一二三四五六日"[cursor.weekday()],
                    "invoices": inv_map.get(key, 0),
                    "contracts": con_map.get(key, 0),
                }
            )
            cursor += timedelta(days=1)
        return points

    async def _group_archived_days(
        self,
        db: AsyncSession,
        model: type[Invoice] | type[Contract],
        tenant_id: UUID,
        start: datetime,
        end: datetime,
    ) -> dict[str, int]:
        """按上海自然日分组归档计数。

        不用 PG timezone()+cast：驱动可能把日切成 datetime，isoformat 带时间后对不上 'YYYY-MM-DD'。
        """
        stmt = select(model.updated_at).where(
            model.tenant_id == tenant_id,
            model.status == "active",
            model.updated_at >= start,
            model.updated_at < end,
        )
        result: dict[str, int] = {}
        for (ts,) in (await db.execute(stmt)).all():
            key = _shanghai_day_key(ts)
            if key is None:
                continue
            result[key] = result.get(key, 0) + 1
        return result

    async def _finance_summary(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        start: datetime,
        end: datetime,
    ) -> dict[str, float]:
        """本月确认归档发票的金额拆分。"""
        base = [
            Invoice.tenant_id == tenant_id,
            Invoice.status == "active",
            Invoice.updated_at >= start,
            Invoice.updated_at < end,
        ]
        excl = _as_float(
            (await db.execute(select(func.coalesce(func.sum(Invoice.amount_excl_tax), 0)).where(*base))).scalar_one()
        )
        tax = _as_float(
            (await db.execute(select(func.coalesce(func.sum(Invoice.tax_amount), 0)).where(*base))).scalar_one()
        )
        incl = _as_float(
            (await db.execute(select(func.coalesce(func.sum(Invoice.amount_incl_tax), 0)).where(*base))).scalar_one()
        )
        input_tax = _as_float(
            (
                await db.execute(
                    select(func.coalesce(func.sum(Invoice.tax_amount), 0)).where(
                        *base,
                        Invoice.invoice_type == "special",
                    )
                )
            ).scalar_one()
        )
        return {
            "amount_excl_tax": round(excl, 2),
            "tax_amount": round(tax, 2),
            "input_tax": round(input_tax, 2),
            "amount_incl_tax": round(incl, 2),
        }

    async def _activity(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        start: datetime,
        end: datetime,
    ) -> dict[str, int]:
        """本月活跃用户与业务量。"""
        active_users = int(
            (
                await db.execute(
                    select(func.count(func.distinct(Session.user_id))).where(
                        Session.tenant_id == tenant_id,
                        Session.updated_at >= start,
                        Session.updated_at < end,
                    )
                )
            ).scalar_one()
            or 0
        )
        invoices_uploaded = int(
            (
                await db.execute(
                    select(func.count()).select_from(Invoice).where(
                        Invoice.tenant_id == tenant_id,
                        Invoice.status != "deleted",
                        Invoice.created_at >= start,
                        Invoice.created_at < end,
                    )
                )
            ).scalar_one()
            or 0
        )
        contract_reviews = int(
            (
                await db.execute(
                    select(func.count()).select_from(Contract).where(
                        Contract.tenant_id == tenant_id,
                        Contract.status != "deleted",
                        Contract.created_at >= start,
                        Contract.created_at < end,
                    )
                )
            ).scalar_one()
            or 0
        )
        policy_queries = await self._count_policy_retrieves(db, tenant_id, start, end)
        return {
            "active_users": active_users,
            "invoices_uploaded": invoices_uploaded,
            "policy_queries": policy_queries,
            "contract_reviews": contract_reviews,
        }

    async def _knowledge(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        start: datetime,
        end: datetime,
    ) -> dict[str, Any]:
        """知识库就绪情况（租户文档 + 通用文档）。"""
        vis = or_(KbDocument.tenant_id == tenant_id, KbDocument.tenant_id.is_(None))
        doc_total = int(
            (await db.execute(select(func.count()).select_from(KbDocument).where(vis))).scalar_one() or 0
        )
        chunk_total = int(
            (
                await db.execute(
                    select(func.coalesce(func.sum(KbDocument.chunk_count), 0)).where(vis)
                )
            ).scalar_one()
            or 0
        )
        if chunk_total == 0:
            chunk_total = int(
                (
                    await db.execute(
                        select(func.count()).select_from(KbChunk).where(
                            or_(KbChunk.tenant_id == tenant_id, KbChunk.tenant_id.is_(None))
                        )
                    )
                ).scalar_one()
                or 0
            )
        not_ready = int(
            (
                await db.execute(
                    select(func.count()).select_from(KbDocument).where(
                        vis,
                        KbDocument.status.in_(("pending", "indexing", "failed")),
                    )
                )
            ).scalar_one()
            or 0
        )
        chat_retrieves = await self._count_policy_retrieves(db, tenant_id, start, end)
        test_retrieves = await self._count_kb_test_retrieves(db, tenant_id, start, end)
        return {
            "document_count": doc_total,
            "chunk_count": chunk_total,
            "month_retrieves": chat_retrieves + test_retrieves,
            "all_indexed": not_ready == 0 and doc_total > 0,
            "pending_or_failed": not_ready,
        }

    async def _count_policy_retrieves(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        start: datetime,
        end: datetime,
    ) -> int:
        """本月对话中实际执行过 query_policy 的次数（助手消息上的检索痕迹）。"""
        stmt = select(func.count()).select_from(Message).where(
            Message.tenant_id == tenant_id,
            Message.created_at >= start,
            Message.created_at < end,
            Message.tool_calls.is_not(None),
            cast(Message.tool_calls, String).ilike("%query_policy%"),
        )
        return int((await db.execute(stmt)).scalar_one() or 0)

    async def _count_kb_test_retrieves(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        start: datetime,
        end: datetime,
    ) -> int:
        """本月后台「检索测试」次数。"""
        stmt = select(func.count()).select_from(AuditLog).where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.operation_type == "kb.test_retrieve",
            AuditLog.created_at >= start,
            AuditLog.created_at < end,
        )
        return int((await db.execute(stmt)).scalar_one() or 0)

    async def _risk_contracts(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """高/中风险合同列表，金额从高到低。"""
        stmt = (
            select(Contract)
            .where(
                Contract.tenant_id == tenant_id,
                Contract.status == "active",
                Contract.risk_level.in_(("high", "medium")),
            )
            .order_by(
                Contract.risk_level.asc(),
                Contract.amount.desc(),
                Contract.updated_at.desc(),
            )
            .limit(limit)
        )
        rows = (await db.execute(stmt)).scalars().all()
        items: list[dict[str, Any]] = []
        for row in rows:
            title = row.contract_name or row.contract_no or "未命名合同"
            items.append(
                {
                    "id": str(row.id),
                    "title": title,
                    "amount": _as_float(row.amount),
                    "risk_level": row.risk_level,
                }
            )
        return items

    async def _recent_archives(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        """最近确认归档记录（审计日志）。"""
        stmt = (
            select(AuditLog, User.name)
            .outerjoin(User, User.id == AuditLog.user_id)
            .where(
                AuditLog.tenant_id == tenant_id,
                AuditLog.operation_type.in_(_ARCHIVE_OPS),
                AuditLog.result == "success",
            )
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        rows = (await db.execute(stmt)).all()
        items: list[dict[str, Any]] = []
        for log, operator in rows:
            after = log.after_value if isinstance(log.after_value, dict) else {}
            if log.target_type == "invoice":
                title = after.get("invoice_title") or after.get("invoice_number") or "发票归档"
                amount = after.get("amount_incl_tax")
                kind = "invoice"
            else:
                title = after.get("contract_name") or after.get("contract_no") or "合同归档"
                amount = after.get("amount")
                kind = "contract"
            items.append(
                {
                    "id": str(log.target_id) if log.target_id else str(log.id),
                    "kind": kind,
                    "title": str(title),
                    "amount": _as_float(amount) if amount is not None else None,
                    "operator_name": operator,
                    "created_at": log.created_at.isoformat() if log.created_at else None,
                }
            )
        return items


dashboard_service = DashboardService()
