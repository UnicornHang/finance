// 后端 API 类型定义

export type UserRole = 'employee' | 'finance' | 'admin'

export interface User {
  id: string
  name: string
  account: string
  role: UserRole
  dept: string | null
  status: string
  created_at: string
}

export interface Session {
  id: string
  title: string | null
  summary: string | null
  created_at: string
  updated_at: string
}

export interface Message {
  id: string
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string | null
  tool_calls: Record<string, unknown> | null
  created_at: string
}

export interface Invoice {
  id: string
  invoice_title: string | null
  company: string | null
  tax_id: string | null
  invoice_code: string | null
  invoice_number: string | null
  invoice_date: string | null
  amount_excl_tax: number | null
  tax_amount: number | null
  amount_incl_tax: number | null
  invoice_type: string | null
  seller: string | null
  buyer: string | null
  remark: string | null
  file_url: string | null
  file_hash: string | null
  ocr_confidence: Record<string, number> | null
  status: 'pending_review' | 'active' | 'deleted' | string
  user_id: string
  created_at: string
  updated_at: string | null
}

export interface InvoicePreviewResponse {
  status: 'processing' | 'ready' | 'not_found'
  invoice?: Invoice
}

export interface InvoiceFileResponse {
  url: string
  expires_in: number
}

export interface Contract {
  id: string
  contract_name: string | null
  contract_no: string | null
  party_a: string | null
  party_b: string | null
  sign_date: string | null
  effective_start: string | null
  effective_end: string | null
  amount: number | null
  key_clauses: string | null
  review_result: { violations: Violation[]; risk_level: string; summary: string } | null
  risk_level: 'high' | 'medium' | 'low' | null
  status: string
  created_at: string
}

export interface Violation {
  clause: string
  issue: string
  severity: 'high' | 'medium' | 'low'
}

export interface LLMConfig {
  id: string
  scene: 'chitchat' | 'policy_query' | 'ocr_post' | 'contract_review'
  provider: string
  model: string
  base_url: string | null
  temperature: number
  max_tokens: number
  timeout_seconds: number
  enabled: boolean
  has_api_key: boolean
  api_key_masked: string | null
  updated_at: string | null
}

export interface LLMProvider {
  key: string
  label: string
  base_url: string
  models: string[]
}

export interface LLMScene {
  key: string
  label: string
  description: string
  default_temperature: number
  default_max_tokens: number
}

export interface LLMTestResult {
  ok: boolean
  message: string
  latency_ms: number
}

export interface KbDocument {
  id: string
  title: string
  doc_type: string | null
  status: string
  chunk_count: number
  version: number
  created_at: string
}

// SSE 事件类型
export type StreamEvent =
  | { type: 'text'; content: string; session_id?: string }
  | {
      type: 'sidepanel'
      payload: {
        type: 'invoice' | 'contract'
        data:
          | { status: 'processing'; file_url: string; file_hash: string }
          | { status: 'ready'; invoice_id: string; invoice_title?: string; [k: string]: unknown }
          | Record<string, unknown>
      }
    }
  | { type: 'done' }
  | { type: 'error'; message: string }