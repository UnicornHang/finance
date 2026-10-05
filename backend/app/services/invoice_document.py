"""把上传文件变成模型能看的内容。

图片直接作为 image_url。PDF / Word 先抽正文；抽不到时再发页面图。
绝不把 PDF 源码（stream、FlateDecode、/Font）当成合同或发票正文。
分类、识别和文件对话共用这里的结果。
"""

from __future__ import annotations

import base64
import logging
import re
import zipfile
from io import BytesIO

try:
    from pypdf import PdfReader
except ImportError:  # 依赖未安装时改走 PDFium，仍不回退到源码拼接
    PdfReader = None  # type: ignore[misc, assignment]

try:
    import pypdfium2 as pdfium
except ImportError:
    pdfium = None  # type: ignore[assignment]

from app.services.contract_overview import (
    extract_contract_overview as _extract_contract_overview,
)
from app.services.docx_text import extract_docx_text

logger = logging.getLogger(__name__)

# 按图片块发送的 MIME（其余文件先抽文字，抽不到再发页面图）
_IMAGE_MIME = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/gif",
}

# Word 的 word/media 里只取这些图片
_EMBEDDED_EXT_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

# 扫描件通常一页一张图。文字抽空时最多渲染前几页，避免把整本文件塞进上下文
_MAX_EMBEDDED_IMAGES = 3
_MAX_RENDER_PAGES = 6
# 小于此大小的 JPEG 多半是印章或二维码，有大图时跳过
_MIN_EMBEDDED_IMAGE_BYTES = 10_000
_TEXT_LIMIT = 12_000

# 二进制 .doc（OLE）文件头
_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

# 这些词出现在正文里，说明抽到的是 PDF 结构而不是合同
_PDF_SOURCE_MARKERS = (
    "endstream",
    "endobj",
    "flatedecode",
    "/mediabox",
    "%pdf",
    "/filter",
)

# PDF 结构里的英文单词，不能单独当成自然语言
_PDF_NOISE_WORDS = {
    "endstream",
    "endobj",
    "stream",
    "layout",
    "placement",
    "block",
    "bbox",
    "producer",
    "microsoft",
    "word",
    "creator",
    "obj",
}

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class DocumentUnreadableError(ValueError):
    """PDF 或 Word 里没有可交给模型的正文，也没有可看的页面图。"""


def _guess_mime(file_bytes: bytes, content_type: str | None, filename: str | None) -> str:
    """推断 MIME：优先图片类型和魔数，再看文件名。"""
    if content_type and content_type.split(";")[0].strip().lower() in _IMAGE_MIME:
        return content_type.split(";")[0].strip().lower()
    if content_type and content_type.startswith("image/"):
        return content_type.split(";")[0].strip().lower()

    if file_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if file_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WEBP":
        return "image/webp"
    if file_bytes[:4] == b"%PDF":
        return "application/pdf"
    if file_bytes[:2] == b"PK" and _zip_has_docx(file_bytes):
        return _DOCX_MIME
    if file_bytes.startswith(_OLE_MAGIC):
        name = (filename or "").lower()
        declared = (content_type or "").split(";")[0].strip().lower()
        if name.endswith(".doc") or declared == "application/msword":
            return "application/msword"

    name = (filename or "").lower()
    if name.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if name.endswith(".png"):
        return "image/png"
    if name.endswith(".webp"):
        return "image/webp"
    if name.endswith(".pdf"):
        return "application/pdf"
    if name.endswith(".docx"):
        return _DOCX_MIME
    if name.endswith(".doc"):
        return "application/msword"
    return content_type or "application/octet-stream"


def _zip_has_docx(file_bytes: bytes) -> bool:
    """PK 头不一定是 Word，要确认包里有 document.xml。"""
    try:
        with zipfile.ZipFile(BytesIO(file_bytes)) as zf:
            return "word/document.xml" in zf.namelist()
    except (zipfile.BadZipFile, OSError):
        return False


def _docx_text(file_bytes: bytes) -> str:
    """从 DOCX 抽正文并保留可供结构切分使用的标题层级。"""
    return extract_docx_text(file_bytes)


def _doc_text(file_bytes: bytes) -> str:
    """从二进制 .doc 里回收连续汉字。

    旧版 Word 把段落存在 OLE 流的 UTF-16LE 里，没有 document.xml。
    只保留足够长的汉字串，避免把扇区字节误当成正文。
    """
    if not file_bytes.startswith(_OLE_MAGIC):
        return ""
    decoded = file_bytes.decode("utf-16le", errors="ignore")
    seen: set[str] = set()
    ordered: list[str] = []
    for piece in re.findall(r"[\u4e00-\u9fff]{8,}", decoded):
        if piece in seen:
            continue
        seen.add(piece)
        ordered.append(piece)
    return "\n".join(ordered)


def _is_readable_char(ch: str) -> bool:
    """汉字、中文标点和常见 ASCII 算可读字符。"""
    if "\u4e00" <= ch <= "\u9fff":
        return True
    if "\u3000" <= ch <= "\u303f" or "\uff00" <= ch <= "\uffef":
        return True
    if ch.isspace():
        return True
    return ch.isascii() and (ch.isalnum() or ch in ".,:/-_()%¥@#&+;!?'\"")


def _is_document_text(value: str) -> bool:
    """二进制被当成字符串时不算正文。"""
    stripped = value.strip()
    if len(stripped) < 2:
        return False
    allowed = sum(1 for ch in stripped if _is_readable_char(ch))
    return allowed / len(stripped) >= 0.8


def _has_readable_body(value: str) -> bool:
    """有汉字或足够的自然语言，才算抽出了正文。PDF 元数据不算。"""
    if sum(1 for ch in value if "\u4e00" <= ch <= "\u9fff") >= 4:
        return True
    words = [
        word
        for word in re.findall(r"[A-Za-z]{3,}", value)
        if word.lower() not in _PDF_NOISE_WORDS
    ]
    return len(words) >= 8


def _looks_like_pdf_source(value: str) -> bool:
    """抽字结果里夹着对象和压缩过滤器，说明这是源码不是合同。"""
    lowered = value.lower()
    hits = sum(1 for marker in _PDF_SOURCE_MARKERS if marker in lowered)
    return hits >= 2


# 单个汉字或中文标点。用来把「投 资 合 作」粘回「投资合作」
_CJK_OR_PUNCT = re.compile(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]")
# 浏览器「打印为 PDF」留在页脚的时间戳和本地路径，不是合同条款
_PRINT_FOOTER_LINE = re.compile(
    r"^(?:file://\S+.*|\d{4}/\d{1,2}/\d{1,2}\s+\d{1,2}:\d{2}.*导出\s*PDF.*)$",
    re.IGNORECASE,
)


def _collapse_glyph_spaces(line: str) -> str:
    """只粘合被拆开的单字，词语之间的空格保留。

    「投 资 合 作」里每个词只有一个字，应合成「投资合作」。
    「第一条 投资金额」两边都是词，中间空格要留下。
    """
    tokens = [token for token in re.split(r"[ \t]+", line.strip()) if token]
    words: list[str] = []
    glyphs = ""
    for token in tokens:
        if len(token) == 1 and _CJK_OR_PUNCT.fullmatch(token):
            glyphs += token
            continue
        if glyphs:
            words.append(glyphs)
            glyphs = ""
        words.append(token)
    if glyphs:
        words.append(glyphs)
    return " ".join(words)


def _normalize_document_text(value: str) -> str:
    """整理抽出的正文，让模型读到连续条款而不是排版碎片。

    有的 PDF 把每个汉字单独定位，抽出来会变成「投 资 合 作」。
    浏览器打印还会在页脚留下 file:// 和「导出 PDF」。这些都不是条款。
    """
    if not value:
        return ""
    kept = []
    for line in value.splitlines():
        stripped = line.strip()
        if not stripped or _PRINT_FOOTER_LINE.match(stripped):
            continue
        kept.append(_collapse_glyph_spaces(stripped))
    return "\n".join(kept).strip()


def _text_richness(value: str) -> int:
    """汉字越多越像正文。没有汉字时用总长度，避免英文合同被丢掉。"""
    cjk = sum(1 for ch in value if "\u4e00" <= ch <= "\u9fff")
    return cjk if cjk else len(value)


def _usable_document_text(value: str) -> bool:
    """可以交给模型的正文。"""
    stripped = value.strip()
    if not stripped or _looks_like_pdf_source(stripped):
        return False
    return _is_document_text(stripped) and _has_readable_body(stripped)


def _pdf_text_pypdf(file_bytes: bytes) -> str:
    """用 pypdf 解压内容流并抽出文字。FlateDecode 里的正文只有这一步能看见。"""
    if PdfReader is None:
        return ""
    reader = PdfReader(BytesIO(file_bytes))
    if reader.is_encrypted:
        reader.decrypt("")
    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            logger.debug("pypdf skip page", exc_info=True)
            continue
    return "\n".join(parts)


def _pdf_text_pdfium(file_bytes: bytes) -> str:
    """用 PDFium 抽文字。中文合同时它通常不会在每个汉字之间插入空格。"""
    if pdfium is None:
        return ""
    parts: list[str] = []
    pdf = pdfium.PdfDocument(file_bytes)
    try:
        for index in range(len(pdf)):
            page = pdf[index]
            textpage = page.get_textpage()
            try:
                parts.append(textpage.get_text_bounded() or "")
            finally:
                textpage.close()
                page.close()
    finally:
        pdf.close()
    return "\n".join(parts)


def _pdf_text(file_bytes: bytes) -> str:
    """抽出 PDF 可见文字。两种引擎都试，留下整理后更完整的那一份。

    抽不到就返回空，改由页面渲染接手。
    PDFium 先试：中文合同时它通常不会在每个汉字之间插入空格。
    """
    best = ""
    best_score = -1
    for extractor in (_pdf_text_pdfium, _pdf_text_pypdf):
        try:
            raw = extractor(file_bytes)
        except Exception:
            logger.debug("pdf text extractor failed", exc_info=True)
            continue
        text = _normalize_document_text(raw)
        if not _usable_document_text(text):
            continue
        score = _text_richness(text)
        if score > best_score:
            best = text
            best_score = score
    return best


def _extract_file_text(file_bytes: bytes, mime: str, filename: str | None) -> str:
    """非图片文件转成文本。魔数优先于后缀，避免把 PDF 当纯文本解码。"""
    name = (filename or "").lower()
    if file_bytes[:4] == b"%PDF" or mime == "application/pdf" or name.endswith(".pdf"):
        return _pdf_text(file_bytes)
    if _zip_has_docx(file_bytes) or "wordprocessingml" in mime or name.endswith(".docx"):
        return _docx_text(file_bytes)
    if file_bytes.startswith(_OLE_MAGIC) or mime == "application/msword" or name.endswith(".doc"):
        return _doc_text(file_bytes)
    try:
        return file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return ""


def _docx_images(file_bytes: bytes) -> list[tuple[str, bytes]]:
    """解压 docx 的 word/media，取出 jpeg/png 等图片。"""
    images: list[tuple[str, bytes]] = []
    try:
        with zipfile.ZipFile(BytesIO(file_bytes)) as zf:
            names = sorted(
                name
                for name in zf.namelist()
                if name.startswith("word/media/") and not name.endswith("/")
            )
            for name in names:
                ext = name[name.rfind(".") :].lower() if "." in name else ""
                image_mime = _EMBEDDED_EXT_MIME.get(ext)
                if image_mime is None:
                    continue
                images.append((image_mime, zf.read(name)))
    except (zipfile.BadZipFile, KeyError, OSError):
        return []
    return _prefer_page_images(images)


def _pdf_jpeg_images(file_bytes: bytes) -> list[tuple[str, bytes]]:
    """抽出 PDF 里 DCTDecode 的 JPEG。这种流本身就是 SOI 到 EOI 的图片字节。"""
    blobs: list[bytes] = []
    start = 0
    marker = b"\xff\xd8\xff"
    while True:
        soi = file_bytes.find(marker, start)
        if soi < 0:
            break
        eoi = file_bytes.find(b"\xff\xd9", soi + len(marker))
        if eoi < 0:
            break
        blobs.append(file_bytes[soi : eoi + 2])
        start = eoi + 2
    return _prefer_page_images([("image/jpeg", blob) for blob in blobs])


def _prefer_page_images(images: list[tuple[str, bytes]]) -> list[tuple[str, bytes]]:
    """有大图时丢掉印章和二维码，最多保留前几页。"""
    large = [item for item in images if len(item[1]) >= _MIN_EMBEDDED_IMAGE_BYTES]
    chosen = large or images
    return chosen[:_MAX_EMBEDDED_IMAGES]


def _pdf_page_images(file_bytes: bytes) -> list[tuple[str, bytes]]:
    """把 PDF 前几页渲成 PNG。扫描件没有文字层时，模型靠这些图阅读。"""
    if pdfium is None:
        return []
    images: list[tuple[str, bytes]] = []
    pdf = pdfium.PdfDocument(file_bytes)
    try:
        count = min(len(pdf), _MAX_RENDER_PAGES)
        for index in range(count):
            page = pdf[index]
            bitmap = page.render(scale=1.4)
            try:
                image = bitmap.to_pil()
                buf = BytesIO()
                image.save(buf, format="PNG")
                images.append(("image/png", buf.getvalue()))
            finally:
                bitmap.close()
                page.close()
    finally:
        pdf.close()
    return images


def _embedded_images(
    file_bytes: bytes, mime: str, filename: str | None
) -> list[tuple[str, bytes]]:
    """文字抽空后的视觉材料。PDF 优先渲染整页，其次才是内嵌 JPEG。"""
    name = (filename or "").lower()
    if "wordprocessingml" in mime or name.endswith(".docx") or _zip_has_docx(file_bytes):
        return _docx_images(file_bytes)
    if mime == "application/pdf" or name.endswith(".pdf") or file_bytes[:4] == b"%PDF":
        try:
            rendered = _pdf_page_images(file_bytes)
        except Exception:
            logger.debug("pdf page render failed", exc_info=True)
            rendered = []
        if rendered:
            return rendered
        return _pdf_jpeg_images(file_bytes)
    return []


def _image_part(mime: str, raw: bytes) -> dict:
    """拼一条 image_url 内容块。"""
    normalized = "image/jpeg" if mime == "image/jpg" else mime
    b64 = base64.b64encode(raw).decode("ascii")
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{normalized};base64,{b64}"},
    }


def _prepare_document(
    file_bytes: bytes, mime: str, filename: str | None
) -> tuple[list[tuple[str, bytes]], str]:
    """决定交给模型的材料。分类和识别共用。

    直接是图片则用原图。否则先抽文字；文字不像正文时改用页面图。
    返回 (images, text)，二者互斥；都空表示没有可看的内容。
    """
    if mime in _IMAGE_MIME or mime.startswith("image/"):
        return [(mime, file_bytes)], ""
    text = _extract_file_text(file_bytes, mime, filename).strip()
    if _usable_document_text(text):
        return [], text[:_TEXT_LIMIT]
    images = _embedded_images(file_bytes, mime, filename)
    if images:
        return images, ""
    return [], ""


def _as_llm_message_content(parts: list[dict]) -> str | list[dict]:
    """只有文本时改成普通字符串。

    部分 OpenAI 兼容接口对 content 数组处理不稳定；纯文本合同用 string 更稳。
    带图片时仍返回数组。
    """
    if len(parts) == 1 and parts[0].get("type") == "text":
        return str(parts[0].get("text") or "")
    return parts


def _media_content(
    file_bytes: bytes, mime: str, filename: str | None, instruction: str
) -> list[dict]:
    """图片或页面图走 image_url；有正文则附文本。没有可读材料时直接失败。"""
    content: list[dict] = [{"type": "text", "text": instruction}]
    images, text = _prepare_document(file_bytes, mime, filename)
    if images:
        for image_mime, raw in images:
            content.append(_image_part(image_mime, raw))
        return content
    if not text:
        raise DocumentUnreadableError(
            "没能读出这份文件的正文，无法继续审查。"
            "请上传未加密的 PDF 或 Word，或改用清晰的页面图片。"
        )
    # 合成一条文本。有的兼容接口只读取第一条 content，拆成两段时正文会丢
    content[0]["text"] = (
        f"{instruction}\n\n"
        f"【系统已完成文字提取】下面是文件《{filename or '附件'}》的可读正文，"
        f"不是 PDF 源码，也不是二进制流。请直接审查条款：\n"
        f"{text[:_TEXT_LIMIT]}"
    )
    return content
