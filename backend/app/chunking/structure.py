"""按标题节切分：节内再套 recursive；标题不得并入上一块末尾。"""

from __future__ import annotations

from app.chunking.parse import heading_title, is_heading_line
from app.chunking.recursive import split_text
from app.chunking.types import ChunkDraft, DocumentTree, SplitConfig


def split_structure(tree: DocumentTree, config: SplitConfig) -> list[ChunkDraft]:
    """每个标题开新块；节内超长才按长度切，第一块仍以标题开头。"""
    drafts: list[ChunkDraft] = []
    local = 0
    for section in tree.sections:
        for path, block in _heading_blocks(section.text, section.path):
            pieces = split_text(block, config.child_size, config.overlap)
            for piece in pieces:
                drafts.append(
                    ChunkDraft(
                        local_id=local,
                        content=piece,
                        role="leaf",
                        embeddable=True,
                        section_path=path,
                        page_no=section.page_no,
                    )
                )
                local += 1
    return drafts


def _heading_blocks(text: str, default_path: str) -> list[tuple[str, str]]:
    """节内再扫一遍标题，避免漏检时标题被 recursive 塞进上一块。"""
    text = (text or "").strip()
    if not text:
        return []
    lines = text.splitlines()
    starts: list[int] = []
    for i, line in enumerate(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        if is_heading_line(line, nxt):
            starts.append(i)
    if not starts:
        return [(default_path, text)]
    out: list[tuple[str, str]] = []
    if starts[0] > 0:
        preface = "\n".join(lines[: starts[0]]).strip()
        if preface:
            out.append((default_path, preface))
    for j, start in enumerate(starts):
        end = starts[j + 1] if j + 1 < len(starts) else len(lines)
        block = "\n".join(lines[start:end]).strip()
        if block:
            out.append((heading_title(lines[start]) or default_path, block))
    return out or [(default_path, text)]
