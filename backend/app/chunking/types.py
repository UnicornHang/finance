"""切分领域类型：文档树、切分配置、块草稿。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

StrategyName = Literal["recursive", "structure", "parent_child", "semantic"]
InnerStrategy = Literal["recursive", "structure"]
ChunkRole = Literal["leaf", "child", "parent"]

CHILD_SIZE_DEFAULT = 400
PARENT_SIZE_DEFAULT = 1200
OVERLAP_DEFAULT = 50
RECURSIVE_SIZE_DEFAULT = 500
PARENT_INJECT_MAX_CHARS = 1500
PARENT_CHILD_MAX_CHILD_CHARS = 1000
SEMANTIC_THRESHOLD_DEFAULT = 0.45


@dataclass(slots=True)
class Section:
    """解析后的一节：标题路径 + 正文。"""

    path: str
    text: str
    page_no: int | None = None


@dataclass(slots=True)
class DocumentTree:
    """弱结构文档树，目前一层 section 足够。"""

    sections: list[Section] = field(default_factory=list)


@dataclass(slots=True)
class SplitConfig:
    """一次索引的切分参数。"""

    strategy: StrategyName = "parent_child"
    inner_strategy: InnerStrategy = "recursive"
    child_size: int = CHILD_SIZE_DEFAULT
    parent_size: int = PARENT_SIZE_DEFAULT
    overlap: int = OVERLAP_DEFAULT
    semantic_threshold: float = SEMANTIC_THRESHOLD_DEFAULT


@dataclass(slots=True)
class ChunkDraft:
    """尚未落库的切块。parent_local_id 指向同批 local_id。"""

    local_id: int
    content: str
    role: ChunkRole
    embeddable: bool
    section_path: str = ""
    page_no: int | None = None
    parent_local_id: int | None = None


def overlap_tail(text: str, overlap: int) -> str:
    """取块尾作为下一块前缀，避免段落边界丢上下文。"""
    if overlap <= 0 or not text:
        return ""
    if len(text) <= overlap:
        return text
    return text[-overlap:]
