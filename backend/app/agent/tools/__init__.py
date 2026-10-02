"""LangChain Tools。"""

from langchain_core.tools import tool

from app.services.invoice_vision_service import invoice_vision_service


@tool
async def ocr_invoice(file_url: str) -> dict:
    """用通用大模型识别发票图片/文件，返回结构化字段。不调用 OCR 引擎。"""
    result, _source = await invoice_vision_service.recognize(b"", filename=file_url)
    return {
        "invoice_title": result.invoice_title,
        "company": result.company,
        "tax_id": result.tax_id,
        "amount_incl_tax": result.amount_incl_tax,
        # ...
    }


@tool
async def query_policy(question: str, tenant_id: str) -> str:
    """查询企业制度（RAG 检索知识库）。"""
    from app.core.database import async_session_factory
    from app.services.rag_service import rag_service

    async with async_session_factory() as db:
        hits = await rag_service.retrieve(
            db, question, tenant_id, top_k=5, doc_type=None
        )
    if not hits:
        return "知识库未召回到相关制度片段。"
    parts: list[str] = []
    for h in hits:
        title = h.get("title") or "未命名"
        score = float(h.get("score") or 0)
        body = (h.get("content") or "").strip()
        parts.append(f"《{title}》(score={score:.3f})\n{body}")
    return "\n\n---\n\n".join(parts)


@tool
async def archive_invoice(invoice_data: dict, user_id: str) -> dict:
    """归档发票到数据库。"""
    # TODO: 接入 InvoiceService
    return {"status": "archived", "invoice_id": "placeholder"}


@tool
async def review_contract(file_url: str, tenant_id: str) -> dict:
    """审查合同合规性。"""
    from app.services.contract_service import review_contract
    # TODO: 完整实现
    return {"risk_level": "medium", "violations": []}


ALL_TOOLS = [ocr_invoice, query_policy, archive_invoice, review_contract]
