"""供应商错误到用户文案。"""

from app.services.llm_service import user_facing_llm_error


def test_quota_exhausted_is_actionable():
    exc = Exception(
        "APIError: OpenAIException - Free quota exhausted. "
        "To continue accessing the model on a paid basis, please add funds "
        'or disable the "use free tier only" mode.'
    )
    text = user_facing_llm_error(exc)
    assert text is not None
    assert "免费额度" in text
    assert "编排中断" not in text


def test_unknown_error_stays_none():
    assert user_facing_llm_error(RuntimeError("db down")) is None
