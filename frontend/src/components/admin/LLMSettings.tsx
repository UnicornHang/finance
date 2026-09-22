import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { CheckCircle2, Cpu, Eye, EyeOff, PlayCircle, XCircle } from 'lucide-react'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input, Textarea } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { SectionHeader } from '@/components/ui/stat'
import { EmptyState } from '@/components/ui/table'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { llmApi } from '@/api/admin'
import type { LlmConfigPayload } from '@/api/admin'
import { PROVIDERS, PROVIDER_LIST } from '@/api/providers'
import { cn } from '@/lib/utils'
import type { LLMConfig, LLMTestResult } from '@/types'

const SCENE_LABEL: Record<string, string> = {
  chitchat: '闲聊',
  policy_query: '制度问答',
  ocr_post: '单据识别',
  contract_review: '合同审查',
}

const SCENE_DESC: Record<string, string> = {
  chitchat: '通用对话场景，处理问候与闲聊',
  policy_query: '结合 RAG 检索企业制度文档',
  ocr_post: '发票/单据 OCR 后的结构化提取',
  contract_review: '解析合同并匹配合规规则',
}

const SCENE_ICON: Record<string, string> = {
  chitchat: '💬',
  policy_query: '📚',
  ocr_post: '🧾',
  contract_review: '📜',
}

/** 同步覆盖：步长 100 / 100~32000 */
const MAX_TOKENS_STEP = 100
const MAX_TOKENS_MIN = 100
const MAX_TOKENS_MAX = 32000

/** 后端 default: system_prompt 等同置空时按 "" 提交（保留 key 不变） */
interface EditState {
  provider: string
  model: string
  base_url: string
  temperature: number
  max_tokens: number
  system_prompt: string
  /** API Key 明文（用户实际输入的值）。空字符串 = 保持原 key 不动 */
  api_key_input: string
}

export function LLMSettings() {
  const { data: configs, isLoading } = useQuery<LLMConfig[]>({
    queryKey: ['llm-configs'],
    queryFn: () => llmApi.listConfigs(),
  })

  const [editingScene, setEditingScene] = useState<string | null>(null)
  const editingCfg = configs?.find((c) => c.scene === editingScene) || null

  return (
    <div className="space-y-6">
      <SectionHeader
        title="模型"
        description="为不同业务场景配置独立的模型路由与参数"
        actions={
          <TestAllButton
            scenes={(configs || []).map((c) => c.scene)}
            disabled={!configs || configs.length === 0}
          />
        }
      />

      {isLoading ? (
        <EmptyState icon={<Cpu className="h-5 w-5" />} title="加载中..." />
      ) : !configs || configs.length === 0 ? (
        <EmptyState
          icon={<Cpu className="h-5 w-5" />}
          title="尚未配置模型"
          description="为业务场景分配 LLM 模型与路由"
        />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {configs.map((cfg) => (
            <ConfigCard
              key={cfg.id}
              cfg={cfg}
              onEdit={() => setEditingScene(cfg.scene)}
            />
          ))}
        </div>
      )}

      {/* 弹窗编辑对话框 */}
      <EditConfigDialog
        cfg={editingCfg}
        open={!!editingCfg}
        onOpenChange={(o) => {
          if (!o) setEditingScene(null)
        }}
      />
    </div>
  )
}

/* ============================================================ */

function TestAllButton({ scenes, disabled }: { scenes: string[]; disabled: boolean }) {
  const testAll = useMutation({
    mutationFn: async () => {
      return Promise.all(
        scenes.map((scene) =>
          llmApi
            .testSavedConfig(scene)
            .then((result) => ({ scene, result }))
            .catch((err: any) => ({
              scene,
              result: {
                ok: false,
                message: err?.response?.data?.message || '请求失败',
                latency_ms: 0,
              } as LLMTestResult,
            })),
        ),
      )
    },
    onSuccess: (rows) => {
      const okCount = rows.filter((r) => r.result.ok).length
      const failed = rows.filter((r) => !r.result.ok)
      if (failed.length === 0) {
        toast.success(`连通性测试全部通过：${okCount}/${rows.length}`)
      } else {
        toast.warning(
          `连通性测试：${okCount}/${rows.length} 通过。失败：${failed
            .map((r) => `${SCENE_LABEL[r.scene] || r.scene}(${r.result.message})`)
            .join('；')}`,
        )
      }
    },
    onError: () => toast.error('测试全部失败'),
  })

  return (
    <Button
      variant="secondary"
      size="md"
      onClick={() => testAll.mutate()}
      disabled={disabled || testAll.isPending}
    >
      <PlayCircle className="h-4 w-4" />
      {testAll.isPending ? '测试中...' : '测试全部'}
    </Button>
  )
}

/* ============================================================ */

function ConfigCard({
  cfg,
  onEdit,
}: {
  cfg: LLMConfig
  onEdit: () => void
}) {
  const [testResult, setTestResult] = useState<LLMTestResult | null>(null)

  const test = useMutation({
    mutationFn: () => llmApi.testSavedConfig(cfg.scene),
    onSuccess: (result) => {
      setTestResult(result)
      if (result.ok) {
        toast.success(`${SCENE_LABEL[cfg.scene] || cfg.scene} 连通成功（${result.latency_ms}ms）`)
      } else {
        toast.error(`${SCENE_LABEL[cfg.scene] || cfg.scene} 连通失败：${result.message}`)
      }
    },
    onError: (err: any) => {
      const msg = err?.response?.data?.message || '连通性测试请求失败'
      setTestResult({ ok: false, message: msg, latency_ms: 0 })
      toast.error(msg)
    },
  })

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-primary-tint text-primary text-title-lg">
              {SCENE_ICON[cfg.scene] || '🤖'}
            </div>
            <div>
              <CardTitle>{SCENE_LABEL[cfg.scene] || cfg.scene}</CardTitle>
              <CardDescription>
                {SCENE_DESC[cfg.scene] || ''}
              </CardDescription>
            </div>
          </div>
          {cfg.enabled ? (
            <Badge tone="success" dot>
              启用
            </Badge>
          ) : (
            <Badge tone="neutral" dot>
              禁用
            </Badge>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        <dl className="space-y-2.5">
          <Row label="Provider" value={cfg.provider || 'openai'} mono />
          <Row label="模型" value={cfg.model || '—'} mono />
          <Row label="Base URL" value={cfg.base_url || '—'} mono subtle />
          <div className="grid grid-cols-2 gap-4">
            <Row label="Temperature" value={cfg.temperature} mono />
            <Row label="Max Tokens" value={cfg.max_tokens} mono />
          </div>
          <Row
            label="API Key"
            value={cfg.has_api_key ? cfg.api_key_masked || '****' : '未配置'}
            mono
            subtle
          />
        </dl>

        {testResult && (
          <div
            className={cn(
              'flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-body-sm',
              testResult.ok
                ? 'border-success-border bg-success-tint text-success'
                : 'border-danger-border bg-danger-tint text-danger',
            )}
          >
            <div className="flex min-w-0 flex-1 items-center gap-2">
              {testResult.ok ? (
                <CheckCircle2 className="h-4 w-4 shrink-0" />
              ) : (
                <XCircle className="h-4 w-4 shrink-0" />
              )}
              <div className="min-w-0 flex-1">
                <p className="leading-5 font-medium">
                  {testResult.ok
                    ? `连通成功 (${testResult.latency_ms}ms)`
                    : `连通失败：${testResult.message}`}
                </p>
                {testResult.ok && testResult.message && (
                  <p
                    className="mt-1 leading-5 break-words text-ink-secondary"
                    title={testResult.message}
                  >
                    {testResult.message.length > 100
                      ? testResult.message.slice(0, 100) + '…'
                      : testResult.message}
                  </p>
                )}
              </div>
            </div>
            <button
              type="button"
              onClick={() => setTestResult(null)}
              className="shrink-0 leading-5 underline-offset-2 hover:underline"
            >
              清除
            </button>
          </div>
        )}

        <div className="flex items-center justify-between gap-2 border-t border-line-subtle pt-3">
          <span className="flex items-center gap-1.5 text-label-sm text-ink-tertiary">
            {cfg.enabled ? (
              <>
                <CheckCircle2 className="h-3.5 w-3.5 text-success" />
                当前路由到此模型
              </>
            ) : (
              <>
                <XCircle className="h-3.5 w-3.5 text-ink-muted" />
                已禁用
              </>
            )}
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => test.mutate()}
              disabled={test.isPending}
              title={
                !cfg.has_api_key
                  ? '未配置 API Key，将直接测试当前保存的配置'
                  : '使用当前保存的模型与 API Key 测试连通性'
              }
            >
              {test.isPending ? '测试中...' : '测试连通性'}
            </Button>
            {/* 编辑：默认 primary 变体自带白色文字 */}
            <Button size="sm" onClick={onEdit} className="text-white">
              编辑
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

/* ============================================================ */

function EditConfigDialog({
  cfg,
  open,
  onOpenChange,
}: {
  cfg: LLMConfig | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const queryClient = useQueryClient()
  const [state, setState] = useState<EditState>({
    provider: 'openai',
    model: '',
    base_url: '',
    temperature: 0.7,
    max_tokens: 2000,
    system_prompt: '',
    api_key_input: '',
  })

  // 每次打开或切换场景，重置表单（包含 system_prompt 持久化）
  useEffect(() => {
    if (cfg) {
      setState({
        provider: cfg.provider || 'openai',
        model: cfg.model || '',
        base_url: cfg.base_url || '',
        temperature:
          typeof cfg.temperature === 'number' ? cfg.temperature : 0.7,
        max_tokens: cfg.max_tokens || 2000,
        system_prompt: cfg.system_prompt || '',
        api_key_input: '',
      })
    }
  }, [cfg?.id, cfg?.scene])

  const save = useMutation({
    mutationFn: async () => {
      if (!cfg) throw new Error('No config')
      const payload: LlmConfigPayload = {
        provider: state.provider,
        model: state.model,
        base_url: state.base_url || null,
        temperature: state.temperature,
        max_tokens: state.max_tokens,
        system_prompt: state.system_prompt || null,
      }
      // API Key：仅当用户实际输入了新值才发送；
      // 为空字符串 → 不带 api_key 字段，后端视为保持原 key。
      const trimmedKey = state.api_key_input.trim()
      if (trimmedKey) {
        payload.api_key = trimmedKey
      }
      return llmApi.upsertConfig(cfg.scene, payload)
    },
    onSuccess: (updated) => {
      toast.success(`场景 ${SCENE_LABEL[cfg?.scene || ''] || cfg?.scene} 已保存`)
      queryClient.setQueryData<LLMConfig[]>(['llm-configs'], (prev) =>
        (prev || []).map((c) => (c.id === updated.id ? updated : c)),
      )
      onOpenChange(false)
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.message || '保存失败')
    },
  })

  const providerDef = PROVIDERS[state.provider]

  const handleProviderChange = (provider: string) => {
    const def = PROVIDERS[provider]
    setState((s) => ({
      ...s,
      provider,
      base_url: def?.base_url ?? s.base_url,
    }))
  }

  if (!cfg) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>编辑配置 — {SCENE_LABEL[cfg.scene] || cfg.scene}</DialogTitle>
          <DialogDescription>
            修改后将立即保存到当前场景，其他字段不受影响。
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <FieldInline label="Provider">
            <Select value={state.provider} onValueChange={handleProviderChange}>
              <SelectTrigger>
                <SelectValue placeholder="选择 Provider" />
              </SelectTrigger>
              <SelectContent>
                {PROVIDER_LIST.map((p) => (
                  <SelectItem key={p.key} value={p.key}>
                    {p.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </FieldInline>

          <FieldInline label="模型">
            <Input
              value={state.model}
              onChange={(e) =>
                setState((s) => ({ ...s, model: e.target.value }))
              }
              placeholder="例如：gpt-4o-mini"
              autoComplete="off"
              className="font-mono"
            />
          </FieldInline>

          <FieldInline label="Base URL">
            <Input
              value={state.base_url}
              onChange={(e) =>
                setState((s) => ({ ...s, base_url: e.target.value }))
              }
              placeholder={providerDef?.base_url || 'https://api.example.com/v1'}
              className="font-mono text-body-sm"
            />
          </FieldInline>

          <div className="grid grid-cols-2 gap-3">
            <FieldInline label="Temperature">
              <Input
                type="number"
                step="0.1"
                min="0"
                max="2"
                value={state.temperature}
                onChange={(e) =>
                  setState((s) => ({
                    ...s,
                    temperature: Number(e.target.value),
                  }))
                }
              />
            </FieldInline>
            <FieldInline label="Max Tokens">
              <Input
                type="number"
                step={MAX_TOKENS_STEP}
                min={MAX_TOKENS_MIN}
                max={MAX_TOKENS_MAX}
                value={state.max_tokens}
                onChange={(e) => {
                  const raw = Number(e.target.value)
                  if (!Number.isFinite(raw)) return
                  const clamped = Math.min(
                    MAX_TOKENS_MAX,
                    Math.max(MAX_TOKENS_MIN, Math.round(raw)),
                  )
                  setState((s) => ({ ...s, max_tokens: clamped }))
                }}
                className="tabular-nums"
              />
            </FieldInline>
          </div>

          <FieldInline label="API Key">
            <ApiKeyInput
              hasKey={cfg.has_api_key}
              masked={cfg.api_key_masked}
              value={state.api_key_input}
              onChange={(v) => setState((s) => ({ ...s, api_key_input: v }))}
            />
          </FieldInline>

          <FieldInline label="提示词">
            <Textarea
              value={state.system_prompt}
              onChange={(e) =>
                setState((s) => ({ ...s, system_prompt: e.target.value }))
              }
              placeholder="例如：你是财务助手，回答需简洁严谨..."
              rows={4}
              className="font-mono text-body-sm"
            />
          </FieldInline>
        </div>

        <DialogFooter>
          <Button
            variant="secondary"
            size="md"
            onClick={() => onOpenChange(false)}
            disabled={save.isPending}
          >
            取消
          </Button>
          <Button
            size="md"
            onClick={() => save.mutate()}
            disabled={save.isPending || !state.model.trim()}
            className="text-white"
          >
            {save.isPending ? '保存中...' : '保存'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/* ============================================================ */

function Row({
  label,
  value,
  mono = false,
  subtle = false,
}: {
  label: string
  value: React.ReactNode
  mono?: boolean
  subtle?: boolean
}) {
  return (
    <div className="flex items-center justify-between gap-3 text-body-sm">
      <dt className="text-ink-tertiary">{label}</dt>
      <dd
        className={cn(
          'truncate text-right',
          mono && 'font-mono',
          subtle && 'text-ink-tertiary text-body-sm',
        )}
      >
        {value}
      </dd>
    </div>
  )
}

function FieldInline({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <div>
      <Label className="normal-case tracking-normal text-body-sm font-medium text-ink-secondary mb-1">
        {label}
      </Label>
      {children}
    </div>
  )
}

/* ============================================================
 * ApiKeyInput：单一输入框 + 尾部显示/隐藏按钮
 *  - 不区分「保持/替换」状态：用户输入 = 替换；留空 = 保持原 key
 *  - 已有 key 时，把掩码作为 placeholder，避免泄露也方便核对
 * ============================================================ */
export function ApiKeyInput({
  hasKey,
  masked,
  value,
  onChange,
}: {
  hasKey: boolean
  masked: string | null
  value: string
  onChange: (v: string) => void
}) {
  const [reveal, setReveal] = useState(false)
  return (
    <div className="space-y-1.5">
      <div className="relative">
        <Input
          type={reveal ? 'text' : 'password'}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={
            hasKey ? masked || '****' : '粘贴厂商提供的 API Key'
          }
          className="pr-10 font-mono"
          autoComplete="off"
          spellCheck={false}
        />
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          onClick={() => setReveal((v) => !v)}
          aria-label={reveal ? '隐藏 API Key' : '显示 API Key'}
          title={reveal ? '隐藏' : '显示'}
          className="absolute right-1 top-1/2 -translate-y-1/2"
        >
          {reveal ? (
            <EyeOff className="h-4 w-4" />
          ) : (
            <Eye className="h-4 w-4" />
          )}
        </Button>
      </div>
      <p className="text-label-sm text-ink-tertiary">
        {hasKey
          ? '留空表示保持原 key 不变；输入新值会立即加密入库（旧 key 不可恢复）。'
          : '填入后将立即加密入库。'}
      </p>
    </div>
  )
}
