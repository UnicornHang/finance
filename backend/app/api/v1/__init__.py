"""API v1 路由聚合。"""

from fastapi import APIRouter

from app.api.v1 import auth, chat, contracts, files, invoices, kb, llm, sessions, users

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
api_router.include_router(invoices.router, prefix="/invoices", tags=["invoices"])
api_router.include_router(contracts.router, prefix="/contracts", tags=["contracts"])
api_router.include_router(files.router, prefix="/files", tags=["files"])
api_router.include_router(kb.router, prefix="/kb", tags=["kb"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(llm.router, prefix="/llm", tags=["llm"])