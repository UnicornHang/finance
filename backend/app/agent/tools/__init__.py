"""LangChain Tools。"""

from langchain_core.tools import tool

from app.services.ocr_service import get_ocr_service


@tool
async def ocr_invoice(file_url: str) -> dict:
    """识别发票图片，返回结构化字段。"""
    ocr = get_ocr_service()
    # 实际：从 file_url 下载文件再识别
    result = await ocr.recognize_invoice(b"")
    return {
        "invoice_title": result.invoice_title,
        "company": result.company,
        "tax_id": result.tax_id,
        "amount_incl_tax": result.amount_incl_tax,
        # ...
    }


@tool
async def query_policy(question: str, tenant_id: str) -> str:
    """查询企业制度。"""
    # TODO: 接入 RAG
    return f"（待实现）{question}"


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