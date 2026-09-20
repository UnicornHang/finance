"""知识库管理 API。"""

from fastapi import APIRouter, UploadFile

router = APIRouter()


@router.get("/documents")
async def list_documents():
    """文档列表。"""
    raise NotImplementedError("待实现")


@router.post("/documents")
async def upload_document(file: UploadFile):
    """上传知识库文档（异步切分 + 向量化）。"""
    raise NotImplementedError("待实现")


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    """删除文档。"""
    raise NotImplementedError("待实现")


@router.post("/documents/{doc_id}/reindex")
async def reindex_document(doc_id: str):
    """重新向量化。"""
    raise NotImplementedError("待实现")


@router.post("/test-retrieve")
async def test_retrieve():
    """检索测试：输入问题，返回召回片段。"""
    raise NotImplementedError("待实现")