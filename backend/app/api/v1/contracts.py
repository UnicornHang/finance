"""合同归档 API。"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_contracts():
    """合同列表。"""
    raise NotImplementedError("待实现")


@router.post("/archive")
async def archive_contract():
    """归档合同（含合规审查结果）。"""
    raise NotImplementedError("待实现")


@router.get("/{contract_id}")
async def get_contract(contract_id: str):
    """合同详情 + 审查报告。"""
    raise NotImplementedError("待实现")


@router.post("/{contract_id}/review")
async def re_review_contract(contract_id: str):
    """重新审查合同（人工触发）。"""
    raise NotImplementedError("待实现")


@router.delete("/{contract_id}")
async def delete_contract(contract_id: str):
    """删除合同。"""
    raise NotImplementedError("待实现")