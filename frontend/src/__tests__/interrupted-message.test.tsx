import { describe, expect, it } from 'vitest'

import { isInterruptedMessage } from '@/lib/messages'

describe('isInterruptedMessage', () => {
  it('detects interrupted flag', () => {
    expect(
      isInterruptedMessage({
        id: '1',
        role: 'assistant',
        content: '半截',
        tool_calls: { interrupted: true },
        created_at: '',
      }),
    ).toBe(true)
  })

  it('returns false without interrupted flag', () => {
    expect(
      isInterruptedMessage({
        id: '1',
        role: 'assistant',
        content: '完整',
        tool_calls: { tool: 'query_policy' },
        created_at: '',
      }),
    ).toBe(false)
  })

  it('returns false when tool_calls is null', () => {
    expect(
      isInterruptedMessage({
        id: '1',
        role: 'assistant',
        content: 'x',
        tool_calls: null,
        created_at: '',
      }),
    ).toBe(false)
  })
})
