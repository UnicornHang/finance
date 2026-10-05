"""切分入口：校验配置、选策略、产出草稿。"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from app.chunking.parse import parse_document
from app.chunking.parent_child import split_parent_child
from app.chunking.recursive import split_recursive
from app.chunking.semantic import split_semantic
from app.chunking.structure import split_structure
from app.chunking.types import (
    CHILD_SIZE_DEFAULT,
    OVERLAP_DEFAULT,
    PARENT_CHILD_MAX_CHILD_CHARS,
    PARENT_SIZE_DEFAULT,
    RECURSIVE_SIZE_DEFAULT,
    SEMANTIC_THRESHOLD_DEFAULT,
    ChunkDraft,
    DocumentTree,
    InnerStrategy,
    Section,
    SplitConfig,
    StrategyName,
)
from app.core.exceptions import BusinessError

logger = logging.getLogger(__name__)

_STRATEGIES = frozenset({"recursive", "structure", "parent_child", "semantic"})
_INNERS = frozenset({"recursive", "structure"})

EmbedFn = Callable[[list[str]], Awaitable[list[list[float]]]]


def default_inner_strategy(filename: str | None) -> InnerStrategy:
    """父子切分的内层：一律先走结构（能识别中文章节）；无标题时等价 recursive。"""
    _ = filename
    return "structure"


def normalize_split_config(
    *,
    strategy: str | None,
    filename: str | None,
    child_size: int | None,
    parent_size: int | None,
    overlap: int | None,
    inner_strategy: str | None = None,
    semantic_threshold: float | None = None,
) -> SplitConfig:
    """校验并填默认值。未知策略直接失败。"""
    raw = (strategy or "parent_child").strip().lower()
    if raw not in _STRATEGIES:
        raise BusinessError(
            "切分策略须为 recursive / structure / parent_child / semantic",
            code="KB_CHUNK_STRATEGY_INVALID",
        )
    if raw == "recursive":
        name: StrategyName = "recursive"
    elif raw == "structure":
        name = "structure"
    elif raw == "semantic":
        name = "semantic"
    else:
        name = "parent_child"
    inner_raw = (inner_strategy or default_inner_strategy(filename)).strip().lower()
    if inner_raw not in _INNERS:
        raise BusinessError(
            "内部切分须为 recursive / structure",
            code="KB_CHUNK_INNER_INVALID",
        )
    if inner_raw == "structure":
        inner: InnerStrategy = "structure"
    else:
        inner = "recursive"

    size_default = (
        RECURSIVE_SIZE_DEFAULT if name == "recursive" else CHILD_SIZE_DEFAULT
    )
    size = int(child_size) if child_size else size_default
    ov = int(overlap) if overlap is not None else OVERLAP_DEFAULT
    psize = int(parent_size) if parent_size else PARENT_SIZE_DEFAULT
    thr = (
        float(semantic_threshold)
        if semantic_threshold is not None
        else SEMANTIC_THRESHOLD_DEFAULT
    )
    if size < 100 or size > 4000:
        raise BusinessError("分段长度须在 100–4000 之间", code="KB_CHUNK_SIZE_INVALID")
    if ov < 0 or ov >= size:
        raise BusinessError("重叠长度须 ≥0 且小于分段长度", code="KB_CHUNK_OVERLAP_INVALID")
    if name == "parent_child":
        if size > PARENT_CHILD_MAX_CHILD_CHARS:
            raise BusinessError(
                f"父子切分的子块长度不能超过 {PARENT_CHILD_MAX_CHILD_CHARS}",
                code="KB_CHILD_SIZE_INVALID",
            )
        if psize <= size or psize > 8000:
            raise BusinessError(
                "父块长度须大于子块且不超过 8000",
                code="KB_PARENT_SIZE_INVALID",
            )
    if name == "semantic" and not 0.15 <= thr <= 0.85:
        raise BusinessError(
            "话题断开阈值须在 0.15–0.85 之间",
            code="KB_SEMANTIC_THRESHOLD_INVALID",
        )
    return SplitConfig(
        strategy=name,
        inner_strategy=inner,
        child_size=size,
        parent_size=psize,
        overlap=ov,
        semantic_threshold=thr,
    )


def _flat_tree(content: str) -> DocumentTree:
    """整篇一节，忽略标题。recursive / semantic 用这条，避免和 structure 撞车。"""
    text = (content or "").strip()
    if not text:
        return DocumentTree(sections=[])
    return DocumentTree(sections=[Section(path="", text=text)])


def split_document(
    content: str,
    *,
    filename: str | None,
    config: SplitConfig,
) -> list[ChunkDraft]:
    """同步切分（不含 semantic，semantic 走 run_split）。"""
    if config.strategy == "recursive":
        tree = _flat_tree(content)
    else:
        tree = parse_document(content, filename)
    if not tree.sections:
        return []
    match config.strategy:
        case "recursive":
            return split_recursive(tree, config)
        case "structure":
            return split_structure(tree, config)
        case "semantic":
            return split_recursive(tree, config)
        case "parent_child":
            return split_parent_child(tree, config)
        case _ as unreachable:
            raise BusinessError(
                f"未实现的切分策略：{unreachable}",
                code="KB_CHUNK_STRATEGY_INVALID",
            )


async def run_split(
    content: str,
    *,
    filename: str | None,
    config: SplitConfig,
    embed_fn: EmbedFn | None = None,
) -> tuple[list[ChunkDraft], StrategyName, str | None]:
    """执行切分；semantic 失败时回退 recursive 并返回原因。"""
    if config.strategy != "semantic":
        return split_document(content, filename=filename, config=config), config.strategy, None
    tree = _flat_tree(content)
    if not tree.sections:
        return [], "semantic", None
    if embed_fn is None:
        return (
            split_recursive(tree, config),
            "recursive",
            "semantic_embed_unavailable",
        )
    try:
        drafts = await split_semantic(tree, config, embed_fn)
    except Exception:
        logger.exception("semantic split failed, fallback recursive")
        return split_recursive(tree, config), "recursive", "semantic_embed_failed"
    if not drafts:
        return split_recursive(tree, config), "recursive", "semantic_empty"
    return drafts, "semantic", None


def config_to_params(
    config: SplitConfig,
    *,
    fallback_reason: str | None = None,
    drafts: list[ChunkDraft] | None = None,
) -> dict:
    """把实际配置和切分统计落库，供验收与故障诊断。"""
    data = {
        "child_size": config.child_size,
        "parent_size": config.parent_size,
        "overlap": config.overlap,
        "inner_strategy": config.inner_strategy,
        "semantic_threshold": config.semantic_threshold,
    }
    if fallback_reason:
        data["fallback_reason"] = fallback_reason
    if drafts is not None:
        retrieval = [draft for draft in drafts if draft.embeddable]
        lengths = [len(draft.content) for draft in retrieval]
        data["split_stats"] = {
            "stored_chunks": len(drafts),
            "retrieval_chunks": len(retrieval),
            "parent_chunks": sum(draft.role == "parent" for draft in drafts),
            "child_chunks": sum(draft.role == "child" for draft in drafts),
            "leaf_chunks": sum(draft.role == "leaf" for draft in drafts),
            "min_chars": min(lengths, default=0),
            "max_chars": max(lengths, default=0),
            "avg_chars": (
                round(sum(lengths) / len(lengths), 1) if lengths else 0
            ),
            "section_paths": len(
                {
                    draft.section_path
                    for draft in drafts
                    if draft.section_path
                }
            ),
        }
    return data
