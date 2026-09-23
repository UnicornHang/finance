"""合同归档 API。

> **TODO(Phase B):** 完整流水线（PDF 解析 + 合规审查 + RAG 规则匹配 + 持久化）
> 留到 Phase B 接入。当前 5 个端点均为 stub。本期文件**上传**走通用
> `POST /api/v1/files/upload`，由 chat_service 在用户发送消息时根据 LLM
> 语义判断是否调用合同审查工具。
"""

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
