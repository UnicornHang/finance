// 与后端 app/services/providers.py 保持一致
// 新增 provider 时两边同步更新

export interface ProviderDef {
  key: string
  label: string
  base_url: string
  models: string[]
  api_key_help: string
  api_key_prefix?: string
}

export const PROVIDERS: Record<string, ProviderDef> = {
  openai: {
    key: 'openai',
    label: 'OpenAI',
    base_url: 'https://api.openai.com/v1',
    models: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-3.5-turbo'],
    api_key_help: '在 https://platform.openai.com/api-keys 创建',
    api_key_prefix: 'sk-',
  },
  anthropic: {
    key: 'anthropic',
    label: 'Anthropic Claude',
    base_url: 'https://api.anthropic.com',
    models: [
      'claude-sonnet-4-5',
      'claude-opus-4-1',
      'claude-haiku-4-5',
      'claude-3-5-sonnet-latest',
    ],
    api_key_help: '在 https://console.anthropic.com/ 创建',
    api_key_prefix: 'sk-ant-',
  },
  deepseek: {
    key: 'deepseek',
    label: 'DeepSeek',
    base_url: 'https://api.deepseek.com',
    models: ['deepseek-chat', 'deepseek-reasoner'],
    api_key_help: '在 https://platform.deepseek.com/api_keys 创建',
    api_key_prefix: 'sk-',
  },
  dashscope: {
    key: 'dashscope',
    label: '通义千问（阿里云百炼）',
    base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    models: ['qwen-plus', 'qwen-turbo', 'qwen-max', 'qwen-long'],
    api_key_help: '在阿里云百炼平台 https://bailian.console.aliyun.com/ 创建',
    api_key_prefix: 'sk-',
  },
  wenxin: {
    key: 'wenxin',
    label: '文心一言（百度智能云）',
    base_url: 'https://qianfan.baidubce.com/v2',
    models: ['ernie-4.5-8k', 'ernie-4.5-turbo-8k', 'ernie-3.5-8k', 'ernie-speed-8k'],
    api_key_help: '在百度智能云千帆大模型平台创建',
  },
  zhipu: {
    key: 'zhipu',
    label: '智谱 GLM',
    base_url: 'https://open.bigmodel.cn/api/paas/v4',
    models: ['glm-4-plus', 'glm-4-air', 'glm-4-air-plus', 'glm-4-flash'],
    api_key_help: '在 https://bigmodel.cn/usercenter/apikeys 创建',
  },
  doubao: {
    key: 'doubao',
    label: '豆包（火山引擎）',
    base_url: 'https://ark.cn-beijing.volces.com/api/v3',
    models: ['doubao-pro-32k', 'doubao-lite-32k', 'doubao-pro-256k'],
    api_key_help: '在火山引擎控制台创建',
  },
  moonshot: {
    key: 'moonshot',
    label: '月之暗面 Moonshot',
    base_url: 'https://api.moonshot.cn/v1',
    models: ['moonshot-v1-128k', 'moonshot-v1-32k', 'moonshot-v1-8k'],
    api_key_help: '在 https://platform.moonshot.cn/console/api-keys 创建',
    api_key_prefix: 'sk-',
  },
  ollama: {
    key: 'ollama',
    label: 'Ollama（本地）',
    base_url: 'http://localhost:11434/v1',
    models: ['llama3.2', 'qwen2.5', 'deepseek-r1', 'gemma2'],
    api_key_help: '本地运行 Ollama 服务，API Key 填任意值即可',
  },
  custom: {
    key: 'custom',
    label: '自定义（兼容 OpenAI 协议）',
    base_url: '',
    models: [],
    api_key_help: '填写任意 OpenAI 兼容协议的 API 地址与密钥',
  },
}

export const PROVIDER_LIST: ProviderDef[] = Object.values(PROVIDERS)
