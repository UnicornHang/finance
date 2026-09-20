"""LLM 服务 - 优先读 DB 配置，env 兜底。

调用链路：
1. 尝试从 llm_configs 表读取配置（带 60s 内存缓存）
2. 没有或 disabled 时，从 settings（env）兜底
3. 都没有则进入 mock 模式（演示用）
"""

import asyncio
import logging
from typing import AsyncGenerator, TYPE_CHECKING

from app.config import settings
from app.services.llm_config_service import llm_config_service

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


logger = logging.getLogger(__name__)


SCENE_CONFIG_MAP = {
    "chitchat": ("llm_chitchat_model", "llm_chitchat_api_key", "llm_chitchat_base_url"),
    "policy_query": ("llm_policy_model", "llm_policy_api_key", "llm_policy_base_url"),
    "ocr_post": ("llm_ocr_model", "llm_ocr_api_key", "llm_ocr_base_url"),
    "contract_review": ("llm_contract_model", "llm_contract_api_key", "llm_contract_base_url"),
}


class LLMService:
    """LLM 统一调度，支持 DB 配置 + 流式 + 多场景。"""

    async def _resolve_config(
        self, scene: str, db: "AsyncSession | None" = None, tenant_id: str | None = None
    ) -> dict | None:
        """合并配置：DB > env。

        返回 {provider, model, api_key, base_url, temperature, max_tokens, timeout}
        若全部没有则返回 None（上层走 mock）。
        """
        # 1. DB 优先
        if db is not None and tenant_id:
            cfg = await llm_config_service.resolve(db, tenant_id, scene)
            if cfg:
                return cfg

        # 2. env 兜底
        if scene not in SCENE_CONFIG_MAP:
            return None
        model_attr, key_attr, url_attr = SCENE_CONFIG_MAP[scene]
        model = getattr(settings, model_attr)
        api_key = getattr(settings, key_attr)
        base_url = getattr(settings, url_attr)
        if not api_key:
            return None

        return {
            "provider": "openai",  # 默认按 OpenAI 兼容协议
            "model": model,
            "api_key": api_key,
            "base_url": base_url,
            "temperature": 0.7,
            "max_tokens": 2000,
            "timeout": 30,
        }

    async def invoke(
        self,
        messages: list[dict],
        scene: str = "chitchat",
        db: "AsyncSession | None" = None,
        tenant_id: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """同步调用 LLM。"""
        from litellm import acompletion

        cfg = await self._resolve_config(scene, db, tenant_id)
        if not cfg:
            return self._mock_response(messages)

        response = await acompletion(
            model=cfg["model"],
            messages=messages,
            api_key=cfg["api_key"],
            api_base=cfg["base_url"] or None,
            temperature=temperature if temperature is not None else cfg["temperature"],
            max_tokens=max_tokens or cfg["max_tokens"],
        )
        return response.choices[0].message.content

    async def stream(
        self,
        messages: list[dict],
        scene: str = "chitchat",
        db: "AsyncSession | None" = None,
        tenant_id: str | None = None,
        temperature: float | None = None,
    ) -> AsyncGenerator[str, None]:
        """流式调用，逐 chunk 产出文本。

        未配置 API Key 时进入 mock 模式，逐字符返回演示响应。
        """
        cfg = await self._resolve_config(scene, db, tenant_id)
        if not cfg:
            async for chunk in self._mock_stream(messages):
                yield chunk
            return

        from litellm import acompletion

        try:
            response = await acompletion(
                model=cfg["model"],
                messages=messages,
                api_key=cfg["api_key"],
                api_base=cfg["base_url"] or None,
                temperature=temperature if temperature is not None else cfg["temperature"],
                stream=True,
                timeout=cfg["timeout"],
            )
            async for chunk in response:
                content = chunk.choices[0].delta.content
                if content:
                    yield content
        except Exception as exc:
            logger.exception("LLM 流式调用失败: %s", exc)
            yield f"\n\n[LLM 调用失败: {exc}]"

    async def test_connectivity(
        self,
        provider: str,
        model: str,
        api_key: str,
        base_url: str | None = None,
    ) -> dict:
        """连通性测试：使用指定 provider/model 调用一次。

        返回 {ok: bool, message: str, latency_ms: int}。
        """
        from litellm import acompletion

        from app.services.providers import PROVIDERS

        if not api_key:
            return {"ok": False, "message": "API Key 不能为空", "latency_ms": 0}

        prov_cfg = PROVIDERS.get(provider, {})
        resolved_base_url = base_url or prov_cfg.get("base_url", "")

        try:
            start = asyncio.get_event_loop().time()
            response = await acompletion(
                model=model,
                messages=[{"role": "user", "content": "ping"}],
                api_key=api_key,
                api_base=resolved_base_url or None,
                max_tokens=8,
                timeout=15,
            )
            elapsed_ms = int((asyncio.get_event_loop().time() - start) * 1000)
            content = response.choices[0].message.content
            return {
                "ok": True,
                "message": f"连通成功，模型返回：{content[:50]}",
                "latency_ms": elapsed_ms,
            }
        except Exception as exc:
            logger.warning("LLM 连通性测试失败: %s", exc)
            return {"ok": False, "message": f"连通失败：{exc}", "latency_ms": 0}

    # ================ Mock Fallback ================

    async def _mock_stream(self, messages: list[dict]) -> AsyncGenerator[str, None]:
        """演示模式流式输出。未配置任何 LLM 时启用。"""
        user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_msg = m.get("content", "")
                break

        response = (
            f"👋 你好！我是企业财务 AI 助手 **¥ 小财**。\n\n"
            f"你刚才说：「{user_msg}」\n\n"
            f"---\n\n"
            f"⚠️ **当前为演示模式**\n\n"
            f"未检测到 LLM 配置。请管理员进入 **系统设置 → LLM 配置** 完成配置：\n\n"
            f"- 选择服务提供商（OpenAI / DeepSeek / 通义千问 / 文心一言 / 智谱 / 豆包 / 自定义）\n"
            f"- 填入对应 API Key\n"
            f"- 选择模型\n"
            f"- 点击「保存」并「测试连通性」\n\n"
            f"启用后即可使用完整 AI 能力。\n\n"
            f"---\n\n"
            f"**我可以帮你**（配置完成后即可使用）：\n\n"
            f"- 🧾 发票识别与归档\n"
            f"- 📜 合同合规审查\n"
            f"- 💬 制度问答（基于知识库）"
        )

        for char in response:
            await asyncio.sleep(0.015)
            yield char

    def _mock_response(self, messages: list[dict]) -> str:
        """演示模式同步输出。"""
        user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_msg = m.get("content", "")
                break
        return f"（演示模式）收到：「{user_msg}」。请管理员配置 LLM 启用完整能力。"


llm_service = LLMService()
