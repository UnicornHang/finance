import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { Markdown } from '@/components/chat/Markdown'
import { readSearchSources } from '@/lib/messages'

describe('readSearchSources', () => {
  it('reads nested search.sources', () => {
    const sources = readSearchSources({
      id: '1',
      role: 'assistant',
      content: 'x',
      created_at: '',
      tool_calls: {
        tool: 'query_policy',
        search: {
          tool: 'search_official_data',
          sources: [{ index: 1, title: 'A', url: 'https://a.example' }],
        },
      },
    })
    expect(sources).toHaveLength(1)
    expect(sources[0].index).toBe(1)
  })

  it('returns empty without sources', () => {
    expect(
      readSearchSources({
        id: '1',
        role: 'assistant',
        content: 'x',
        created_at: '',
        tool_calls: { tool: 'query_policy' },
      }),
    ).toEqual([])
  })
})

describe('Markdown cite chips', () => {
  it('renders clickable [n] only when index is in citeIndexes', () => {
    const onCiteClick = vi.fn()
    render(
      <Markdown
        content="依据 [1] 与 [2] 说明。"
        citeIndexes={new Set([1])}
        onCiteClick={onCiteClick}
      />,
    )
    const citeBtn = screen.getByRole('button', { name: '引用来源 1' })
    fireEvent.click(citeBtn)
    expect(onCiteClick).toHaveBeenCalledWith(1)
    expect(screen.queryByRole('button', { name: '引用来源 2' })).toBeNull()
    expect(screen.getByText(/\[2\]/)).toBeTruthy()
  })
})
