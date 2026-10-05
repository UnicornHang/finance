"""混合检索融合与 Rerank 解析。"""

from app.services.rag_hybrid import (
    channel_source,
    display_score,
    normalize_rerank_scores,
    reciprocal_rank_fusion,
)
from app.services.rag_tokenize import query_tokens, to_or_tsquery, to_search_tokens
from app.services.rerank_service import rerank_service


def test_tokenize_chinese_bigrams():
    """中文切出整词与 overlapping n-gram。"""
    tokens = to_search_tokens("差旅补贴标准", title="报销制度")
    assert "差旅" in tokens
    assert "补贴" in tokens
    assert "报销制度" in tokens


def test_query_tsquery_uses_or():
    """查询侧用 OR，避免多 token AND 导致零召回。"""
    q = to_or_tsquery(query_tokens("差旅补贴"))
    assert " | " in q
    assert "差旅" in q


def test_rrf_prefers_multi_channel_hits():
    """两路都靠前的文档 RRF 更高。"""
    scores = reciprocal_rank_fusion(
        [["a", "b", "c"], ["a", "d", "e"]],
        k=60,
    )
    assert scores["a"] > scores["b"]
    assert scores["a"] > scores["d"]


def test_display_score_prefers_rerank():
    """有 Rerank 分时覆盖融合分。"""
    assert display_score(vector_score=0.9, sparse_score=0.2, rerank_score=0.41) == 0.41
    fused = display_score(vector_score=0.9, sparse_score=0.5, rerank_score=None)
    assert 0.6 * 0.9 + 0.4 * 0.5 == fused


def test_channel_source():
    """来源标记。"""
    assert channel_source(True, True) == "hybrid"
    assert channel_source(True, False) == "vector"
    assert channel_source(False, True) == "keyword"


def test_normalize_rerank_passthrough_unit_interval():
    """已在 [0,1] 不拉伸。"""
    assert normalize_rerank_scores([0.2, 0.8]) == [0.2, 0.8]


def test_normalize_rerank_minmax_logits():
    """超出 [0,1] 时按本批 min-max。"""
    out = normalize_rerank_scores([-2.0, 2.0])
    assert out[0] == 0.0
    assert out[1] == 1.0


def test_parse_dashscope_rerank_envelope():
    """解析通义 output.results 包体。"""
    data = {
        "output": {
            "results": [
                {"index": 1, "relevance_score": 0.9},
                {"index": 0, "relevance_score": 0.1},
            ]
        }
    }
    parsed = rerank_service._parse_results(data, n_docs=2)
    assert parsed[0] == (1, 0.9)
    assert parsed[1] == (0, 0.1)
