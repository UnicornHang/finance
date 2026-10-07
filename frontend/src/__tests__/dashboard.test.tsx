import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import { Dashboard } from '@/components/admin/Dashboard'
import { dashboardApi } from '@/api/admin'
import type { DashboardOverview } from '@/types'

vi.mock('@/api/admin', () => ({
  dashboardApi: {
    overview: vi.fn(),
  },
}))

const mockedApi = vi.mocked(dashboardApi)

function sampleOverview(): DashboardOverview {
  return {
    timezone: 'Asia/Shanghai',
    generated_at: '2026-10-05T10:00:00+08:00',
    days: 7,
    kpis: {
      today_archived: { value: 2, previous: 1, delta_pct: 100 },
      month_invoice_amount: { value: 1130, previous: 0, delta_pct: null },
      month_contracts: { value: 1, previous: 0, delta_pct: null },
      high_risk_contracts: { value: 1, previous: null, delta_pct: null },
    },
    trend: {
      points: [
        { date: '2026-10-05', label: '10/5', weekday: '周一', invoices: 2, contracts: 1 },
      ],
      delta_pct: 8.4,
    },
    risk_contracts: [
      { id: 'c1', title: '设备采购合同', amount: 580000, risk_level: 'high' },
    ],
    token_trend: {
      points: [
        { date: '2026-10-05', label: '10/5', weekday: '周一', total_tokens: 1200 },
      ],
      delta_pct: 12.5,
      period_total: 1200,
    },
    activity: {
      active_users: 3,
      invoices_uploaded: 2,
      policy_queries: 4,
      contract_reviews: 1,
    },
    finance: {
      amount_excl_tax: 1000,
      tax_amount: 130,
      input_tax: 130,
      amount_incl_tax: 1130,
    },
    knowledge: {
      document_count: 2,
      chunk_count: 40,
      month_retrieves: 4,
      all_indexed: true,
      pending_or_failed: 0,
    },
  }
}

function renderDashboard() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('数据概览', () => {
  beforeEach(() => {
    mockedApi.overview.mockReset()
  })

  it('应展示 KPI 与 Token 消耗趋势', async () => {
    mockedApi.overview.mockResolvedValue(sampleOverview())
    renderDashboard()

    expect(await screen.findByText('今日归档')).toBeInTheDocument()
    expect(screen.getByText(/Token 消耗/)).toBeInTheDocument()
    expect(screen.queryByText('看板测试发票')).not.toBeInTheDocument()
  })

  it('加载失败时应提供重试', async () => {
    mockedApi.overview.mockRejectedValue(new Error('network'))
    renderDashboard()

    expect(await screen.findByText('数据概览暂时无法加载')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '重新加载' })).toBeInTheDocument()
  })
})
