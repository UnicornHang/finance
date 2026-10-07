"""合同审查报告 PDF / zip 纯生成器（无 DB / Celery）。

字体策略：
  优先嵌入系统清晰中文字体（微软雅黑 / 黑体 / Noto），保证 PDF 内嵌字形更清晰；
  找不到时再回退 reportlab CID `STSong-Light`。

审查摘要支持常见 Markdown：标题、加粗、空行分段，不再原样输出 `####` / `**`。
内容规格见设计 §5.2（方案 A）：封面信息 + 审查摘要 + 违规列表。
"""

from __future__ import annotations

import logging
import re
import zipfile
from dataclasses import dataclass, field
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Sequence

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

logger = logging.getLogger(__name__)

_CID_FALLBACK = "STSong-Light"
_FONT_FAMILY = "ExportCN"
_FONT_NORMAL = "ExportCN"
_FONT_BOLD = "ExportCN-Bold"

# zip / 文件系统不安全字符
_UNSAFE_FILENAME_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')
# Markdown 标题
_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
# 加粗：***x*** 或 **x**（先匹配三星号）
_MD_BOLD_RE = re.compile(r"\*\*\*(.+?)\*\*\*|\*\*(.+?)\*\*")

# Windows / Linux 常见中文字体（常规 + 粗体）
_FONT_CANDIDATES: list[tuple[Path, int | None, Path | None, int | None]] = [
    # (regular_path, regular_subfont, bold_path, bold_subfont)
    (
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        0,
        Path(r"C:\Windows\Fonts\msyhbd.ttc"),
        0,
    ),
    (Path(r"C:\Windows\Fonts\simhei.ttf"), None, None, None),
    (Path(r"C:\Windows\Fonts\simsun.ttc"), 0, None, None),
    (
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        0,
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
        0,
    ),
    (
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        0,
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"),
        0,
    ),
]

_FONTS_READY = False
_ACTIVE_FONT = _CID_FALLBACK
_ACTIVE_BOLD = _CID_FALLBACK


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


def _register_ttc_or_ttf(name: str, path: Path, subfont_index: int | None) -> bool:
    """注册单个 TTF/TTC 字体；失败返回 False。"""
    try:
        if subfont_index is None:
            pdfmetrics.registerFont(TTFont(name, str(path)))
        else:
            pdfmetrics.registerFont(TTFont(name, str(path), subfontIndex=subfont_index))
        return True
    except Exception:
        logger.debug("register font failed name=%s path=%s", name, path, exc_info=True)
        return False


def _ensure_fonts() -> tuple[str, str]:
    """返回 (正文字体名, 粗体字体名)；优先嵌入系统字体。"""
    global _FONTS_READY, _ACTIVE_FONT, _ACTIVE_BOLD
    if _FONTS_READY:
        return _ACTIVE_FONT, _ACTIVE_BOLD

    for regular, reg_idx, bold, bold_idx in _FONT_CANDIDATES:
        if not regular.is_file():
            continue
        if not _register_ttc_or_ttf(_FONT_NORMAL, regular, reg_idx):
            continue
        bold_name = _FONT_NORMAL
        if bold is not None and bold.is_file():
            if _register_ttc_or_ttf(_FONT_BOLD, bold, bold_idx):
                bold_name = _FONT_BOLD
        try:
            pdfmetrics.registerFontFamily(
                _FONT_FAMILY,
                normal=_FONT_NORMAL,
                bold=bold_name,
            )
        except Exception:
            logger.debug("registerFontFamily failed", exc_info=True)
        _ACTIVE_FONT = _FONT_NORMAL
        _ACTIVE_BOLD = bold_name
        _FONTS_READY = True
        logger.info("export pdf font embedded: %s (bold=%s)", regular, bold_name)
        return _ACTIVE_FONT, _ACTIVE_BOLD

    # 回退 CID（依赖阅读器本地字形，清晰度一般）
    pdfmetrics.registerFont(UnicodeCIDFont(_CID_FALLBACK))
    _ACTIVE_FONT = _CID_FALLBACK
    _ACTIVE_BOLD = _CID_FALLBACK
    _FONTS_READY = True
    logger.warning("export pdf fallback CID font=%s", _CID_FALLBACK)
    return _ACTIVE_FONT, _ACTIVE_BOLD


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


def _inline_markdown_to_xml(text: str) -> str:
    """把行内 **加粗** / ***加粗*** 转为 reportlab `<b>`，并转义其余文本。"""
    parts: list[str] = []
    pos = 0
    for match in _MD_BOLD_RE.finditer(text):
        parts.append(_escape_xml(text[pos : match.start()]))
        bold = match.group(1) or match.group(2) or ""
        parts.append(f"<b>{_escape_xml(bold)}</b>")
        pos = match.end()
    parts.append(_escape_xml(text[pos:]))
    return "".join(parts)


def _summary_flowables(
    summary: str,
    *,
    body_style: ParagraphStyle,
    h3_style: ParagraphStyle,
    h4_style: ParagraphStyle,
) -> list[object]:
    """将审查摘要 Markdown 拆成可读段落（标题 / 加粗 / 分段）。"""
    text = (summary or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return [Paragraph("暂无审查结果", body_style)]

    flowables: list[object] = []
    for raw_line in text.split("\n"):
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            flowables.append(Spacer(1, 2.2 * mm))
            continue

        heading = _MD_HEADING_RE.match(stripped)
        if heading:
            level = len(heading.group(1))
            content = _inline_markdown_to_xml(heading.group(2).strip())
            style = h3_style if level <= 3 else h4_style
            flowables.append(Paragraph(content, style))
            continue

        # 去掉行首无序列表标记的多余空格，保留「1.」「-」等可读前缀
        flowables.append(Paragraph(_inline_markdown_to_xml(stripped), body_style))

    return flowables


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
    font, bold_font = _ensure_fonts()
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
        fontName=bold_font,
        fontSize=18,
        leading=26,
        spaceAfter=10,
        alignment=1,  # center
        textColor=colors.HexColor("#0f172a"),
    )
    h2_style = ParagraphStyle(
        "ExportH2",
        parent=styles["Heading2"],
        fontName=bold_font,
        fontSize=13,
        leading=20,
        spaceBefore=12,
        spaceAfter=8,
        textColor=colors.HexColor("#0f172a"),
    )
    h3_style = ParagraphStyle(
        "ExportH3",
        parent=styles["Heading3"],
        fontName=bold_font,
        fontSize=12,
        leading=19,
        spaceBefore=8,
        spaceAfter=4,
        textColor=colors.HexColor("#1e293b"),
    )
    h4_style = ParagraphStyle(
        "ExportH4",
        parent=styles["Heading4"],
        fontName=bold_font,
        fontSize=11,
        leading=18,
        spaceBefore=6,
        spaceAfter=3,
        textColor=colors.HexColor("#334155"),
    )
    body_style = ParagraphStyle(
        "ExportBody",
        parent=styles["Normal"],
        fontName=font,
        fontSize=10.5,
        leading=18,
        spaceAfter=2,
        textColor=colors.HexColor("#1e293b"),
    )
    cell_style = ParagraphStyle(
        "ExportCell",
        parent=styles["Normal"],
        fontName=font,
        fontSize=10,
        leading=15,
        textColor=colors.HexColor("#1e293b"),
    )
    cell_label_style = ParagraphStyle(
        "ExportCellLabel",
        parent=cell_style,
        fontName=bold_font,
    )

    story: list[object] = []
    story.append(Paragraph("合同审查报告", title_style))
    story.append(Spacer(1, 3 * mm))

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
        [
            Paragraph(_escape_xml(k), cell_label_style),
            Paragraph(_escape_xml(v), cell_style),
        ]
        for k, v in cover_rows
    ]
    cover_table = Table(cover_data, colWidths=[32 * mm, 140 * mm])
    cover_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(cover_table)

    # 审查摘要（Markdown → 结构化段落）
    story.append(Paragraph("审查摘要", h2_style))
    story.extend(
        _summary_flowables(
            contract.summary or "",
            body_style=body_style,
            h3_style=h3_style,
            h4_style=h4_style,
        )
    )

    # 违规列表
    story.append(Paragraph("违规列表", h2_style))
    header = [
        Paragraph("条款", cell_label_style),
        Paragraph("问题", cell_label_style),
        Paragraph("严重程度", cell_label_style),
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

    viol_table = Table(table_data, colWidths=[45 * mm, 95 * mm, 32 * mm])
    viol_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
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
