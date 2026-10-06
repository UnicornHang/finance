"""ChatFinanceLLM 消息转换。"""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agent.llm_adapter import history_to_messages, messages_to_openai


def test_history_to_messages_order():
    """system + 历史 + 本轮 user。"""
    msgs = history_to_messages(
        [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "ok"}],
        "人设",
        "下一问",
    )
    assert isinstance(msgs[0], SystemMessage)
    assert msgs[0].content == "人设"
    assert isinstance(msgs[-1], HumanMessage)
    assert msgs[-1].content == "下一问"


def test_history_to_messages_does_not_drop_extra_items():
    """裁剪由调用方完成，适配器保留全部传入历史。"""
    history = [{"role": "user", "content": str(i)} for i in range(21)]
    msgs = history_to_messages(history, "人设", "下一问")
    # system + 21 条历史 + 本轮
    assert len(msgs) == 23
    assert msgs[1].content == "0"
    assert msgs[-2].content == "20"


def test_messages_to_openai_tool_calls():
    """AIMessage.tool_calls 转 OpenAI 结构。"""
    ai = AIMessage(
        content="",
        tool_calls=[{"id": "1", "name": "query_policy", "args": {"question": "差旅"}}],
    )
    out = messages_to_openai([ai])
    assert out[0]["role"] == "assistant"
    assert out[0]["tool_calls"][0]["function"]["name"] == "query_policy"
