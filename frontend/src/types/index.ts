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

/** 聊天气泡内展示的附件（发票图片 / PDF 等） */
export interface MessageAttachment {
  id?: string
  file_url: string
  file_hash: string
  original_filename?: string | null
  content_type?: string | null
  size?: number | null
  file_kind?: 'image' | 'file' | string | null
  intent?: string | null
  recognize_status?: string | null
  recognize_error?: string | null
  /** 合同侧栏字段等；审查时写入，重开会话直接用 */
  extract_result?: {
    contract_name?: string | null
    party_a?: string | null
    party_b?: string | null
    sign_date?: string | null
    amount?: number | null
    invoice_code?: string | null
    invoice_number?: string | null
  } | null
  invoice_id?: string | null
  /** 用于同一张发票去重（代码+号码） */
  invoice_code?: string | null
  invoice_number?: string | null
  contract_id?: string | null
}

export interface Message {
  id: string
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string | null
  tool_calls: Record<string, unknown> | null
  /** 与 content 同一次发送的图片/文件 */
  attachments?: MessageAttachment[] | null
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
  /** 侧栏归档态：本票已归档，或档案已有相同代码+号码 */
  archive_status?: 'pending' | 'archived' | string | null
  user_id: string
  /** 上传该发票的用户姓名 */
  operator_name?: string | null
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
  /** 侧栏归档态：本合同已归档，或档案已有相同文件 */
  archive_status?: 'pending' | 'archived' | string | null
  file_url: string | null
  file_hash: string | null
  created_at: string
  updated_at?: string | null
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
  system_prompt: string | null
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

export interface ToolConfig {
  id: string | null
  tool_name: string
  label: string
  description: string
  provider: string
  base_url: string | null
  enabled: boolean
  timeout_seconds: number
  max_results: number
  fetch_pages: number
  fetch_max_chars: number
  has_api_key: boolean
  api_key_masked: string | null
  source: 'db' | 'env'
  updated_at: string | null
}

export interface ToolCatalogItem {
  key: string
  label: string
  description: string
  providers: Array<{
    key: string
    label: string
    default_base_url: string
    api_key_help: string
  }>
}

export interface KbDocument {
  id: string
  title: string
  doc_type: string | null
  status: string
  chunk_count: number
  version: number
  created_at: string
  error_message?: string | null
  source_file?: string | null
  tenant_id?: string | null
  chunk_strategy?: string | null
  chunk_strategy_effective?: string | null
  chunk_params?: {
    child_size?: number
    parent_size?: number
    overlap?: number
    inner_strategy?: string
    semantic_threshold?: number
    fallback_reason?: string
    split_stats?: {
      stored_chunks: number
      retrieval_chunks: number
      parent_chunks: number
      child_chunks: number
      leaf_chunks: number
      min_chars: number
      max_chars: number
      avg_chars: number
      section_paths: number
    }
  } | null
}

/** 上传或重新索引时使用的切分配置。 */
export interface KbChunkConfig {
  chunkStrategy: string
  chunkSize: number
  chunkOverlap: number
  parentSize: number
  semanticThreshold: number
}

/** 文档预览详情 */
export interface KbDocumentDetail extends KbDocument {
  content: string
  embedding_model?: string | null
  updated_at?: string | null
  chunks: Array<{
    id: string
    chunk_index: number
    content: string
    token_count?: number | null
    role?: string
    parent_id?: string | null
    section_path?: string | null
    embeddable?: boolean
  }>
}

/** 知识库上传弹窗默认配置（GET /kb/settings） */
export interface KbIndexSettings {
  chunk_size: number
  chunk_overlap: number
  parent_size?: number
  chunk_strategy?: string
  semantic_threshold?: number
  chunk_strategies?: Array<{
    value: string
    label: string
    recommended?: boolean
    suited?: string
    how?: string
    example?: string
    cost_hint?: string
    visual?: string[]
    description?: string
  }>
  embedding_model: string
  embedding_dimension: number
  embedding_base_url: string
  index_mode: string
  index_modes: Array<{
    value: string
    label: string
    description: string
    disabled?: boolean
  }>
  retrieve_top_k: number
  hybrid_enabled?: boolean
  rerank_enabled?: boolean
  rerank_model?: string
  milvus_enabled: boolean
  allowed_suffixes: string[]
  max_upload_bytes: number
}

/** 后台数据概览 */
export interface DashboardKpi {
  value: number
  previous: number | null
  delta_pct: number | null
}

export interface DashboardTrendPoint {
  date: string
  label: string
  weekday: string
  invoices: number
  contracts: number
}

export interface DashboardRiskContract {
  id: string
  title: string
  amount: number
  risk_level: 'high' | 'medium' | 'low' | string
}

export interface DashboardRecentArchive {
  id: string
  kind: 'invoice' | 'contract' | string
  title: string
  amount: number | null
  operator_name: string | null
  created_at: string | null
}

export interface DashboardOverview {
  timezone: string
  generated_at: string
  days: number
  kpis: {
    today_archived: DashboardKpi
    month_invoice_amount: DashboardKpi
    month_contracts: DashboardKpi
    high_risk_contracts: DashboardKpi
  }
  trend: {
    points: DashboardTrendPoint[]
    delta_pct: number | null
  }
  risk_contracts: DashboardRiskContract[]
  recent_archives: DashboardRecentArchive[]
  activity: {
    active_users: number
    invoices_uploaded: number
    policy_queries: number
    contract_reviews: number
  }
  finance: {
    amount_excl_tax: number
    tax_amount: number
    input_tax: number
    amount_incl_tax: number
  }
  knowledge: {
    document_count: number
    chunk_count: number
    month_retrieves: number
    all_indexed: boolean
    pending_or_failed: number
  }
}

/** 公开检索 / SSE sources 事件中的单条引用。 */
export interface WebSource {
  index: number
  title: string
  url: string
  snippet?: string
  source_kind?: 'official' | 'supplemental' | 'web' | string
  favicon_host?: string
  published_at?: string
}

// SSE 事件类型
export type StreamEvent =
  | { type: 'text'; content: string; session_id?: string }
  | { type: 'status'; message: string }
  | { type: 'sources'; hit_count: number; sources: WebSource[] }
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