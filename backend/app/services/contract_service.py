"""合同服务 - 解析 + 审查 + 风险评估。"""

import re

from app.services.llm_service import llm_service
from app.services.rag_service import rag_service


# ================ 敏感字段脱敏 ================

def mask_sensitive(text: str) -> str:
    """脱敏处理：税号、银行账号、手机号、身份证。"""
    text = re.sub(r"\d{15,20}", "[TAX_ID]", text)
    text = re.sub(r"\d{16,19}", "[BANK_ACCOUNT]", text)
    text = re.sub(r"1[3-9]\d{9}", "[PHONE]", text)
    text = re.sub(r"\d{17}[\dXx]", "[ID_CARD]", text)
    return text


# ================ 合同审查 ================

async def review_contract(text_content: str, tenant_id: str, db) -> dict:
    """审查合同合规性。

    流程：脱敏 → RAG 检索规则 → LLM 审查 → 结构化结果
    """
    from sqlalchemy.ext.asyncio import AsyncSession

    assert isinstance(db, AsyncSession)

    # 1. 脱敏
    masked = mask_sensitive(text_content)

    # 2. 检索规则
    rules = await rag_service.retrieve_rules(db, tenant_id)

    # 3. LLM 审查
    rules_text = "\n".join(f"- {r}" for r in rules)
    prompt = f"""你是合同合规审查专家。请根据以下规则审查合同。

[规则]
{rules_text}

[合同内容]
{masked}

返回 JSON：
{{
  "violations": [{{"clause": "...", "issue": "...", "severity": "high/medium/low"}}],
  "risk_level": "high/medium/low",
  "summary": "..."
}}
"""
    import json

    result = await llm_service.invoke(
        messages=[{"role": "user", "content": prompt}],
        scene="contract_review",
        response_format={"type": "json_object"},
    )
    return json.loads(result)