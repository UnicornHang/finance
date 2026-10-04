"""ChatService 流式响应测试（纯 mock，隔离数据库与外部依赖）。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.chat_service import ChatService, SYSTEM_PROMPT


def _make_msg(role="assistant", content=None):
    return SimpleNamespace(role=role, content=content)


@pytest.fixture
def mock_db():
    """模拟 AsyncSession：execute 链式返回 scalars().all()。"""
    db = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.get = AsyncMock()
    db.add = MagicMock()

    # 构造 execute -> scalars -> [msgs] 链
    scalars_mock = MagicMock()
    scalars_mock.all = MagicMock(return_value=[])  # 默认空
    execute_result = MagicMock()
    execute_result.scalars = MagicMock(return_value=scalars_mock)
    db.execute = AsyncMock(return_value=execute_result)

    db._scalars_mock = scalars_mock  # 测试中可修改 all 返回值
    db._execute_result = execute_result
    return db


@pytest.fixture
def mock_user():
    return SimpleNamespace(id="user-uuid-123", tenant_id="tenant-uuid-456")


@pytest.fixture
def mock_session():
    return SimpleNamespace(
        id="session-uuid-789",
        user_id="user-uuid-123",
        tenant_id="tenant-uuid-456",
        title=None,
    )


@pytest.mark.asyncio
async def test_load_recent_messages_excludes_empty(mock_db):
    """加载历史时排除空内容。"""
    # DB 按 created_at desc 返回，最新的先
    msgs = [
        _make_msg(role="assistant", content="hi"),  # 最新
        _make_msg(role="assistant", content=None),  # 空内容应被排除
        _make_msg(role="user", content="hello"),  # 最早
    ]
    mock_db._scalars_mock.all = MagicMock(return_value=msgs)

    service = ChatService()
    result = await service.load_recent_messages(mock_db, "session-id")

    assert len(result) == 2
    # 反转后：时间正序（user 在前，assistant 在后）
    assert result[0]["role"] == "user"
    assert result[0]["content"] == "hello"
    assert result[1]["role"] == "assistant"
    assert result[1]["content"] == "hi"


@pytest.mark.asyncio
async def test_stream_response_yields_events(mock_db, mock_user, mock_session):
    """验证流式响应产出正确的事件序列。"""

    async def mock_llm_stream(messages, scene, **kwargs):
        for chunk in ["你", "好", "，", "我是", "AI"]:
            yield chunk

    with patch("app.services.chat_service.llm_config_service") as mock_cfg_svc:
        mock_cfg_svc.resolve = AsyncMock(return_value=None)
        with patch("app.services.chat_service.llm_service") as mock_llm:
            mock_llm.stream = mock_llm_stream

            with patch("app.services.chat_service.session_service") as mock_session_svc:
                mock_session_svc.verify_access = AsyncMock(return_value=mock_session)

                service = ChatService()
                service.save_message = AsyncMock()

                events = []
                async for event in service.stream_response(
                    mock_db, mock_user, mock_session.id, "hello"
                ):
                    events.append(event)

    # 验证事件类型序列
    event_types = [e["type"] for e in events]
    assert "text" in event_types
    assert event_types[-1] == "done"

    # 验证文本 chunk 拼接为完整消息
    text_chunks = [e["content"] for e in events if e["type"] == "text"]
    full_text = "".join(text_chunks)
    assert full_text == "你好，我是AI"

    # save_message 至少被调用 2 次（user + assistant）
    assert service.save_message.call_count >= 2


@pytest.mark.asyncio
async def test_stream_response_handles_llm_error(mock_db, mock_user, mock_session):
    """LLM 调用失败时 yield error 事件。"""

    async def failing_llm_stream(messages, scene, **kwargs):
        raise RuntimeError("API rate limit")
        yield  # noqa: 让生成器标记为 async generator

    with patch("app.services.chat_service.llm_config_service") as mock_cfg_svc:
        mock_cfg_svc.resolve = AsyncMock(return_value=None)
        with patch("app.services.chat_service.llm_service") as mock_llm:
            mock_llm.stream = failing_llm_stream

            with patch("app.services.chat_service.session_service") as mock_session_svc:
                mock_session_svc.verify_access = AsyncMock(return_value=mock_session)

                service = ChatService()
                service.save_message = AsyncMock()

                events = []
                async for event in service.stream_response(
                    mock_db, mock_user, mock_session.id, "hello"
                ):
                    events.append(event)

    error_events = [e for e in events if e["type"] == "error"]
    assert len(error_events) == 1
    assert "API rate limit" in error_events[0]["message"]


@pytest.mark.asyncio
async def test_auto_title_truncates_long_message():
    """长消息自动截断为标题。"""
    session = SimpleNamespace(title=None)
    long_msg = "x" * 100  # 100 字符

    # 单独构造可被 await 的 commit
    db = MagicMock()
    db.commit = AsyncMock()

    service = ChatService()
    await service.auto_title(db, session, long_msg)

    assert session.title is not None
    assert len(session.title) <= 33  # 30 + "…"
    assert session.title.endswith("…")


def test_system_prompt_contains_brand():
    """系统提示词包含品牌标识。"""
    assert "MoFan" in SYSTEM_PROMPT
    assert "魔方财务科技" in SYSTEM_PROMPT
    assert "财务" in SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_stream_uses_custom_system_prompt(mock_db, mock_user, mock_session):
    """用户配置了场景提示词时，发给模型的 system 必须是用户原文。"""
    captured: dict = {}

    async def mock_llm_stream(messages, scene, **kwargs):
        captured["messages"] = messages
        yield "ok"

    with patch("app.services.chat_service.llm_config_service") as mock_cfg_svc:
        mock_cfg_svc.resolve = AsyncMock(
            return_value={"system_prompt": "你叫MoFan，是魔方财务科技顾问。"}
        )
        with patch("app.services.chat_service.llm_service") as mock_llm:
            mock_llm.stream = mock_llm_stream
            with patch("app.services.chat_service.session_service") as mock_session_svc:
                mock_session_svc.verify_access = AsyncMock(return_value=mock_session)
                service = ChatService()
                service.save_message = AsyncMock()
                async for _ in service.stream_response(
                    mock_db, mock_user, mock_session.id, "你是谁？"
                ):
                    pass

    assert captured["messages"][0]["role"] == "system"
    assert captured["messages"][0]["content"] == "你叫MoFan，是魔方财务科技顾问。"
    assert "小财" not in captured["messages"][0]["content"]


@pytest.mark.asyncio
async def test_stream_public_tax_searches_and_cites(mock_db, mock_user, mock_session):
    """公开财税问题先检索再生成，并推送 status 事件。"""
    captured: dict = {}

    async def mock_llm_stream(messages, scene, **kwargs):
        captured["messages"] = messages
        captured["scene"] = scene
        yield "根据检索"

    search_payload = {
        "ok": True,
        "provider": "bocha",
        "query": "q",
        "hits": [
            {
                "title": "国家税务总局公告",
                "url": "https://www.chinatax.gov.cn/a",
                "snippet": "小微企业优惠",
                "published_at": "2026-03-01",
                "source_kind": "official",
            }
        ],
        "pages": [
            {
                "title": "国家税务总局公告",
                "url": "https://www.chinatax.gov.cn/a",
                "text": "对小型微利企业减免企业所得税",
            }
        ],
        "error": None,
    }

    with patch("app.services.chat_service.llm_config_service") as mock_cfg_svc:
        mock_cfg_svc.resolve = AsyncMock(return_value=None)
        with patch("app.services.chat_service.llm_service") as mock_llm:
            mock_llm.stream = mock_llm_stream
            with patch("app.services.chat_service.session_service") as mock_session_svc:
                mock_session_svc.verify_access = AsyncMock(return_value=mock_session)
                with patch("app.services.chat_service.rag_service") as mock_rag:
                    mock_rag.retrieve = AsyncMock(return_value=[])
                    with patch(
                        "app.services.chat_service.official_policy_service"
                    ) as mock_policy:
                        mock_policy.search_and_fetch = AsyncMock(
                            return_value=search_payload
                        )
                        service = ChatService()
                        service.save_message = AsyncMock()
                        events = []
                        async for event in service.stream_response(
                            mock_db,
                            mock_user,
                            mock_session.id,
                            "广州地区有哪些企业所得税税收优惠政策？",
                        ):
                            events.append(event)

    assert any(e.get("type") == "status" for e in events)
    assert captured["messages"][0]["role"] == "system"
    assert "权威网站" in captured["messages"][0]["content"]
    user_content = captured["messages"][-1]["content"]
    assert "国家税务总局公告" in user_content
    assert "https://www.chinatax.gov.cn/a" in user_content
    tool_kw = service.save_message.call_args.kwargs
    assert tool_kw.get("tool_calls", {}).get("tool") == "search_official_policy"