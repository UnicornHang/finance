"""LLM Provider 注册表。

每个 provider 包含：
- base_url: 默认 API 根地址
- models: 热门模型列表（按推荐顺序）
- supports_stream: 是否支持流式（LiteLLM 透传）
- api_key_help: 用户引导文案

新增 provider 只需在这里追加，UI 自动出现。
"""

PROVIDERS: dict[str, dict] = {
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "models": [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "gpt-3.5-turbo",
        ],
        "api_key_help": "在 https://platform.openai.com/api-keys 创建",
        "api_key_prefix": "sk-",
        "supports_stream": True,
    },
    "anthropic": {
        "label": "Anthropic Claude",
        "base_url": "https://api.anthropic.com",
        "models": [
            "claude-sonnet-4-5",
            "claude-opus-4-1",
            "claude-haiku-4-5",
            "claude-3-5-sonnet-latest",
        ],
        "api_key_help": "在 https://console.anthropic.com/ 创建",
        "api_key_prefix": "sk-ant-",
        "supports_stream": True,
    },
    "deepseek": {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "models": [
            "deepseek-chat",
            "deepseek-reasoner",
        ],
        "api_key_help": "在 https://platform.deepseek.com/api_keys 创建",
        "api_key_prefix": "sk-",
        "supports_stream": True,
    },
    "dashscope": {
        "label": "通义千问（阿里云百炼）",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": [
            "qwen-plus",
            "qwen-turbo",
            "qwen-max",
            "qwen-long",
        ],
        "api_key_help": "在阿里云百炼平台 https://bailian.console.aliyun.com/ 创建",
        "api_key_prefix": "sk-",
        "supports_stream": True,
    },
    "wenxin": {
        "label": "文心一言（百度智能云）",
        "base_url": "https://qianfan.baidubce.com/v2",
        "models": [
            "ernie-4.5-8k",
            "ernie-4.5-turbo-8k",
            "ernie-3.5-8k",
            "ernie-speed-8k",
        ],
        "api_key_help": "在百度智能云千帆大模型平台 https://console.bce.baidu.com/qianfan/ 创建",
        "api_key_prefix": "",
        "supports_stream": True,
    },
    "zhipu": {
        "label": "智谱 GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": [
            "glm-4-plus",
            "glm-4-air",
            "glm-4-air-plus",
            "glm-4-flash",
        ],
        "api_key_help": "在 https://bigmodel.cn/usercenter/apikeys 创建",
        "api_key_prefix": "",
        "supports_stream": True,
    },
    "doubao": {
        "label": "豆包（火山引擎）",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "models": [
            "doubao-pro-32k",
            "doubao-lite-32k",
            "doubao-pro-256k",
        ],
        "api_key_help": "在火山引擎 https://www.volcengine.com/product/doubao 创建",
        "api_key_prefix": "",
        "supports_stream": True,
    },
    "moonshot": {
        "label": "月之暗面 Moonshot",
        "base_url": "https://api.moonshot.cn/v1",
        "models": [
            "moonshot-v1-128k",
            "moonshot-v1-32k",
            "moonshot-v1-8k",
        ],
        "api_key_help": "在 https://platform.moonshot.cn/console/api-keys 创建",
        "api_key_prefix": "sk-",
        "supports_stream": True,
    },
    "ollama": {
        "label": "Ollama（本地）",
        "base_url": "http://localhost:11434/v1",
        "models": [
            "llama3.2",
            "qwen2.5",
            "deepseek-r1",
            "gemma2",
        ],
        "api_key_help": "本地运行 Ollama 服务，无需 API Key（可填任意值如 'ollama'）",
        "api_key_prefix": "",
        "supports_stream": True,
    },
    "custom": {
        "label": "自定义（兼容 OpenAI 协议）",
        "base_url": "",
        "models": [],
        "api_key_help": "填写任意 OpenAI 兼容协议的 API 地址与密钥",
        "api_key_prefix": "",
        "supports_stream": True,
    },
}


# 业务场景 -> 友好名称 + 默认参数
SCENES: dict[str, dict] = {
    "chitchat": {
        "label": "日常对话",
        "description": "闲聊、企业财务通用问答",
        "default_temperature": 0.7,
        "default_max_tokens": 2000,
    },
    "policy_query": {
        "label": "制度问答（RAG）",
        "description": "基于企业知识库回答差旅/报销/审批制度等问题",
        "default_temperature": 0.3,
        "default_max_tokens": 2000,
    },
    "ocr_post": {
        "label": "单据识别后处理",
        "description": "对 OCR 提取结果做结构化、补全字段",
        "default_temperature": 0.1,
        "default_max_tokens": 1500,
    },
    "contract_review": {
        "label": "合同审查",
        "description": "识别合同条款风险、给出修改建议",
        "default_temperature": 0.2,
        "default_max_tokens": 4000,
    },
}


def get_provider_list() -> list[dict]:
    """返回 provider 列表（供前端渲染下拉框）。"""
    return [
        {"key": key, "label": cfg["label"], "base_url": cfg["base_url"], "models": cfg["models"]}
        for key, cfg in PROVIDERS.items()
    ]


def get_scene_list() -> list[dict]:
    """返回场景列表。"""
    return [
        {"key": key, **{k: v for k, v in cfg.items() if k != "default_temperature"}}
        | {"default_temperature": cfg["default_temperature"]}
        for key, cfg in SCENES.items()
    ]
