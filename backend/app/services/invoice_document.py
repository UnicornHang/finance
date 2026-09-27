"""把上传文件变成模型能看的内容。

图片直接作为 image_url。PDF / Word 先抽文字；抽不到正文时改发内嵌图片。
分类、识别和文件对话共用这里的结果。
"""

from __future__ import annotations

import base64
import re
import zipfile
from io import BytesIO
from xml.etree import ElementTree

try:
    from pypdf import PdfReader
except ImportError:  # 项目未声明该依赖，缺失时走字面量抽取
    PdfReader = None

# 按图片块发送的 MIME（其余文件先抽文字，抽不到再发内嵌图）
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

# 扫描件通常一页一张图，多页只带前几张，避免把整本文件塞进上下文
_MAX_EMBEDDED_IMAGES = 3
# 小于此大小的 JPEG 多半是印章或二维码，有大图时跳过
_MIN_EMBEDDED_IMAGE_BYTES = 10_000

# PDF 结构里的英文单词，不能当成票面正文
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


def _guess_mime(file_bytes: bytes, content_type: str | None, filename: str | None) -> str:
    """推断 MIME：优先 content_type，其次魔数，再次文件名后缀。"""
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

    name = (filename or "").lower()
    if name.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if name.endswith(".png"):
        return "image/png"
    if name.endswith(".webp"):
        return "image/webp"
    if name.endswith(".pdf"):
        return "application/pdf"
    return content_type or "application/octet-stream"


def _docx_text(file_bytes: bytes) -> str:
    """从 docx 的 word/document.xml 抽出纯文本。"""
    try:
        with zipfile.ZipFile(BytesIO(file_bytes)) as zf:
            xml = zf.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError):
        return ""
    root = ElementTree.fromstring(xml)
    parts = [node.text for node in root.iter() if node.text and node.text.strip()]
    return "\n".join(parts)


def _is_document_text(value: str) -> bool:
    """二进制被当成字符串时不算正文。只接受汉字和常见 ASCII。"""
    stripped = value.strip()
    if len(stripped) < 2:
        return False
    allowed = 0
    for ch in stripped:
        is_cjk = "\u4e00" <= ch <= "\u9fff"
        is_plain = ch.isascii() and (ch.isalnum() or ch in " \t\r\n.,:/-_()%¥")
        if is_cjk or is_plain:
            allowed += 1
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


def _pdf_text(file_bytes: bytes) -> str:
    """尽量抽出 PDF 里的可见文字。扫描件通常抽不到，随后改发内嵌图。"""
    if PdfReader is not None:
        try:
            reader = PdfReader(BytesIO(file_bytes))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
            if _is_document_text(text):
                return text
        except Exception:
            pass
    # 只保留 PDF 字面量里像正文的片段，避免把 JPEG 字节当成文字
    raw = file_bytes.decode("latin1", errors="ignore")
    chunks = re.findall(r"\((?:\\.|[^\\)]){2,}\)", raw)
    texts = []
    for chunk in chunks[:400]:
        inner = chunk[1:-1].replace("\\n", "\n").replace("\\r", "")
        if _is_document_text(inner):
            texts.append(inner)
    return "\n".join(texts)


def _extract_file_text(file_bytes: bytes, mime: str, filename: str | None) -> str:
    """非图片文件转成文本，交给同一个大模型抽取字段。"""
    name = (filename or "").lower()
    if mime == "application/pdf" or name.endswith(".pdf"):
        return _pdf_text(file_bytes)
    if "wordprocessingml" in mime or name.endswith(".docx"):
        return _docx_text(file_bytes)
    if name.endswith(".doc"):
        return ""
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


def _embedded_images(
    file_bytes: bytes, mime: str, filename: str | None
) -> list[tuple[str, bytes]]:
    """文字抽空时使用的内嵌图。Word 走压缩包，PDF 只取未压缩 JPEG。"""
    name = (filename or "").lower()
    if "wordprocessingml" in mime or name.endswith(".docx"):
        return _docx_images(file_bytes)
    if mime == "application/pdf" or name.endswith(".pdf") or file_bytes[:4] == b"%PDF":
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

    直接是图片则用原图。否则先抽文字；文字为空或只是 PDF 元数据时改用内嵌图片。
    返回 (images, text)，二者互斥；都空表示没有可看的内容。
    """
    if mime in _IMAGE_MIME or mime.startswith("image/"):
        return [(mime, file_bytes)], ""
    text = _extract_file_text(file_bytes, mime, filename).strip()
    if text and _has_readable_body(text):
        return [], text[:12000]
    images = _embedded_images(file_bytes, mime, filename)
    if images:
        return images, ""
    return [], text[:12000]


def _media_content(
    file_bytes: bytes, mime: str, filename: str | None, instruction: str
) -> list[dict]:
    """图片或内嵌图走 image_url；有文字则附文本。分类与文件对话共用。"""
    content: list[dict] = [{"type": "text", "text": instruction}]
    images, text = _prepare_document(file_bytes, mime, filename)
    if images:
        for image_mime, raw in images:
            content.append(_image_part(image_mime, raw))
        return content
    content.append(
        {
            "type": "text",
            "text": f"文件《{filename or '附件'}》文本：\n{(text or '（未能抽出文字）')[:12000]}",
        }
    )
    return content
