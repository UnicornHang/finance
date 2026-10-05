"""DOCX 正文与标题结构抽取。"""

from __future__ import annotations

import re
import zipfile
from io import BytesIO
from xml.etree import ElementTree

_WML = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def extract_docx_text(file_bytes: bytes) -> str:
    """抽取正文、页眉页脚和批注；Word 标题转换为 Markdown 标记。"""
    try:
        with zipfile.ZipFile(BytesIO(file_bytes)) as zf:
            names = _docx_part_names(zf.namelist())
            style_levels = _read_heading_styles(zf)
            chunks = [
                _xml_visible_text(
                    zf.read(name),
                    style_levels if name == "word/document.xml" else None,
                )
                for name in names
            ]
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError, OSError):
        return ""
    return "\n".join(chunk for chunk in chunks if chunk)


def _read_heading_styles(zf: zipfile.ZipFile) -> dict[str, int]:
    """读取可用的 Word 标题样式，损坏时按无样式处理。"""
    if "word/styles.xml" not in zf.namelist():
        return {}
    try:
        return _heading_style_levels(zf.read("word/styles.xml"))
    except (ElementTree.ParseError, OSError, ValueError):
        return {}


def _docx_part_names(names: list[str]) -> list[str]:
    """正文在前，页眉页脚和批注在后；样式表不作为正文。"""
    body = [name for name in names if name == "word/document.xml"]
    extras = sorted(
        name
        for name in names
        if name.startswith("word/")
        and name.endswith(".xml")
        and (
            name.startswith("word/header")
            or name.startswith("word/footer")
            or name
            in {
                "word/footnotes.xml",
                "word/endnotes.xml",
                "word/comments.xml",
            }
        )
    )
    return body + extras


def _w_attr(elem: ElementTree.Element, name: str) -> str:
    """读取 w: 属性，兼容无命名空间 XML。"""
    return (elem.get(f"{_WML}{name}") or elem.get(name) or "").strip()


def _heading_style_levels(styles_xml: bytes) -> dict[str, int]:
    """把段落样式 ID 映射为标题层级，一级标题为 0。"""
    root = ElementTree.fromstring(styles_xml)
    mapping: dict[str, int] = {}
    for style in root.iter(f"{_WML}style"):
        if _w_attr(style, "type") not in ("", "paragraph"):
            continue
        style_id = _w_attr(style, "styleId")
        if not style_id:
            continue
        name_element = style.find(f"{_WML}name")
        name = (
            _w_attr(name_element, "val").lower()
            if name_element is not None
            else ""
        )
        outline = _style_outline_level(style)
        numbered = re.search(r"(?:heading|标题)\s*(\d+)", name)
        if outline is None and numbered:
            outline = max(int(numbered.group(1)) - 1, 0)
        if outline is None and ("heading" in name or "标题" in name):
            outline = 0
        if outline is not None:
            mapping[style_id] = outline
    return mapping


def _style_outline_level(style: ElementTree.Element) -> int | None:
    """读取样式定义中的大纲级别。"""
    properties = style.find(f"{_WML}pPr")
    if properties is None:
        return None
    outline = properties.find(f"{_WML}outlineLvl")
    if outline is None:
        return None
    try:
        return int(_w_attr(outline, "val") or "0")
    except ValueError:
        return 0


def _paragraph_heading_level(
    paragraph: ElementTree.Element,
    style_levels: dict[str, int],
) -> int | None:
    """读取段落自身或其段落样式中的大纲级别。"""
    properties = paragraph.find(f"{_WML}pPr")
    if properties is None:
        return None
    outline = properties.find(f"{_WML}outlineLvl")
    if outline is not None:
        try:
            return int(_w_attr(outline, "val") or "0")
        except ValueError:
            return 0
    paragraph_style = properties.find(f"{_WML}pStyle")
    if paragraph_style is None:
        return None
    return style_levels.get(_w_attr(paragraph_style, "val"))


def _xml_visible_text(
    xml: bytes,
    style_levels: dict[str, int] | None = None,
) -> str:
    """按段落抽取文本；标题段落添加对应层级的 Markdown 标记。"""
    root = ElementTree.fromstring(xml)
    levels = style_levels or {}
    paragraphs: list[str] = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] != "p":
            continue
        line = "".join(
            node.text or ""
            for node in element.iter()
            if node.tag.rsplit("}", 1)[-1] == "t"
        ).strip()
        if not line:
            continue
        heading_level = _paragraph_heading_level(element, levels)
        if heading_level is None:
            paragraphs.append(line)
            continue
        hashes = "#" * min(heading_level + 1, 6)
        paragraphs.append(f"{hashes} {line}")
    if paragraphs:
        return "\n".join(paragraphs)
    return "\n".join(
        node.text.strip()
        for node in root.iter()
        if node.text and node.text.strip()
    )
