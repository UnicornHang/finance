"""Recursive Character：空行 → 行 → 句 → 硬切，块间保留 overlap。"""

from __future__ import annotations

import re

from app.chunking.types import ChunkDraft, DocumentTree, SplitConfig, overlap_tail

_SEPARATORS = (
    re.compile(r"\n\s*\n+"),
    re.compile(r"\n+"),
    re.compile(r"(?<=[。！？；.!?])\s*"),
    re.compile(r"(?<=[，,])\s*"),
)


def split_recursive(tree: DocumentTree, config: SplitConfig) -> list[ChunkDraft]:
    """对每个 section 独立 recursive，再统一编号。"""
    drafts: list[ChunkDraft] = []
    local = 0
    for section in tree.sections:
        pieces = split_text(section.text, config.child_size, config.overlap)
        for piece in pieces:
            drafts.append(
                ChunkDraft(
                    local_id=local,
                    content=piece,
                    role="leaf",
                    embeddable=True,
                    section_path=section.path,
                    page_no=section.page_no,
                )
            )
            local += 1
    return drafts


def split_text(content: str, chunk_size: int, overlap: int) -> list[str]:
    """依次按段落、行、句、逗号递归降级，最后才按字符硬切。"""
    text = (content or "").strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    units = _recursive_units(text, chunk_size, overlap, 0)
    chunks: list[str] = []
    buf = ""
    for piece in units:
        candidate = f"{buf}\n{piece}".strip() if buf else piece
        if len(candidate) <= chunk_size:
            buf = candidate
            continue
        if buf:
            chunks.append(buf)
        prefix = overlap_tail(chunks[-1], overlap) if chunks else ""
        if prefix and piece.startswith(prefix):
            buf = piece
            continue
        with_overlap = f"{prefix}\n{piece}".strip() if prefix else piece
        buf = with_overlap if len(with_overlap) <= chunk_size else piece
    if buf:
        chunks.append(buf)
    return [c for c in chunks if c.strip()]


def _recursive_units(
    text: str,
    chunk_size: int,
    overlap: int,
    level: int,
) -> list[str]:
    """超长片段继续使用下一级分隔符，而不是直接硬切。"""
    value = text.strip()
    if not value:
        return []
    if len(value) <= chunk_size:
        return [value]
    if level >= len(_SEPARATORS):
        return _hard_slices(value, chunk_size, overlap)
    parts = [
        part.strip()
        for part in _SEPARATORS[level].split(value)
        if part and part.strip()
    ]
    if len(parts) <= 1:
        return _recursive_units(value, chunk_size, overlap, level + 1)
    units: list[str] = []
    for part in parts:
        units.extend(
            _recursive_units(part, chunk_size, overlap, level + 1)
        )
    return units


def _hard_slices(
    piece: str,
    chunk_size: int,
    overlap: int,
) -> list[str]:
    """所有自然分隔符都失效时按带重叠的字符窗口切片。"""
    step = max(chunk_size - overlap, 1)
    chunks: list[str] = []
    start = 0
    while start < len(piece):
        end = min(start + chunk_size, len(piece))
        chunks.append(piece[start:end])
        if end >= len(piece):
            break
        start += step
    return chunks
