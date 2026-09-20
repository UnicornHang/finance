"""意图识别路由。"""

from enum import Enum

from app.services.llm_service import llm_service


class Intent(str, Enum):
    CHITCHAT = "chitchat"
    POLICY_QUERY = "policy_query"
    INVOICE_UPLOAD = "invoice_upload"
    CONTRACT_UPLOAD = "contract_upload"


INTENT_PROMPT = """判断用户意图，返回以下之一：
- chitchat: 闲聊
- policy_query: 制度问答
- invoice_upload: 发票上传
- contract_upload: 合同上传

用户输入：{input}
附件：{file_type}

返回 JSON：{{"intent": "...", "confidence": 0.95}}
"""


async def route_intent(input_text: str, file_type: str | None = None) -> Intent:
    """识别用户意图。"""
    import json

    # 文件类型直接判定
    if file_type == "invoice":
        return Intent.INVOICE_UPLOAD
    if file_type == "contract":
        return Intent.CONTRACT_UPLOAD

    # 文本意图识别
    prompt = INTENT_PROMPT.format(input=input_text, file_type=file_type or "none")
    result = await llm_service.invoke(
        messages=[{"role": "user", "content": prompt}],
        scene="chitchat",
        response_format={"type": "json_object"},
    )
    data = json.loads(result)
    return Intent(data.get("intent", "chitchat"))