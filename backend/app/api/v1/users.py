"""用户管理 API（管理员权限）。"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_users():
    """用户列表。"""
    raise NotImplementedError("待实现")


@router.post("/")
async def create_user():
    """创建用户。"""
    raise NotImplementedError("待实现")


@router.patch("/{user_id}")
async def update_user(user_id: str):
    """更新用户（角色/部门/状态）。"""
    raise NotImplementedError("待实现")


@router.post("/{user_id}/reset-password")
async def reset_password(user_id: str):
    """重置密码。"""
    raise NotImplementedError("待实现")


@router.delete("/{user_id}")
async def delete_user(user_id: str):
    """删除/停用用户。"""
    raise NotImplementedError("待实现")