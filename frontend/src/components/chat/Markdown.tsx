import type { ReactNode } from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { cn } from '@/lib/utils'

interface Props {
  content: string
  className?: string
}

const HEADING_CLASS = {
  1: 'mt-3 mb-1.5 text-title-lg font-semibold first:mt-0',
  2: 'mt-2.5 mb-1 text-title-md font-semibold first:mt-0',
  3: 'mt-2 mb-1 text-title-sm font-semibold first:mt-0',
  4: 'mt-1.5 mb-0.5 text-body-md font-semibold first:mt-0',
  5: 'mt-1.5 mb-0.5 text-body-md font-semibold first:mt-0',
  6: 'mt-1.5 mb-0.5 text-body-md font-semibold first:mt-0',
} as const

/** 标题样式与原先手写渲染保持一致。 */
function heading(level: keyof typeof HEADING_CLASS): Components['h1'] {
  const Tag = `h${level}` as 'h1'
  return function Heading({ children }) {
    return <Tag className={HEADING_CLASS[level]}>{children}</Tag>
  }
}

/** 行内代码用浅底，围栏代码块由外层 pre 承担边框。 */
function Code({ className, children }: { className?: string; children?: ReactNode }) {
  const block = Boolean(className) || String(children).includes('\n')
  if (block) {
    return <code className={cn('font-mono text-[0.9em]', className)}>{children}</code>
  }
  return (
    <code className="rounded bg-canvas px-1 py-0.5 font-mono text-[0.9em] text-ink">{children}</code>
  )
}

const components: Components = {
  h1: heading(1),
  h2: heading(2),
  h3: heading(3),
  h4: heading(4),
  h5: heading(5),
  h6: heading(6),
  p: ({ children }) => <p className="my-1.5 leading-relaxed first:mt-0 last:mb-0">{children}</p>,
  ul: ({ children }) => (
    <ul className="my-1.5 ml-5 list-disc space-y-0.5 marker:text-ink-tertiary">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="my-1.5 ml-5 list-decimal space-y-0.5 marker:text-ink-tertiary">{children}</ol>
  ),
  hr: () => <hr className="my-2 border-line" />,
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="text-primary underline underline-offset-2"
    >
      {children}
    </a>
  ),
  blockquote: ({ children }) => (
    <blockquote className="my-2 border-l-2 border-line pl-3 text-ink-secondary">{children}</blockquote>
  ),
  pre: ({ children }) => (
    <pre className="my-2 overflow-x-auto rounded-md border border-line bg-canvas p-3 font-mono text-[0.9em] leading-relaxed">
      {children}
    </pre>
  ),
  code: Code,
  table: ({ children }) => (
    <div className="my-2 overflow-x-auto">
      <table className="w-full border-collapse text-left text-body-sm">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border border-line bg-canvas px-2 py-1 font-semibold">{children}</th>
  ),
  td: ({ children }) => <td className="border border-line px-2 py-1">{children}</td>,
}

/**
 * 用 react-markdown 渲染模型回复。
 * 不启用 rehype-raw，模型输出里的 HTML 不会当成页面节点插入。
 */
export function Markdown({ content, className }: Props) {
  return (
    <div className={cn('text-body-md text-ink', className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  )
}
