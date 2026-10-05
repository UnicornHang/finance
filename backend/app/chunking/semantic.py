"""Semantic Chunk：邻句向量相似度跌破阈值或局部最低点则另起一块。"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable

from app.chunking.recursive import split_text
from app.chunking.types import ChunkDraft, DocumentTree, Section, SplitConfig

EmbedFn = Callable[[list[str]], Awaitable[list[list[float]]]]

_SENT_SPLIT = re.compile(r"(?<=[。！？；])|(?<=[^0-9.])(?<=[.!?])")


def cosine(a: list[float], b: list[float]) -> float:
    """余弦相似度，零向量视为不相关。"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na < 1e-12 or nb < 1e-12:
        return 0.0
    return dot / ((na**0.5) * (nb**0.5))


def split_sentences(text: str) -> list[str]:
    """句读优先，其次按换行；仍超长则按窗口切开。"""
    raw = (text or "").strip()
    if not raw:
        return []
    units: list[str] = []
    for para in re.split(r"\n+", raw):
        para = para.strip()
        if not para:
            continue
        bits = [p.strip() for p in _SENT_SPLIT.split(para) if p and p.strip()]
        if not bits:
            units.append(para)
            continue
        units.extend(bits)
    # 单句过长时再切一刀，避免整段被当成一句从而和 recursive 撞车
    out: list[str] = []
    window = 180
    for u in units:
        if len(u) <= window:
            out.append(u)
            continue
        for i in range(0, len(u), window):
            piece = u[i : i + window].strip()
            if piece:
                out.append(piece)
    return out


def group_by_similarity(
    sentences: list[str],
    vectors: list[list[float]],
    *,
    min_size: int,
    max_size: int,
    threshold: float,
) -> list[str]:
    """按相似度谷值切分；threshold 表示灵敏度，越大越容易切开。"""
    if not sentences:
        return []
    if len(sentences) != len(vectors):
        return ["\n".join(sentences)]
    sims = [
        cosine(vectors[i], vectors[i + 1]) for i in range(len(sentences) - 1)
    ]
    distances = [max(0.0, 1.0 - sim) for sim in sims]
    # 0.15 → 87.5 分位；0.85 → 52.5 分位。灵敏度越高，断点越多。
    quantile = 0.95 - threshold * 0.5
    dynamic_cutoff = max(0.08, _percentile(distances, quantile))
    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0
    for i, sent in enumerate(sentences):
        slen = len(sent)
        if buf and buf_len + slen > max_size:
            chunks.append("".join(buf))
            buf = [sent]
            buf_len = slen
            continue
        if buf and i > 0 and buf_len >= min_size:
            distance = distances[i - 1]
            local_peak = _is_local_peak(distances, i - 1)
            strong_shift = distance >= 0.28
            if strong_shift or (
                distance >= dynamic_cutoff and local_peak
            ):
                chunks.append("".join(buf))
                buf = [sent]
                buf_len = slen
                continue
        buf.append(sent)
        buf_len += slen
    if buf:
        chunks.append("".join(buf))
    return [c.strip() for c in chunks if c.strip()]


def _percentile(values: list[float], quantile: float) -> float:
    """线性插值分位数，避免引入数值计算依赖。"""
    if not values:
        return 1.0
    ordered = sorted(values)
    position = min(max(quantile, 0.0), 1.0) * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    ratio = position - lower
    return ordered[lower] * (1 - ratio) + ordered[upper] * ratio


def _is_local_peak(distances: list[float], idx: int) -> bool:
    """语义距离局部峰值，代表相邻句发生话题跳变。"""
    if not distances:
        return False
    value = distances[idx]
    left = distances[idx - 1] if idx > 0 else 0.0
    right = distances[idx + 1] if idx + 1 < len(distances) else 0.0
    return value >= left and value >= right


async def split_semantic(
    tree: DocumentTree,
    config: SplitConfig,
    embed_fn: EmbedFn,
) -> list[ChunkDraft]:
    """对每节分句后按向量断点组块；组后仍超长则 recursive 收尾。"""
    jobs: list[tuple[Section, list[str]]] = []
    for section in tree.sections:
        sents = split_sentences(section.text)
        jobs.append((section, sents))
    all_sents = [s for _, sents in jobs for s in sents]
    min_size = max(60, config.child_size // 6)
    # 语义块允许比递归块更长，否则会被字数上限切成同样长短
    max_size = min(max(config.child_size * 2, 800), 2000)
    threshold = config.semantic_threshold

    vectors: list[list[float]] | None = None
    if len(all_sents) >= 2:
        vectors = await embed_fn(all_sents)
        _validate_vectors(vectors, len(all_sents))

    drafts: list[ChunkDraft] = []
    local = 0
    offset = 0
    for section, sents in jobs:
        if not sents:
            continue
        if vectors is None or len(sents) < 2:
            pieces = split_text(section.text, config.child_size, config.overlap)
        else:
            part = vectors[offset : offset + len(sents)]
            pieces = group_by_similarity(
                sents,
                part,
                min_size=min_size,
                max_size=max_size,
                threshold=threshold,
            )
            refined: list[str] = []
            for piece in pieces:
                if len(piece) <= max_size:
                    refined.append(piece)
                else:
                    refined.extend(
                        split_text(piece, config.child_size, config.overlap)
                    )
            pieces = refined or split_text(
                section.text, config.child_size, config.overlap
            )
        offset += len(sents)
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


def _validate_vectors(vectors: list[list[float]], expected: int) -> None:
    """语义切分必须获得数量、维数一致的非零向量，否则触发明确降级。"""
    if len(vectors) != expected:
        raise ValueError("语义切分向量数量不匹配")
    dimensions = {len(vector) for vector in vectors}
    if len(dimensions) != 1 or not dimensions or 0 in dimensions:
        raise ValueError("语义切分向量维数无效")
    if any(not any(abs(value) > 1e-12 for value in vector) for vector in vectors):
        raise ValueError("语义切分收到零向量")
