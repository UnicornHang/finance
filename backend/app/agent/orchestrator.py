"""Agent 编排 - LangChain 集成（占位骨架）。"""

from app.agent.context import SessionContext
from app.agent.router import Intent, route_intent
from app.services.rag_service import rag_service


class AgentOrchestrator:
    """LangChain Agent 编排器（骨架实现）。"""

    def __init__(self):
        # TODO: 初始化 LangChain AgentExecutor、Tool 列表
        # self.llm = ChatLiteLLM(...)
        # self.tools = [ocr_tool, contract_tool, rag_tool, archive_tool]
        # self.executor = AgentExecutor(agent=..., tools=self.tools)
        pass

    async def stream(self, ctx: SessionContext, user_input: str, file=None):
        """流式处理用户输入。"""
        # 1. 意图识别
        intent = await route_intent(user_input, file_type=None)

        # 2. 路由到对应处理
        if intent == Intent.INVOICE_UPLOAD and file:
            # 异步触发 OCR 任务
            yield {
                "type": "text",
                "content": "正在识别发票...",
            }
            # 实际：触发 Celery 任务，完成后通过 WebSocket 通知
            yield {
                "type": "sidepanel",
                "payload": {"type": "invoice", "data": {}},
            }
        elif intent == Intent.POLICY_QUERY:
            # RAG 检索
            yield {"type": "text", "content": "正在检索相关制度...\n\n"}
            # 实际：从 RAG 检索 + LLM 生成
            yield {"type": "text", "content": "（示例回答）请参考《差旅补贴管理办法》第三条..."}
        else:
            # 闲聊
            yield {"type": "text", "content": "我是企业财务 AI 助手，可以帮你处理发票、查询制度、审查合同。"}

        yield {"type": "done"}


agent_orchestrator = AgentOrchestrator()