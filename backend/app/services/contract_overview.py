"""从合同正文提取侧栏概览字段。"""

from __future__ import annotations

import re


def extract_contract_overview(text: str) -> dict:
    """提取合同双方、金额和签署日期；无法确定的字段保持为空。"""
    if not text.strip():
        return {}
    overview: dict = {}
    party_a = _match_labeled_value(
        text,
        ("甲方", "转让方", "出卖人", "卖方"),
    )
    party_b = _match_labeled_value(
        text,
        ("乙方", "受让方", "买受人", "买方"),
    )
    if party_a:
        overview["party_a"] = party_a
    if party_b:
        overview["party_b"] = party_b
    amount = _parse_money_amount(text)
    if amount is not None:
        overview["amount"] = amount
    sign_date = _parse_sign_date(text)
    if sign_date:
        overview["sign_date"] = sign_date
    return overview


def _match_labeled_value(text: str, labels: tuple[str, ...]) -> str | None:
    """按“标签：值”抓取第一处非空行尾内容。"""
    for label in labels:
        pattern = rf"{re.escape(label)}\s*[（(][^）)]*[）)]?\s*[:：]\s*(.+)$"
        matched = re.search(pattern, text, re.MULTILINE)
        if matched and matched.group(1).strip():
            return matched.group(1).strip()
        pattern = rf"{re.escape(label)}\s*[:：]\s*(.+)$"
        matched = re.search(pattern, text, re.MULTILINE)
        if matched and matched.group(1).strip():
            return matched.group(1).strip()
    return None


def _parse_money_amount(text: str) -> float | None:
    """优先提取带人民币符号或金额标签的数字。"""
    patterns = (
        r"[¥￥]\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)",
        r"(?:人民币|金额|价款|转让价)[^\n]{0,24}?"
        r"([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)\s*元",
    )
    for pattern in patterns:
        matched = re.search(pattern, text)
        if not matched:
            continue
        try:
            return float(matched.group(1).replace(",", ""))
        except ValueError:
            continue
    return None


def _parse_sign_date(text: str) -> str | None:
    """提取签署日期并规范为 YYYY-MM-DD。"""
    matched = re.search(
        r"(?:日期|签署日期|签订日期|签约日期)\s*[:：]?\s*"
        r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日",
        text,
    )
    if not matched:
        matched = re.search(
            r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日",
            text,
        )
    if not matched:
        return None
    year, month, day = matched.groups()
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
