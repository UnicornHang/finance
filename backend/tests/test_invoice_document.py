"""PDF / Word 正文抽取。

合同审查曾经把 PDF 源码（stream、FlateDecode）当成正文送给模型。
这里锁住：压缩流里的文字要抽出来，源码标记不能出现在送审文本里。
"""

from __future__ import annotations

import zipfile
import zlib
from io import BytesIO

import pytest

from app.services.invoice_document import (
    DocumentUnreadableError,
    _extract_file_text,
    _media_content,
    _normalize_document_text,
    _prepare_document,
)


def _text_pdf(text: str, *, compress: bool) -> bytes:
    """造一份只有一行文字的 PDF。compress=True 时正文放在 FlateDecode 流里。"""
    safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({safe}) Tj ET".encode("ascii")
    if compress:
        data = zlib.compress(stream)
        contents = f"<< /Filter /FlateDecode /Length {len(data)} >>\nstream\n".encode()
        contents += data + b"\nendstream"
    else:
        contents = f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"

    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Count 1 /Kids [3 0 R] >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n",
        b"4 0 obj\n" + contents + b"\nendobj\n",
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
    ]
    header = b"%PDF-1.4\n"
    cursor = len(header)
    offsets = [0]
    body = b""
    for part in objects:
        offsets.append(cursor)
        body += part
        cursor += len(part)
    xref = [f"xref\n0 {len(offsets)}\n".encode(), b"0000000000 65535 f \n"]
    xref.extend(f"{off:010d} 00000 n \n".encode() for off in offsets[1:])
    trailer = (
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{cursor}\n%%EOF\n".encode()
    )
    return header + body + b"".join(xref) + trailer


def _syntax_only_pdf() -> bytes:
    """只有对象结构、没有可读正文的 PDF 源码。"""
    return b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R /Filter /FlateDecode >>
endobj
2 0 obj
<< /Type /Pages /Count 1 /Kids [3 0 R] /MediaBox [0 0 595 842] >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842]
/Resources << /Font << /F1 << /BaseFont /Calibri /Encoding /Identity-H >> >> >>
/Filter /FlateDecode /Length 8 >>
stream
(Microsoft Word Calibri Identity Helvetica ProcSet Resources)
endstream
endobj
%%EOF
"""


def _docx_bytes(text: str) -> bytes:
    """最小 docx：正文放在 word/document.xml。"""
    xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body>
</w:document>"""
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", xml)
    return buf.getvalue()


def _assert_no_pdf_source(value: str) -> None:
    lowered = value.lower()
    assert "endstream" not in lowered
    assert "flatedecode" not in lowered
    assert "/mediabox" not in lowered


def test_flate_pdf_extracts_contract_text() -> None:
    """压缩流里的合同句子要被解开，不能把 FlateDecode 本身交给模型。"""
    sentence = "The borrower shall repay the loan amount on the due date"
    pdf = _text_pdf(sentence, compress=True)
    images, text = _prepare_document(pdf, "application/pdf", "借款合同.pdf")
    assert images == []
    assert "borrower" in text
    assert "loan amount" in text
    _assert_no_pdf_source(text)


def test_pdf_syntax_is_not_sent_as_body() -> None:
    """源码片段不能再被当成合同正文。"""
    pdf = _syntax_only_pdf()
    try:
        content = _media_content(pdf, "application/pdf", "借款合同.pdf", "请审查这份合同")
    except DocumentUnreadableError:
        return
    texts = "\n".join(part.get("text", "") for part in content if part.get("type") == "text")
    _assert_no_pdf_source(texts)
    assert "Microsoft Word Calibri" not in texts


def test_docx_extracts_contract_clauses() -> None:
    clause = "借款合同甲方应于签订后向乙方支付借款金额"
    text = _extract_file_text(_docx_bytes(clause), "application/octet-stream", "借款合同.docx")
    assert clause in text


def test_legacy_doc_extracts_chinese_runs() -> None:
    clause = "借款合同甲方应于签订后支付借款金额"
    blob = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 32 + clause.encode("utf-16le")
    text = _extract_file_text(blob, "application/msword", "借款合同.doc")
    assert "借款合同" in text
    assert "借款金额" in text


def test_spaced_cjk_and_print_footer_become_contract_text() -> None:
    """浏览器打印的 PDF 常把标题拆成「投 资」，并带上 file:// 页脚。"""
    raw = (
        "投 资 合 作 协 议\n"
        "甲 方 （ 投 资 方 ） ： 示例公司\n"
        "file:///C:/tmp/a.html 1/2\n"
        "2026/9/27 12:04 财务合同批量导出 PDF\n"
        "甲方出资人民币壹万元。"
    )
    text = _normalize_document_text(raw + "\n第 一 条  投 资 金 额\n第一条 投资金额")
    assert "投资合作协议" in text
    assert "甲方（投资方）" in text
    assert "示例公司" in text
    assert "第一条 投资金额" in text
    assert "甲方出资人民币壹万元。" in text
    assert "file://" not in text
    assert "导出" not in text


def test_media_content_keeps_body_in_single_text_part() -> None:
    """正文必须和指令在同一条文本里，避免接口只读第一条时丢掉合同。"""
    sentence = "The borrower shall repay the loan amount on the due date"
    pdf = _text_pdf(sentence, compress=True)
    content = _media_content(pdf, "application/pdf", "借款合同.pdf", "请审查这份合同")
    texts = [part.get("text", "") for part in content if part.get("type") == "text"]
    assert len(texts) == 1
    assert "borrower" in texts[0]
    assert "请审查这份合同" in texts[0]


def test_text_only_content_flattens_to_string() -> None:
    """纯文本合同应送给模型字符串，而不是单元素 content 数组。"""
    from app.services.invoice_document import _as_llm_message_content

    sentence = "The borrower shall repay the loan amount on the due date"
    pdf = _text_pdf(sentence, compress=True)
    parts = _media_content(pdf, "application/pdf", "借款合同.pdf", "请审查")
    flat = _as_llm_message_content(parts)
    assert isinstance(flat, str)
    assert "borrower" in flat
    assert "系统已完成文字提取" in flat


def test_extract_contract_overview_from_chinese_body() -> None:
    """侧栏字段从正文标签抓取，不依赖模型再抽一遍。"""
    from app.services.invoice_document import _extract_contract_overview

    text = (
        "股权转让协议\n"
        "甲方（转让方）：张明\n"
        "乙方（受让方）：深圳市星辰科技有限公司\n"
        "人民币叁佰万元整（¥3,000,000.00）。\n"
        "日期：2026年9月27日\n"
    )
    overview = _extract_contract_overview(text)
    assert overview["party_a"] == "张明"
    assert overview["party_b"] == "深圳市星辰科技有限公司"
    assert overview["amount"] == 3000000.0
    assert overview["sign_date"] == "2026-09-27"


def test_unreadable_bytes_do_not_call_model_with_placeholder() -> None:
    """既不是 PDF 也不是 Word 的二进制，应明确失败，而不是送一句“未能抽出文字”。"""
    with pytest.raises(DocumentUnreadableError):
        _media_content(b"\x00\x01\x02\x03not-a-document", "application/octet-stream", "a.bin", "看一下")
