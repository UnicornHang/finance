"""发票归档 API。"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_invoices():
    """发票列表（支持筛选、分页）。"""
    raise NotImplementedError("待实现")


@router.post("/archive")
async def archive_invoice():
    """归档发票（用户确认侧弹窗后调用）。"""
    raise NotImplementedError("待实现")


@router.get("/{invoice_id}")
async def get_invoice(invoice_id: str):
    """发票详情。"""
    raise NotImplementedError("待实现")


@router.patch("/{invoice_id}")
async def update_invoice(invoice_id: str):
    """修改发票字段。"""
    raise NotImplementedError("待实现")


@router.delete("/{invoice_id}")
async def delete_invoice(invoice_id: str):
    """软删发票。"""
    raise NotImplementedError("待实现")


@router.get("/{invoice_id}/file")
async def download_invoice_file(invoice_id: str):
    """下载发票原件（鉴权后临时 URL）。"""
    raise NotImplementedError("待实现")