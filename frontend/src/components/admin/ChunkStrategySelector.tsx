import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { CHUNK_STRATEGY_CARDS } from '@/components/admin/kbMeta'
import type { KbChunkConfig, KbIndexSettings } from '@/types'

type ChunkStrategySelectorProps = {
  value: KbChunkConfig
  settings?: KbIndexSettings
  onChange: (next: KbChunkConfig) => void
}

/** 四种切分策略与各自参数，上传和重新索引共用。 */
export function ChunkStrategySelector({
  value,
  settings,
  onChange,
}: ChunkStrategySelectorProps) {
  const strategies = settings?.chunk_strategies?.length
    ? settings.chunk_strategies
    : [...CHUNK_STRATEGY_CARDS]

  /** 只更新一个参数，保留其余切分配置。 */
  const patch = (partial: Partial<KbChunkConfig>) => {
    onChange({ ...value, ...partial })
  }

  return (
    <section className="space-y-3">
      <div>
        <h3 className="text-body-sm font-semibold text-ink">
          这篇文档打算怎么切开？
        </h3>
        <p className="mt-1 text-label-sm text-ink-tertiary">
          四种策略使用不同边界规则；重新索引时也可以切换。
        </p>
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        {strategies.map((strategy) => {
          const selected = value.chunkStrategy === strategy.value
          return (
            <button
              key={strategy.value}
              type="button"
              onClick={() => patch({ chunkStrategy: strategy.value })}
              className={[
                'rounded-lg border px-3 py-3 text-left transition-colors',
                selected
                  ? 'border-primary bg-primary-tint/40'
                  : 'border-line-subtle bg-canvas hover:border-primary/40',
              ].join(' ')}
            >
              <div className="flex items-center gap-2">
                <p className="text-body-sm font-medium text-ink">
                  {strategy.label}
                </p>
                {strategy.recommended && (
                  <span className="rounded bg-primary-tint px-1.5 py-0.5 text-label-sm text-primary">
                    推荐
                  </span>
                )}
              </div>
              {strategy.suited && (
                <p className="mt-1 text-label-sm text-ink-secondary">
                  适合：{strategy.suited}
                </p>
              )}
              <p className="mt-1 text-label-sm text-ink-tertiary">
                {strategy.how}
              </p>
              {strategy.visual && strategy.visual.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {strategy.visual.map((item) => (
                    <span
                      key={item}
                      className="rounded border border-line-subtle bg-surface px-1.5 py-0.5 text-label-sm text-ink-tertiary"
                    >
                      {item}
                    </span>
                  ))}
                </div>
              )}
              {strategy.example && (
                <p className="mt-2 text-label-sm text-ink-tertiary">
                  例如：{strategy.example}
                </p>
              )}
              {strategy.cost_hint && (
                <p className="mt-1 text-label-sm text-ink-tertiary">
                  {strategy.cost_hint}
                </p>
              )}
            </button>
          )
        })}
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="kb-chunk-size">
            {value.chunkStrategy === 'parent_child'
              ? '检索子块最大字数'
              : value.chunkStrategy === 'semantic'
                ? '语义块基础字数'
                : '每块最大字数'}
          </Label>
          <Input
            id="kb-chunk-size"
            type="number"
            min={100}
            max={value.chunkStrategy === 'parent_child' ? 1000 : 4000}
            value={value.chunkSize}
            onChange={(event) =>
              patch({ chunkSize: Number(event.target.value) || 400 })
            }
          />
        </div>

        {value.chunkStrategy !== 'semantic' && (
          <div className="space-y-1.5">
            <Label htmlFor="kb-chunk-overlap">相邻块重叠字数</Label>
            <Input
              id="kb-chunk-overlap"
              type="number"
              min={0}
              max={2000}
              value={value.chunkOverlap}
              onChange={(event) =>
                patch({ chunkOverlap: Number(event.target.value) || 0 })
              }
            />
          </div>
        )}

        {value.chunkStrategy === 'parent_child' && (
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="kb-parent-size">回答父块最大字数</Label>
            <Input
              id="kb-parent-size"
              type="number"
              min={200}
              max={8000}
              value={value.parentSize}
              onChange={(event) =>
                patch({ parentSize: Number(event.target.value) || 1200 })
              }
            />
            <p className="text-label-sm text-ink-tertiary">
              父块应明显大于子块；命中子块后，回答阶段会扩展为父块。
            </p>
          </div>
        )}

        {value.chunkStrategy === 'semantic' && (
          <div className="space-y-1.5">
            <Label htmlFor="kb-semantic-th">
              话题变化灵敏度（0.15–0.85）
            </Label>
            <Input
              id="kb-semantic-th"
              type="number"
              min={0.15}
              max={0.85}
              step={0.05}
              value={value.semanticThreshold}
              onChange={(event) =>
                patch({
                  semanticThreshold: Number(event.target.value) || 0.45,
                })
              }
            />
            <p className="text-label-sm text-ink-tertiary">
              数字越大越容易识别话题跳变并另起一块。
            </p>
          </div>
        )}
      </div>
    </section>
  )
}
