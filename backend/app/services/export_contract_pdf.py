"""合同审查报告 PDF / zip 纯生成器（无 DB / Celery）。

中文字体策略（YAGNI）：
  使用 reportlab 自带的 CID 字体 `STSong-Light`
  （`UnicodeCIDFont`），不在仓库内 vendoring Noto/思源等大体积字体文件。
  CID 字体由 PDF 阅读器侧解析，适合中文正文；无需 `backend/app/assets/fonts/`。
  若未来需嵌入字体以保证所有阅读器一致显示，可再改为注册 OTF/TTF。

内容规格见设计 §5.2（方案 A）：封面信息 + 审查摘要 + 违规列表。
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from decimal import Decimal
from io import BytesIO
from typing import Sequence

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# 宋体 CID：Adobe 亚洲字体集，reportlab 内置映射，无需本地字体文件
_CID_FONT_NAME = "STSong-Light"
_FONT_REGISTERED = False

# zip / 文件系统不安全字符
_UNSAFE_FILENAME_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


@dataclass(frozen=True, slots=True)
class ViolationItem:
    """单条违规项（条款 / 问题 / 严重程度）。"""

    clause: str | None = None
    issue: str | None = None
    severity: str | None = None  # high / medium / low 或已译中文


@dataclass(frozen=True, slots=True)
class ContractView:
    """生成审查报告所需的合同视图（已由上游拼好展示字段）。"""

    contract_name: str | None = None
    contract_no: str | None = None
    party_a: str | None = None
    party_b: str | None = None
    sign_date: str | None = None
    effective_start: str | None = None
    amount: Decimal | float | int | None = None
    risk_level: str | None = None
    status: str | None = None
    exported_at: str | None = None
    summary: str | None = None
    violations: Sequence[ViolationItem] = field(default_factory=tuple)


def _ensure_cid_font() -> str:
    """注册并返回中文 CID 字体名（进程内只注册一次）。"""
    global _FONT_REGISTERED
    if not _FONT_REGISTERED:
        pdfmetrics.registerFont(UnicodeCIDFont(_CID_FONT_NAME))
        _FONT_REGISTERED = True
    return _CID_FONT_NAME


def _severity_label(raw: str | None) -> str:
    """将严重程度规范为中文高/中/低。"""
    if not raw:
        return ""
    key = raw.strip().lower()
    mapping = {
        "high": "高",
        "medium": "中",
        "low": "低",
        "高": "高",
        "中": "中",
        "低": "低",
    }
    return mapping.get(key, raw)


def _risk_label(raw: str | None) -> str:
    """风险等级展示文案。"""
    if not raw:
        return ""
    key = raw.strip().lower()
    mapping = {
        "high": "高",
        "medium": "中",
        "low": "低",
        "高": "高",
        "中": "中",
        "低": "低",
    }
    return mapping.get(key, raw)


def _status_label(raw: str | None) -> str:
    """合同状态展示文案。"""
    if not raw:
        return ""
    mapping = {
        "active": "已归档",
        "pending_review": "待确认",
        "deleted": "已删除",
    }
    return mapping.get(raw.strip().lower(), raw)


def _escape_xml(text: str) -> str:
    """Paragraph 用的简单 XML 转义。"""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _fmt_amount(value: Decimal | float | int | None) -> str:
    """金额格式化为两位小数；空为破折号。"""
    if value is None:
        return "—"
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    return f"{float(value):.2f}"


def _dash(value: str | None) -> str:
    """空串显示为破折号。"""
    if value is None or str(value).strip() == "":
        return "—"
    return str(value)


def safe_pdf_filename(name: str, short_id: str) -> str:
    """生成 zip 内 PDF 文件名：`{名称或编号}-{短id}.pdf`，替换非法字符。"""
    base = (name or "").strip() or "contract"
    # 调用方若已带 .pdf，去掉以免变成 name.pdf-id.pdf
    if base.lower().endswith(".pdf"):
        base = base[:-4]
    cleaned = _UNSAFE_FILENAME_RE.sub("_", base).strip(" ._") or "contract"
    # 过长截断，避免 zip 内路径异常
    if len(cleaned) > 80:
        cleaned = cleaned[:80].rstrip(" ._") or "contract"
    sid = (short_id or "").strip() or "00000000"
    sid = _UNSAFE_FILENAME_RE.sub("_", sid)
    return f"{cleaned}-{sid}.pdf"


def build_contract_report_pdf(contract: ContractView) -> bytes:
    """按方案 A 生成单份合同审查报告 PDF 字节。

    无审查结果时仍出 PDF：摘要标明「暂无审查结果」，违规表为空。
    """
    font = _ensure_cid_font()
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=_dash(contract.contract_name),
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ExportTitle",
        parent=styles["Heading1"],
        fontName=font,
        fontSize=16,
        leading=22,
        spaceAfter=8,
    )
    h2_style = ParagraphStyle(
        "ExportH2",
        parent=styles["Heading2"],
        fontName=font,
        fontSize=12,
        leading=18,
        spaceBefore=10,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "ExportBody",
        parent=styles["Normal"],
        fontName=font,
        fontSize=10,
        leading=15,
    )
    cell_style = ParagraphStyle(
        "ExportCell",
        parent=styles["Normal"],
        fontName=font,
        fontSize=9,
        leading=13,
    )

    story: list[object] = []
    story.append(Paragraph("合同审查报告", title_style))
    story.append(Spacer(1, 4 * mm))

    # 封面信息
    cover_rows = [
        ["合同名称", _dash(contract.contract_name)],
        ["合同编号", _dash(contract.contract_no)],
        ["甲方", _dash(contract.party_a)],
        ["乙方", _dash(contract.party_b)],
        ["签订日期", _dash(contract.sign_date)],
        ["生效日期", _dash(contract.effective_start)],
        ["金额", _fmt_amount(contract.amount)],
        ["风险等级", _dash(_risk_label(contract.risk_level))],
        ["状态", _dash(_status_label(contract.status))],
        ["导出时间", _dash(contract.exported_at)],
    ]
    cover_data = [
        [Paragraph(_escape_xml(k), cell_style), Paragraph(_escape_xml(v), cell_style)]
        for k, v in cover_rows
    ]
    cover_table = Table(cover_data, colWidths=[32 * mm, 140 * mm])
    cover_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font),
                ("BACKGROUND", (0, 0), (0, -1), colors.Color(0.93, 0.93, 0.93)),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(cover_table)

    # 审查摘要
    story.append(Paragraph("审查摘要", h2_style))
    summary_text = (contract.summary or "").strip()
    if not summary_text:
        summary_text = "暂无审查结果"
    story.append(Paragraph(_escape_xml(summary_text).replace("\n", "<br/>"), body_style))

    # 违规列表
    story.append(Paragraph("违规列表", h2_style))
    header = [
        Paragraph("条款", cell_style),
        Paragraph("问题", cell_style),
        Paragraph("严重程度", cell_style),
    ]
    table_data: list[list[object]] = [header]
    for item in contract.violations:
        table_data.append(
            [
                Paragraph(_escape_xml(_dash(item.clause)), cell_style),
                Paragraph(_escape_xml(_dash(item.issue)), cell_style),
                Paragraph(_escape_xml(_dash(_severity_label(item.severity))), cell_style),
            ]
        )
    # 无违规时仅表头（设计：违规表为空）

    viol_table = Table(table_data, colWidths=[45 * mm, 95 * mm, 32 * mm])
    viol_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font),
                ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.88, 0.88, 0.88)),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(viol_table)

    doc.build(story)
    return buf.getvalue()


def build_contract_reports_zip(items: Sequence[tuple[str, bytes]]) -> bytes:
    """将多份 `(zip内文件名, pdf字节)` 打成一个 zip；允许空列表（空 zip）。"""
    buf = BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        used: set[str] = set()
        for filename, pdf_bytes in items:
            name = filename or "report.pdf"
            # 防 zip 内重名：追加计数后缀
            if name in used:
                stem, _, ext = name.rpartition(".")
                base = stem or name
                suffix = ext or "pdf"
                n = 2
                candidate = f"{base}-{n}.{suffix}"
                while candidate in used:
                    n += 1
                    candidate = f"{base}-{n}.{suffix}"
                name = candidate
            used.add(name)
            zf.writestr(name, pdf_bytes)
    return buf.getvalue()
