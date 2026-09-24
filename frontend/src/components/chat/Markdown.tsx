import React from 'react'

import { cn } from '@/lib/utils'

interface Props {
  content: string
  className?: string
}

/**
 * 行内格式解析：处理 **bold**, __bold__, *italic*, _italic_, `code`
 *
 * 设计要点（流式增量友好）：
 * - 全部使用非贪婪 + 字符白名单，避免在未闭合时吞掉后续内容
 * - 未闭合的标记会保持字面文本，不会破坏布局
 */
function renderInline(text: string): React.ReactNode[] {
  type Pattern = {
    regex: RegExp
    render: (full: string, inner: string) => React.ReactNode
  }
  const patterns: Pattern[] = [
    // **bold** / __bold__ — 必须先于 italic，避免 * 被单边吞掉
    { regex: /\*\*([^*\n]+?)\*\*/, render: (_, c) => <strong key={next()}>{c}</strong> },
    { regex: /__([^_\n]+?)__/, render: (_, c) => <strong key={next()}>{c}</strong> },
    // `code`
    {
      regex: /`([^`\n]+?)`/,
      render: (_, c) => (
        <code
          key={next()}
          className="rounded bg-canvas px-1 py-0.5 font-mono text-[0.9em] text-ink"
        >
          {c}
        </code>
      ),
    },
    // *italic* — 要求内部不以空白 / * 开头，避免 `* 你好 *` 这种被吞
    {
      regex: /(?<![*\w])\*([^*\s][^*\n]*?)\*(?!\w)/,
      render: (_, c) => <em key={next()}>{c}</em>,
    },
    // _italic_ — 同上
    {
      regex: /(?<![_\w])_([^_\s][^_\n]*?)_(?!\w)/,
      render: (_, c) => <em key={next()}>{c}</em>,
    },
  ]

  const tokens: React.ReactNode[] = []
  let remaining = text

  while (remaining.length > 0) {
    let firstMatch: { idx: number; len: number; node: React.ReactNode } | null = null

    for (const p of patterns) {
      const m = remaining.match(p.regex)
      if (m && m.index !== undefined) {
        if (!firstMatch || m.index < firstMatch.idx) {
          firstMatch = { idx: m.index, len: m[0].length, node: p.render(m[0], m[1]) }
        }
      }
    }

    if (firstMatch) {
      if (firstMatch.idx > 0) {
        tokens.push(remaining.slice(0, firstMatch.idx))
      }
      tokens.push(firstMatch.node)
      remaining = remaining.slice(firstMatch.idx + firstMatch.len)
    } else {
      tokens.push(remaining)
      break
    }
  }

  return tokens
}

// 模块级计数器，避免 renderInline 每次调用都重新初始化
let inlineKeyCounter = 0
function next() {
  inlineKeyCounter += 1
  return inlineKeyCounter
}

/**
 * 轻量 markdown 渲染：标题 / 列表 / hr / 段落 + 行内格式
 *
 * 仅覆盖 mock 响应 + LLM 常见输出需要的子集：
 * - `# H1` ~ `###### H6`
 * - `-` / `*` / `+` 无序列表
 * - `1.` 有序列表
 * - `---` 水平线
 * - 空行分段
 * - 行内 `**`/`__`/`*`/`_`/`` ` ``
 *
 * 流式增量期间，闭合不完整的标记会被保留为字面文本（不报错、不吞内容）。
 */
export function Markdown({ content, className }: Props) {
  const lines = content.split('\n')
  const blocks: React.ReactNode[] = []
  let blockKey = 0
  let i = 0

  while (i < lines.length) {
    const line = lines[i]

    // Horizontal rule: --- / *** / ___ (允许前后空白)
    if (/^\s{0,3}(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      blocks.push(<hr key={blockKey++} className="my-2 border-line" />)
      i++
      continue
    }

    // Heading: # ~ ###### + 文本 + 可选尾部 # 闭合
    const headingMatch = line.match(/^(#{1,6})\s+(.+?)(?:\s+#+\s*)?$/)
    if (headingMatch) {
      const level = headingMatch[1].length as 1 | 2 | 3 | 4 | 5 | 6
      const text = headingMatch[2]
      const cls =
        level === 1
          ? 'mt-3 mb-1.5 text-title-lg font-semibold first:mt-0'
          : level === 2
            ? 'mt-2.5 mb-1 text-title-md font-semibold first:mt-0'
            : level === 3
              ? 'mt-2 mb-1 text-title-sm font-semibold first:mt-0'
              : 'mt-1.5 mb-0.5 text-body-md font-semibold first:mt-0'
      blocks.push(
        React.createElement(
          `h${level}` as 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'h6',
          { key: blockKey++, className: cls },
          renderInline(text),
        ),
      )
      i++
      continue
    }

    // Unordered list: - / * / +
    if (/^\s*[-*+]\s+/.test(line)) {
      const items: React.ReactNode[] = []
      while (i < lines.length) {
        const m = lines[i].match(/^\s*[-*+]\s+(.+)$/)
        if (!m) break
        items.push(<li key={items.length}>{renderInline(m[1])}</li>)
        i++
      }
      blocks.push(
        <ul
          key={blockKey++}
          className="my-1.5 ml-5 list-disc space-y-0.5 marker:text-ink-tertiary"
        >
          {items}
        </ul>,
      )
      continue
    }

    // Ordered list: 1. 2. ...
    if (/^\s*\d+\.\s+/.test(line)) {
      const items: React.ReactNode[] = []
      while (i < lines.length) {
        const m = lines[i].match(/^\s*\d+\.\s+(.+)$/)
        if (!m) break
        items.push(<li key={items.length}>{renderInline(m[1])}</li>)
        i++
      }
      blocks.push(
        <ol
          key={blockKey++}
          className="my-1.5 ml-5 list-decimal space-y-0.5 marker:text-ink-tertiary"
        >
          {items}
        </ol>,
      )
      continue
    }

    // Blank line: skip (paragraph boundary handled below)
    if (line.trim() === '') {
      i++
      continue
    }

    // Paragraph: collect consecutive "soft" lines until next block boundary
    const para: string[] = [line]
    i++
    while (i < lines.length) {
      const cur = lines[i]
      if (cur.trim() === '') break
      if (/^(#{1,6}\s|---$|\*\*\*$|___$|\s*[-*+]\s|\s*\d+\.\s)/.test(cur)) break
      para.push(cur)
      i++
    }
    blocks.push(
      <p key={blockKey++} className="my-1.5 first:mt-0 last:mb-0 leading-relaxed">
        {renderInline(para.join('\n'))}
      </p>,
    )
  }

  return <div className={cn('text-body-md text-ink', className)}>{blocks}</div>
}