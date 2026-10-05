"""Parent-Child：父块提供上下文，子块负责精确检索。"""

from __future__ import annotations

from dataclasses import dataclass

from app.chunking.recursive import split_text
from app.chunking.types import ChunkDraft, DocumentTree, Section, SplitConfig


@dataclass(slots=True)
class _ParentUnit:
    """尚未包装角色的父级上下文。"""

    content: str
    section_path: str
    page_no: int | None


def split_parent_child(
    tree: DocumentTree, config: SplitConfig
) -> list[ChunkDraft]:
    """先构造长父块，再在每个父块内生成短子块。

    父块跨相邻短章节聚合，避免“一个章节一个父块”导致父块与子块完全相同。
    """
    parents = _build_parent_units(tree.sections, config.parent_size)
    if not parents:
        return []
    out: list[ChunkDraft] = []
    local = 0
    for parent in parents:
        parent_id = local
        out.append(
            ChunkDraft(
                local_id=parent_id,
                content=parent.content,
                role="parent",
                embeddable=False,
                section_path=parent.section_path,
                page_no=parent.page_no,
            )
        )
        local += 1
        child_size = _effective_child_size(
            len(parent.content),
            config.child_size,
        )
        child_overlap = min(config.overlap, child_size - 1)
        children = split_text(
            parent.content,
            child_size,
            child_overlap,
        )
        for child_text in children:
            out.append(
                ChunkDraft(
                    local_id=local,
                    content=child_text,
                    role="child",
                    embeddable=True,
                    section_path=parent.section_path,
                    page_no=parent.page_no,
                    parent_local_id=parent_id,
                )
            )
            local += 1
    return out


def _effective_child_size(parent_length: int, configured_size: int) -> int:
    """短父块仍尽量拆出不同子块；不足 100 字时不做无意义硬拆。"""
    if parent_length <= 100 or parent_length > configured_size:
        return configured_size
    return max(100, min(configured_size - 1, parent_length // 2))


def _build_parent_units(
    sections: list[Section], parent_size: int
) -> list[_ParentUnit]:
    """按原文顺序把章节聚合到父块，单章过长时先按父块上限切开。"""
    limit = max(parent_size, 1)
    units: list[_ParentUnit] = []
    buf: list[str] = []
    paths: list[str] = []
    page_no: int | None = None

    def flush() -> None:
        nonlocal page_no
        content = "\n".join(buf).strip()
        if content:
            units.append(
                _ParentUnit(
                    content=content,
                    section_path=_path_range(paths),
                    page_no=page_no,
                )
            )
        buf.clear()
        paths.clear()
        page_no = None

    for section in sections:
        text = section.text.strip()
        if not text:
            continue
        if len(text) > limit:
            flush()
            for piece in split_text(text, limit, 0):
                units.append(
                    _ParentUnit(
                        content=piece,
                        section_path=section.path,
                        page_no=section.page_no,
                    )
                )
            continue
        candidate_len = sum(len(item) for item in buf) + len(buf) + len(text)
        if buf and candidate_len > limit:
            flush()
        buf.append(text)
        if section.path and section.path not in paths:
            paths.append(section.path)
        if page_no is None:
            page_no = section.page_no
    flush()
    return units


def _path_range(paths: list[str]) -> str:
    """父块覆盖多个章节时给出稳定、可读的路径范围。"""
    if not paths:
        return ""
    if len(paths) == 1:
        return paths[0]
    return f"{paths[0]} … {paths[-1]}"
