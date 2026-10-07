"""导出任务指纹：筛选条件规范化与 SHA-256 摘要。"""

import hashlib
import json
from datetime import date
from typing import Any


def normalize_invoice_filters(
    *,
    invoice_type: str | None = None,
    search: str | None = None,
    status_filter: str | None = "active",
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, Any]:
    """将发票导出筛选参数规范为固定键序、可序列化的字典。"""
    return {
        "resource_type": "invoice",
        "invoice_type": invoice_type or None,
        "search": (search or "").strip(),
        "status_filter": status_filter or "active",
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
    }


def normalize_contract_filters(
    *,
    search: str | None = None,
    risk_level: str | None = None,
) -> dict[str, Any]:
    """将合同导出筛选参数规范为固定键序、可序列化的字典。"""
    return {
        "resource_type": "contract",
        "search": (search or "").strip(),
        "risk_level": risk_level or None,
    }


def export_fingerprint(normalized: dict[str, Any]) -> str:
    """对已规范化的筛选字典计算稳定 SHA-256 十六进制指纹。"""
    payload = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
