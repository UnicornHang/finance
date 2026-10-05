"""按文件名把纯文本解析成 section 树。"""

from __future__ import annotations

import re

from app.chunking.types import DocumentTree, Section

_ATX = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
# 制度常见：第一章、第二节、第三条
_CHAPTER = re.compile(
    r"^第[零〇一二三四五六七八九十百千万0-9]+[章节条款篇部分编]"
)
# 短标题：一、  （一）  1.  1.1
_SHORT_HEADING = re.compile(
    r"^(?:"
    r"[一二三四五六七八九十]+、\s*\S+"
    r"|[（(][一二三四五六七八九十0-9]+[)）]\s*\S+"
    r"|[0-9]{1,2}(?:\.[0-9]{1,2})*[、.．]\s*\S+"
    r")$"
)
_LEADING_MARK = re.compile(r"^[\s▪●■◆•·\-–—*＊☆★□■]+")
_SENT_END = re.compile(r"[。！？；.!?]$")
_INLINE_ENUM = re.compile(r"^[一二三四五六七八九十]+是")
_TOPIC_PREFIX = re.compile(
    r"^(?:前言|概述|总述|背景|目的|范围|原则|职责|流程|要求|"
    r"附则|附录|操作指引|典型案例|常见问题|应急与过渡)"
)


def parse_document(content: str, filename: str | None) -> DocumentTree:
    """所有格式都尝试按标题/条款分节；没有标题则整篇一节。"""
    text = (content or "").strip()
    if not text:
        return DocumentTree(sections=[])
    _ = _suffix(filename)
    if any(_ATX.match(normalize_heading_line(line)) for line in text.splitlines()):
        return DocumentTree(sections=_parse_atx_sections(text))
    sections = _parse_heading_sections(text)
    return DocumentTree(sections=sections)


def _suffix(filename: str | None) -> str:
    """小写后缀，含点。"""
    name = (filename or "").lower()
    if "." not in name:
        return ""
    return "." + name.rsplit(".", 1)[-1]


def normalize_heading_line(line: str) -> str:
    """去掉 Word 标题前的方点/项目符号。"""
    return _LEADING_MARK.sub("", (line or "").strip()).strip()


def is_heading_line(line: str, next_line: str | None = None) -> bool:
    """判断一行是否像章节/条款标题。短标题需后面跟较长正文，避免把上一块吃掉。"""
    s = normalize_heading_line(line)
    if not s:
        return False
    if _ATX.match(s):
        return True
    if _CHAPTER.match(s):
        return True
    if (
        len(s) <= 48
        and _SHORT_HEADING.match(s)
        and not _SENT_END.search(s)
    ):
        return True
    if next_line is None:
        return False
    nxt = normalize_heading_line(next_line)
    if not _looks_like_topic_title(s):
        return False
    return len(nxt) >= 30


def _looks_like_topic_title(s: str) -> bool:
    """识别无大纲样式的制度小标题，同时排除元数据与流程正文。"""
    if not (4 <= len(s) <= 40):
        return False
    if _SENT_END.search(s):
        return False
    if _INLINE_ENUM.match(s):
        return False
    if s.count("：") + s.count(":") > 1:
        return False
    if s.count("，") + s.count(",") > 1:
        return False
    if any(marker in s for marker in ("→", "←", "⇒", "⇨")):
        return False
    cjk = sum(1 for ch in s if "\u4e00" <= ch <= "\u9fff")
    if cjk < 4:
        return False
    if _TOPIC_PREFIX.match(s):
        return True
    # 无固定前缀的小标题通常很短，且以“要求/协同/边界/管理”等名词结束。
    return len(s) <= 16 and s.endswith(
        ("要求", "协同", "边界", "管理", "概述", "说明", "原则", "安排", "画像")
    )


def heading_title(line: str) -> str:
    """标题展示名，截断过长行。"""
    s = normalize_heading_line(line)
    m = _ATX.match(s)
    if m:
        return m.group(2).strip()[:80]
    return s[:80]


def _parse_atx_sections(text: str) -> list[Section]:
    """ATX 标题维护路径栈。"""
    sections: list[Section] = []
    stack: list[tuple[int, str]] = []
    buf: list[str] = []
    current_path = ""

    def flush() -> None:
        body = "\n".join(buf).strip()
        buf.clear()
        if not body:
            return
        sections.append(Section(path=current_path, text=body))

    for line in text.splitlines():
        m = _ATX.match(normalize_heading_line(line))
        if not m:
            buf.append(line)
            continue
        flush()
        level = len(m.group(1))
        title = m.group(2).strip()
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
        current_path = "/".join(t for _, t in stack)
        buf.append(title)
    flush()
    if not sections:
        return [Section(path="", text=text)]
    return sections


def _parse_heading_sections(text: str) -> list[Section]:
    """按中文章节/条款/短标题切开；标题行必须作为新节开头，不得留在上一节末尾。"""
    lines = text.splitlines()
    starts: list[int] = []
    for i, line in enumerate(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        if is_heading_line(line, nxt):
            starts.append(i)
    if not starts:
        return [Section(path="", text=text)]

    sections: list[Section] = []
    if starts[0] > 0:
        preface = "\n".join(lines[: starts[0]]).strip()
        if preface:
            sections.append(Section(path="", text=preface))
    for j, start in enumerate(starts):
        end = starts[j + 1] if j + 1 < len(starts) else len(lines)
        block = "\n".join(lines[start:end]).strip()
        if not block:
            continue
        sections.append(Section(path=heading_title(lines[start]), text=block))
    return sections or [Section(path="", text=text)]
