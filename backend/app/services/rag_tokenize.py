"""知识库稀疏检索分词：中文重叠 bigram + 西文/数字词，无需额外词典。"""

from __future__ import annotations

import re

_LATIN = re.compile(r"[A-Za-z][A-Za-z0-9._-]{1,}|[0-9]+(?:\.[0-9]+)?")
_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
_TSQUERY_BAD = re.compile(r"[':&|!()*<>]")
# 过短或无检索价值的单字/虚词
_STOP = frozenset(
    {
        "的",
        "了",
        "和",
        "与",
        "或",
        "及",
        "在",
        "是",
        "有",
        "为",
        "对",
        "等",
        "其",
        "该",
        "将",
        "并",
        "把",
        "被",
        "从",
        "到",
        "中",
        "上",
        "下",
    }
)


def tokenize(text: str, *, max_tokens: int = 256) -> list[str]:
    """抽出检索 token，保序去重。"""
    raw = (text or "").strip()
    if not raw:
        return []
    seen: set[str] = set()
    out: list[str] = []

    def _add(token: str) -> None:
        if len(out) >= max_tokens:
            return
        t = token.strip()
        if not t or t in _STOP or t in seen:
            return
        seen.add(t)
        out.append(t)

    for m in _LATIN.finditer(raw):
        _add(m.group(0).lower())
    for m in _CJK_RUN.finditer(raw):
        run = m.group(0)
        if len(run) >= 2:
            _add(run)
        for i in range(len(run) - 1):
            _add(run[i : i + 2])
        if len(run) >= 3:
            for i in range(len(run) - 2):
                _add(run[i : i + 3])
    return out


def to_search_tokens(content: str, title: str | None = None) -> str:
    """索引侧：标题+正文变成空格分词串。"""
    blob = f"{title or ''} {content or ''}".strip()
    return " ".join(tokenize(blob, max_tokens=512))


def query_tokens(question: str, *, max_tokens: int = 16) -> list[str]:
    """查询侧：限制 token 数，避免 OR 查询过宽。"""
    parts = tokenize(question, max_tokens=64)
    # 更长短语优先，专有名词更容易命中
    parts.sort(key=lambda x: (-len(x), x))
    return parts[:max_tokens]


def to_or_tsquery(tokens: list[str]) -> str:
    """拼 simple 配置下的 OR tsquery；非法字符直接丢掉。"""
    parts: list[str] = []
    for token in tokens:
        safe = _TSQUERY_BAD.sub("", token).replace("-", "_")
        if not safe:
            continue
        parts.append(safe)
    return " | ".join(parts)


def keyword_terms(question: str, *, max_terms: int = 4) -> list[str]:
    """ILIKE 回退用的原文词（非整 bigram）。"""
    parts = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9_-]{1,}", question or "")
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        if p in seen:
            continue
        seen.add(p)
        out.append(p)
        if len(out) >= max_terms:
            break
    return out
