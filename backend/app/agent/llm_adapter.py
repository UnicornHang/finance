"""把租户 LLM 配置适配成 LangChain 可用的 chat 调用。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Sequence
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool

from app.services.llm_service import llm_service

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def tools_to_openai(tools: Sequence[BaseTool]) -> list[dict]:
    """StructuredTool → OpenAI tools 参数。"""
    return [convert_to_openai_tool(t) for t in tools]


def messages_to_openai(messages: Sequence[BaseMessage]) -> list[dict]:
    """LangChain 消息转为 litellm messages。"""
    out: list[dict] = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            out.append({"role": "system", "content": msg.content})
        elif isinstance(msg, HumanMessage):
            out.append({"role": "user", "content": msg.content})
        elif isinstance(msg, ToolMessage):
            out.append(
                {
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id,
                    "content": msg.content,
                }
            )
        elif isinstance(msg, AIMessage):
            item: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
            if msg.tool_calls:
                item["tool_calls"] = [
                    {
                        "id": tc.get("id") or tc.get("name"),
                        "type": "function",
                        "function": {
                            "name": tc.get("name"),
                            "arguments": _args_to_json(tc.get("args")),
                        },
                    }
                    for tc in msg.tool_calls
                ]
            out.append(item)
        else:
            role = getattr(msg, "type", "user")
            out.append({"role": "assistant" if role == "ai" else role, "content": str(msg.content)})
    return out


def _args_to_json(args: object) -> str:
    import json

    if isinstance(args, str):
        return args
    if args is None:
        return "{}"
    return json.dumps(args, ensure_ascii=False)


def history_to_messages(history: list[dict], system_prompt: str, user_content: str) -> list[BaseMessage]:
    """会话历史 + 本轮 user 组装为 LangChain 消息。"""
    msgs: list[BaseMessage] = [SystemMessage(content=system_prompt)]
    for item in history:
        role = item.get("role")
        content = item.get("content") or ""
        if role == "user":
            msgs.append(HumanMessage(content=content))
        elif role == "assistant":
            msgs.append(AIMessage(content=content))
    msgs.append(HumanMessage(content=user_content))
    return msgs


class ChatFinanceLLM:
    """租户场景模型。不持全局状态；每次请求由编排器新建。"""

    def __init__(
        self,
        *,
        scene: str,
        db: "AsyncSession | None",
        tenant_id: str | None,
        session_id: str | None = None,
        user_id: str | None = None,
    ):
        self.scene = scene
        self.db = db
        self.tenant_id = tenant_id
        self.session_id = session_id
        self.user_id = user_id

    async def ainvoke(
        self,
        messages: Sequence[BaseMessage],
        *,
        tools: Sequence[BaseTool] | None = None,
        temperature: float | None = None,
    ) -> AIMessage:
        """同步语义的一次对话调用，可带 tools。"""
        openai_msgs = messages_to_openai(messages)
        openai_tools = tools_to_openai(tools) if tools else None
        cfg = await llm_service._resolve_config(self.scene, self.db, self.tenant_id)
        if not cfg or not (cfg.get("api_key") or "").strip():
            text = llm_service._mock_response(openai_msgs)
            return AIMessage(content=text)

        content, calls = await llm_service.complete_chat_with_config(
            openai_msgs,
            cfg,
            temperature=temperature,
            apply_scene_prompt=False,
            tools=openai_tools,
            db=self.db,
            tenant_id=self.tenant_id,
            scene=self.scene,
            session_id=self.session_id,
            user_id=self.user_id,
            source="complete",
        )
        tool_calls = [
            {
                "id": c.get("id") or str(uuid4()),
                "name": c["name"],
                "args": c.get("args") or {},
            }
            for c in calls
            if c.get("name")
        ]
        return AIMessage(content=content or "", tool_calls=tool_calls)
