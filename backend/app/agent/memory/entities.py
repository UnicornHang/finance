"""实体抽取 - 从消息中提取结构化信息。"""

import json

from app.services.llm_service import llm_service


async def extract_entities(message: str) -> dict:
    """从单条消息中抽取实体。"""
    prompt = f"""从以下消息抽取实体，返回 JSON：

{message}

字段：
- uploaded_invoices: 发票 ID 列表
- queried_policies: 查询的制度
- pending_task: 待办任务
- user_preference: 用户偏好
"""
    result = await llm_service.invoke(
        messages=[{"role": "user", "content": prompt}],
        scene="chitchat",
        response_format={"type": "json_object"},
    )
    return json.loads(result)