"""摘要更新 - 滚动压缩历史对话。"""

from app.services.llm_service import llm_service


async def update_summary(session_id: str, old_summary: str, recent_messages: list[dict]) -> str:
    """更新会话摘要。"""
    msgs_text = "\n".join(f"{m['role']}: {m['content']}" for m in recent_messages[-20:])
    prompt = f"""旧摘要：{old_summary}

最近对话：
{msgs_text}

请更新摘要，保留关键信息：上传的单据、查询的制度、待办任务、用户偏好。
控制在 200 字以内。
"""
    return await llm_service.invoke(
        messages=[{"role": "user", "content": prompt}],
        scene="chitchat",
    )