"""四种切分策略的差异化输出契约。"""

import asyncio

from app.chunking.parse import parse_document
from app.chunking.pipeline import (
    normalize_split_config,
    run_split,
    split_document,
)
from app.chunking.recursive import split_text
from app.chunking.semantic import cosine, group_by_similarity
from app.chunking.types import SplitConfig
from app.services.rag_hybrid import _parent_window


def test_recursive_overlap_on_paragraph_boundary():
    """段落装不下时，下一块应带上一段尾部 overlap。"""
    a = "甲" * 80
    b = "乙" * 80
    text = f"{a}\n\n{b}"
    chunks = split_text(text, chunk_size=100, overlap=10)
    assert len(chunks) >= 2
    assert chunks[0].startswith("甲")
    assert "乙" in chunks[1]
    assert chunks[1].startswith("甲" * 10) or "甲" in chunks[1][:20]


def test_recursive_uses_sentence_boundary_inside_long_paragraph():
    """超长段落必须继续降级到句子，不能直接按字符截断。"""
    sentence = "这是一条完整的制度句子。"
    chunks = split_text(sentence * 30, chunk_size=100, overlap=10)
    assert len(chunks) > 1
    assert all(chunk.endswith("。") for chunk in chunks)


def test_markdown_structure_section_path():
    """md 标题进入 section_path。"""
    md = "# 差旅\n\n## 住宿\n\n单晚上限五百元。\n"
    drafts = split_document(
        md,
        filename="policy.md",
        config=SplitConfig(strategy="structure", child_size=200, overlap=0),
    )
    assert drafts
    assert any("住宿" in (d.section_path or "") for d in drafts)


def test_parent_child_roles():
    """父子包装：parent 不可检索，child 带 parent_local_id。"""
    text = "第一段内容足够长。\n\n" + ("条款正文。" * 40)
    cfg = normalize_split_config(
        strategy="parent_child",
        filename="a.txt",
        child_size=80,
        parent_size=200,
        overlap=10,
    )
    drafts = split_document(text, filename="a.txt", config=cfg)
    parents = [d for d in drafts if d.role == "parent"]
    children = [d for d in drafts if d.role == "child"]
    assert parents
    assert children
    assert all(not p.embeddable for p in parents)
    assert all(c.embeddable and c.parent_local_id is not None for c in children)
    assert max(len(p.content) for p in parents) > min(
        len(c.content) for c in children
    )
    assert any(
        sum(c.parent_local_id == p.local_id for c in children) >= 2
        for p in parents
    )


def test_parse_plain_txt_single_section():
    """无标题的 txt 整篇一节。"""
    tree = parse_document("hello world " * 5, "note.txt")
    assert len(tree.sections) == 1
    assert tree.sections[0].path == ""


def test_parse_chinese_chapter_headings():
    """docx/txt 里的第一章、一、 应分成多节。"""
    text = "第一章 总则\n为规范发票管理。\n第二章 开具\n应当如实开具发票。\n一、适用范围\n全体员工。\n二、职责\n财务部负责。"
    tree = parse_document(text, "规范.docx")
    paths = [s.path for s in tree.sections]
    assert "第一章 总则" in paths
    assert "第二章 开具" in paths
    assert any("适用范围" in p for p in paths)


def test_recursive_ignores_headings_structure_keeps_them():
    """同一制度文：按长度切 与 按章节切 的边界应不同。"""
    text = (
        "第一章 总则\n"
        + "甲" * 80
        + "\n第二章 开具\n"
        + "乙" * 80
    )
    rec = split_document(
        text,
        filename="规范.docx",
        config=SplitConfig(strategy="recursive", child_size=200, overlap=0),
    )
    st = split_document(
        text,
        filename="规范.docx",
        config=SplitConfig(strategy="structure", child_size=200, overlap=0),
    )
    assert rec
    assert st
    assert any(d.section_path == "第一章 总则" for d in st)
    assert all(not d.section_path for d in rec)
    rec_starts = [d.content[:4] for d in rec]
    st_starts = [d.content[:4] for d in st]
    assert rec_starts != st_starts or len(rec) != len(st)


def test_semantic_breaks_when_topic_shifts():
    """邻句不相似且已够 min_size 时断开。"""
    sents = ["住宿上限五百元。", "宾馆标准间可报销。", "合同盖章必须双章。"]
    v_stay = [1.0, 0.0]
    v_shift = [0.0, 1.0]
    chunks = group_by_similarity(
        sents,
        [v_stay, v_stay, v_shift],
        min_size=5,
        max_size=200,
        threshold=0.5,
    )
    assert len(chunks) == 2
    assert "住宿" in chunks[0]
    assert "盖章" in chunks[1]


def test_cosine_identical_is_one():
    """相同向量余弦为 1。"""
    assert abs(cosine([1.0, 0.0], [1.0, 0.0]) - 1.0) < 1e-6


def test_four_strategies_have_distinct_contracts():
    """同一制度文的四种策略必须呈现不同角色、路径或边界。"""
    text = (
        "第一章 差旅管理\n"
        + "住宿标准适用于全体员工。标准间费用按城市等级执行。" * 8
        + "\n第二章 合同管理\n"
        + "合同签署前必须完成法务审查。盖章后方可正式生效。" * 8
        + "\n第三章 发票管理\n"
        + "发票报销前必须完成查验。重复发票不得再次报销。" * 8
    )
    recursive = split_document(
        text,
        filename="制度.docx",
        config=SplitConfig(
            strategy="recursive",
            child_size=180,
            overlap=20,
        ),
    )
    structure = split_document(
        text,
        filename="制度.docx",
        config=SplitConfig(
            strategy="structure",
            child_size=180,
            overlap=20,
        ),
    )
    parent_child = split_document(
        text,
        filename="制度.docx",
        config=SplitConfig(
            strategy="parent_child",
            child_size=120,
            parent_size=500,
            overlap=20,
        ),
    )

    async def fake_embed(sentences: list[str]) -> list[list[float]]:
        """按主题生成可预测向量，模拟真实话题跳变。"""
        vectors: list[list[float]] = []
        for sentence in sentences:
            if "合同" in sentence or "盖章" in sentence:
                vectors.append([0.0, 1.0, 0.0])
            elif "发票" in sentence or "报销" in sentence:
                vectors.append([0.0, 0.0, 1.0])
            else:
                vectors.append([1.0, 0.0, 0.0])
        return vectors

    semantic, effective, fallback = asyncio.run(
        run_split(
            text,
            filename="制度.docx",
            config=SplitConfig(
                strategy="semantic",
                child_size=180,
                overlap=0,
                semantic_threshold=0.45,
            ),
            embed_fn=fake_embed,
        )
    )

    assert all(d.role == "leaf" and not d.section_path for d in recursive)
    assert all(d.role == "leaf" and d.section_path for d in structure)
    assert {d.role for d in parent_child} == {"parent", "child"}
    assert effective == "semantic"
    assert fallback is None
    assert all(d.role == "leaf" for d in semantic)
    signatures = {
        tuple((d.role, d.section_path, d.content) for d in drafts)
        for drafts in (recursive, structure, parent_child, semantic)
    }
    assert len(signatures) == 4


def test_structure_heading_starts_next_chunk():
    """短标题必须开新块，不能留在上一块末尾。"""
    preface = "前言：发票是企业财务核算与税务合规的核心凭证。" * 8
    heading = "与财务智能平台的协同"
    body = "公司财务智能平台支持发票上传识别、结构化字段展示与查重拦截。" * 4
    text = (
        f"{preface}\n"
        f"总述：发票风险画像\n"
        f"{'从近年内部审计与财务抽查情况看。' * 6}\n"
        f"{heading}\n"
        f"{body}"
    )
    drafts = split_document(
        text,
        filename="规范.docx",
        config=SplitConfig(strategy="structure", child_size=500, overlap=50),
    )
    contents = [d.content.strip() for d in drafts]
    assert any(c.startswith(heading) or c.lstrip("# ").startswith(heading) for c in contents)
    for i, c in enumerate(contents[:-1]):
        last_line = c.splitlines()[-1].strip().lstrip("# ").strip()
        assert last_line != heading, f"标题留在块 {i} 末尾: {c[-40:]}"
    assert any("协同" in (d.section_path or "") for d in drafts)


def test_parent_window_contains_hit_from_parent_tail():
    """命中父块后半段时，扩展窗口仍必须包含命中的子块。"""
    child = "命中的关键发票条款"
    parent = "前文" * 1000 + child + "后文" * 1000
    window = _parent_window(parent, child, 1500)
    assert len(window) <= 1500
    assert child in window
