import { useEffect, useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { CheckCircle2, Eye, EyeOff, PlayCircle, Wrench, XCircle } from 'lucide-react'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
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
import { toolApi } from '@/api/admin'
import type { ToolConfigPayload } from '@/api/admin'
import { cn } from '@/lib/utils'
import type { LLMTestResult, ToolConfig } from '@/types'

const PROVIDER_OPTIONS = [
  { key: 'bocha', label: '博查', help: '国内检索，适合税务总局/财政部页面' },
  { key: 'tavily', label: 'Tavily', help: '有免费额度，中文官网覆盖一般' },
] as const

interface EditState {
  provider: string
  base_url: string
  api_key_input: string
  enabled: boolean
  timeout_seconds: number
  max_results: number
  fetch_pages: number
  fetch_max_chars: number
}

/** 管理端工具配置：开关、提供商、加密存储的 API Key。 */
export function ToolSettings() {
  const { data: configs, isLoading } = useQuery<ToolConfig[]>({
    queryKey: ['tool-configs'],
    queryFn: () => toolApi.listConfigs(),
  })

  const [editingName, setEditingName] = useState<string | null>(null)
  const editingCfg = configs?.find((c) => c.tool_name === editingName) || null

  return (
    <div className="space-y-6">
      {isLoading ? (
        <EmptyState icon={<Wrench className="h-5 w-5" />} title="加载中..." />
      ) : !configs || configs.length === 0 ? (
        <EmptyState
          icon={<Wrench className="h-5 w-5" />}
          title="暂无工具"
          description="当前版本仅支持权威财税检索"
        />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {configs.map((cfg) => (
            <ToolCard
              key={cfg.tool_name}
              cfg={cfg}
              onEdit={() => setEditingName(cfg.tool_name)}
            />
          ))}
        </div>
      )}

      <p className="text-body-sm text-ink-tertiary">
        API Key 仅在保存时通过 HTTPS 提交，服务端 Fernet 加密入库，列表接口只返回掩码。浏览器不保存明文。
      </p>

      <EditToolDialog
        cfg={editingCfg}
        open={!!editingCfg}
        onOpenChange={(o) => {
          if (!o) setEditingName(null)
        }}
      />
    </div>
  )
}

function ToolCard({ cfg, onEdit }: { cfg: ToolConfig; onEdit: () => void }) {
  const queryClient = useQueryClient()
  const [testResult, setTestResult] = useState<LLMTestResult | null>(null)

  const test = useMutation({
    mutationFn: () => toolApi.testSavedConfig(cfg.tool_name),
    onSuccess: (res) => setTestResult(res),
    onError: (err: { response?: { data?: { message?: string } } }) => {
      setTestResult({
        ok: false,
        message: err?.response?.data?.message || '测试失败',
        latency_ms: 0,
      })
    },
  })

  const toggle = useMutation({
    mutationFn: () =>
      toolApi.upsertConfig(cfg.tool_name, {
        provider: cfg.provider,
        base_url: cfg.base_url,
        enabled: !cfg.enabled,
        timeout_seconds: cfg.timeout_seconds,
        max_results: cfg.max_results,
        fetch_pages: cfg.fetch_pages,
        fetch_max_chars: cfg.fetch_max_chars,
      }),
    onSuccess: (updated) => {
      toast.success(updated.enabled ? '已启用工具' : '已关闭工具')
      queryClient.setQueryData<ToolConfig[]>(['tool-configs'], (prev) =>
        (prev || []).map((c) => (c.tool_name === updated.tool_name ? updated : c)),
      )
    },
    onError: (err: { response?: { data?: { message?: string } } }) => {
      toast.error(err?.response?.data?.message || '更新失败')
    },
  })

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-primary-tint text-primary text-title-lg">
              🔎
            </div>
            <div>
              <CardTitle>{cfg.label}</CardTitle>
              <CardDescription>{cfg.description}</CardDescription>
            </div>
          </div>
          {cfg.enabled ? (
            <Badge tone="success" dot>
              启用
            </Badge>
          ) : (
            <Badge tone="neutral" dot>
              关闭
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <dl className="space-y-2.5">
          <Row label="提供商" value={cfg.provider} mono />
          <Row label="Base URL" value={cfg.base_url || '默认端点'} mono subtle />
          <Row
            label="API Key"
            value={cfg.has_api_key ? cfg.api_key_masked || '****' : '未配置'}
            mono
            subtle
          />
          <div className="grid grid-cols-2 items-center gap-4">
            <Row label="原文抓取" value={`${cfg.fetch_pages}页`} />
            <Row label="超时" value={`${cfg.timeout_seconds}s`} />
          </div>
          <Row
            label="配置来源"
            value={cfg.source === 'db' ? '管理端已保存' : '环境变量'}
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
              <p className="leading-5 font-medium">
                {testResult.ok
                  ? `连通成功 (${testResult.latency_ms}ms)：${testResult.message}`
                  : `连通失败：${testResult.message}`}
              </p>
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
                对话中可检索公开财税
              </>
            ) : (
              <>
                <XCircle className="h-3.5 w-3.5 text-ink-muted" />
                已关闭，不会联网
              </>
            )}
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => toggle.mutate()}
              disabled={toggle.isPending}
            >
              {cfg.enabled ? '关闭' : '启用'}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => test.mutate()}
              disabled={test.isPending}
            >
              {test.isPending ? '测试中...' : '测试连通性'}
            </Button>
            <Button size="sm" onClick={onEdit} className="text-white">
              编辑
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function EditToolDialog({
  cfg,
  open,
  onOpenChange,
}: {
  cfg: ToolConfig | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const queryClient = useQueryClient()
  const [reveal, setReveal] = useState(false)
  const [state, setState] = useState<EditState>({
    provider: 'bocha',
    base_url: '',
    api_key_input: '',
    enabled: false,
    timeout_seconds: 15,
    max_results: 8,
    fetch_pages: 2,
    fetch_max_chars: 4000,
  })

  useEffect(() => {
    if (cfg) {
      setState({
        provider: cfg.provider || 'bocha',
        base_url: cfg.base_url || '',
        api_key_input: '',
        enabled: cfg.enabled,
        timeout_seconds: cfg.timeout_seconds,
        max_results: cfg.max_results,
        fetch_pages: cfg.fetch_pages,
        fetch_max_chars: cfg.fetch_max_chars,
      })
      setReveal(false)
    }
  }, [cfg?.tool_name, cfg?.updated_at])

  const save = useMutation({
    mutationFn: async () => {
      if (!cfg) throw new Error('No config')
      const payload: ToolConfigPayload = {
        provider: state.provider,
        base_url: state.base_url || null,
        enabled: state.enabled,
        timeout_seconds: state.timeout_seconds,
        max_results: state.max_results,
        fetch_pages: state.fetch_pages,
        fetch_max_chars: state.fetch_max_chars,
      }
      const trimmedKey = state.api_key_input.trim()
      if (trimmedKey) {
        payload.api_key = trimmedKey
      }
      return toolApi.upsertConfig(cfg.tool_name, payload)
    },
    onSuccess: (updated) => {
      toast.success('工具配置已保存')
      queryClient.setQueryData<ToolConfig[]>(['tool-configs'], (prev) =>
        (prev || []).map((c) => (c.tool_name === updated.tool_name ? updated : c)),
      )
      onOpenChange(false)
    },
    onError: (err: { response?: { data?: { message?: string } } }) => {
      toast.error(err?.response?.data?.message || '保存失败')
    },
  })

  const testDraft = useMutation({
    mutationFn: () => {
      if (!cfg) throw new Error('No config')
      const payload: ToolConfigPayload & { tool_name?: string } = {
        provider: state.provider,
        base_url: state.base_url || null,
        timeout_seconds: state.timeout_seconds,
        tool_name: cfg.tool_name,
      }
      const trimmedKey = state.api_key_input.trim()
      if (trimmedKey) payload.api_key = trimmedKey
      return toolApi.testPayload(payload)
    },
    onSuccess: (res) => {
      if (res.ok) toast.success(res.message)
      else toast.error(res.message)
    },
    onError: (err: { response?: { data?: { message?: string } } }) => {
      toast.error(err?.response?.data?.message || '测试失败')
    },
  })

  if (!cfg) return null

  const help = PROVIDER_OPTIONS.find((p) => p.key === state.provider)?.help

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>编辑工具 — {cfg.label}</DialogTitle>
          <DialogDescription>
            Key 留空则保持原值。保存后立即对当前租户生效。
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <FieldInline label="提供商">
            <Select
              value={state.provider}
              onValueChange={(provider) => setState((s) => ({ ...s, provider }))}
            >
              <SelectTrigger>
                <SelectValue placeholder="选择提供商" />
              </SelectTrigger>
              <SelectContent>
                {PROVIDER_OPTIONS.map((p) => (
                  <SelectItem key={p.key} value={p.key}>
                    {p.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </FieldInline>
          {help ? <p className="text-label-sm text-ink-tertiary">{help}</p> : null}

          <FieldInline label="API Key">
            <div className="relative">
              <Input
                type={reveal ? 'text' : 'password'}
                autoComplete="off"
                placeholder={cfg.has_api_key ? '已配置，留空则不修改' : '粘贴 API Key'}
                value={state.api_key_input}
                onChange={(e) =>
                  setState((s) => ({ ...s, api_key_input: e.target.value }))
                }
              />
              <button
                type="button"
                className="absolute right-2 top-1/2 -translate-y-1/2 text-ink-tertiary"
                onClick={() => setReveal((v) => !v)}
                aria-label={reveal ? '隐藏' : '显示'}
              >
                {reveal ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </FieldInline>

          <FieldInline label="Base URL">
            <Input
              value={state.base_url}
              placeholder="留空使用提供商默认地址"
              onChange={(e) => setState((s) => ({ ...s, base_url: e.target.value }))}
            />
          </FieldInline>

          <div className="flex items-center gap-2 py-1">
            <Checkbox
              id="tool-enabled"
              checked={state.enabled}
              onCheckedChange={(v) =>
                setState((s) => ({ ...s, enabled: v === true }))
              }
            />
            <Label htmlFor="tool-enabled">启用此工具</Label>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <FieldInline label="超时(秒)">
              <Input
                type="number"
                min={5}
                max={120}
                value={state.timeout_seconds}
                onChange={(e) =>
                  setState((s) => ({
                    ...s,
                    timeout_seconds: Number(e.target.value) || 15,
                  }))
                }
              />
            </FieldInline>
            <FieldInline label="条数">
              <Input
                type="number"
                min={1}
                max={20}
                value={state.max_results}
                onChange={(e) =>
                  setState((s) => ({
                    ...s,
                    max_results: Number(e.target.value) || 8,
                  }))
                }
              />
            </FieldInline>
            <FieldInline label="抓取原文页数">
              <Input
                type="number"
                min={0}
                max={5}
                value={state.fetch_pages}
                onChange={(e) =>
                  setState((s) => ({
                    ...s,
                    fetch_pages: Number(e.target.value) || 0,
                  }))
                }
              />
            </FieldInline>
            <FieldInline label="原文最大字数">
              <Input
                type="number"
                min={500}
                max={20000}
                value={state.fetch_max_chars}
                onChange={(e) =>
                  setState((s) => ({
                    ...s,
                    fetch_max_chars: Number(e.target.value) || 4000,
                  }))
                }
              />
            </FieldInline>
          </div>
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="secondary"
            onClick={() => testDraft.mutate()}
            disabled={testDraft.isPending}
          >
            <PlayCircle className="mr-1.5 h-4 w-4" />
            {testDraft.isPending ? '测试中...' : '试调'}
          </Button>
          <Button
            type="button"
            onClick={() => save.mutate()}
            disabled={save.isPending}
            className="text-white"
          >
            {save.isPending ? '保存中...' : '保存'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function FieldInline({
  label,
  children,
}: {
  label: string
  children: ReactNode
}) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      {children}
    </div>
  )
}

function Row({
  label,
  value,
  mono,
  subtle,
}: {
  label: string
  value: string | number
  mono?: boolean
  subtle?: boolean
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <dt className="shrink-0 text-body-sm leading-5 text-ink-tertiary">{label}</dt>
      <dd
        className={cn(
          'min-w-0 break-all text-right text-body-sm leading-5',
          mono && 'font-mono tabular-nums',
          subtle ? 'text-ink-secondary' : 'text-ink',
        )}
      >
        {value}
      </dd>
    </div>
  )
}
