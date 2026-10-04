"""附件子图：分类硬路由，不把识别做成 Tool。"""

import pytest

pytest.importorskip("langgraph")

from app.agent.upload_graph import after_classify, get_upload_graph, upload_runtime


@pytest.mark.asyncio
async def test_upload_graph_routes_invoice():
    """发票分类进入 invoice 节点。"""

    async def classify(*_args, **_kwargs) -> str:
        return "invoice"

    token = upload_runtime.set(
        {
            "classify": classify,
            "file_bytes": b"%PDF",
            "content_type": "application/pdf",
            "filename": "a.pdf",
            "user_message": "识别这个合同",
            "db": None,
            "tenant_id": "t",
        }
    )
    try:
        final = await get_upload_graph().ainvoke(
            {"user_message": "识别这个合同", "file_kind": "", "error": ""}
        )
    finally:
        upload_runtime.reset(token)
    assert final.get("file_kind") == "invoice"
    assert not (final.get("error") or "")


@pytest.mark.asyncio
async def test_upload_graph_routes_contract():
    """合同分类进入 contract 节点。"""

    async def classify(*_args, **_kwargs) -> str:
        return "contract"

    token = upload_runtime.set({"classify": classify, "file_bytes": b"x", "db": None})
    try:
        final = await get_upload_graph().ainvoke({"user_message": "", "file_kind": ""})
    finally:
        upload_runtime.reset(token)
    assert final.get("file_kind") == "contract"


def test_after_classify_error_and_chat():
    """失败走 error，其它走 file_chat。"""
    assert after_classify({"file_kind": "error"}) == "error"
    assert after_classify({"file_kind": "chat"}) == "file_chat"
    assert after_classify({"file_kind": "invoice"}) == "invoice"


@pytest.mark.asyncio
async def test_upload_graph_classify_failure():
    """分类异常写入 error，不假装识别成功。"""

    async def classify(*_args, **_kwargs) -> str:
        raise RuntimeError("boom")

    token = upload_runtime.set({"classify": classify, "file_bytes": b"x", "db": None})
    try:
        final = await get_upload_graph().ainvoke({"user_message": "", "file_kind": ""})
    finally:
        upload_runtime.reset(token)
    assert final.get("file_kind") == "error"
    assert "boom" in (final.get("error") or "")
