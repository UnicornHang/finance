"""场景级 system_prompt 覆盖规则。"""

from app.services.llm_service import apply_system_prompt


def test_empty_prompt_keeps_original_messages():
    """未配置或空白时不改动调用方 messages。"""
    messages = [{"role": "system", "content": "默认人设"}, {"role": "user", "content": "hi"}]

    assert apply_system_prompt(messages, None) is messages
    assert apply_system_prompt(messages, "") is messages
    assert apply_system_prompt(messages, "   ") is messages


def test_custom_prompt_replaces_existing_system():
    """已有 system 时用用户配置整段替换，不叠加默认人设。"""
    messages = [
        {"role": "system", "content": "默认人设"},
        {"role": "user", "content": "hi"},
    ]

    result = apply_system_prompt(messages, "  你是审计助手  ")

    assert result[0] == {"role": "system", "content": "你是审计助手"}
    assert result[1] == {"role": "user", "content": "hi"}
    assert messages[0]["content"] == "默认人设"


def test_custom_prompt_prepends_when_no_system():
    """调用方没有 system 时前置用户提示词。"""
    messages = [{"role": "user", "content": "抽取发票"}]

    result = apply_system_prompt(messages, "只返回 JSON")

    assert result == [
        {"role": "system", "content": "只返回 JSON"},
        {"role": "user", "content": "抽取发票"},
    ]
    assert len(messages) == 1
