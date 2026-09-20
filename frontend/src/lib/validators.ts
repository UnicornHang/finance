import { z } from 'zod'

export const loginSchema = z.object({
  account: z.string().min(1, '请输入账号'),
  password: z.string().min(1, '请输入密码'),
})

export const invoiceSchema = z.object({
  invoice_title: z.string().optional(),
  company: z.string().optional(),
  tax_id: z.string().optional(),
  invoice_code: z.string().optional(),
  invoice_number: z.string().optional(),
  invoice_date: z.string().optional(),
  amount_excl_tax: z.coerce.number().optional(),
  tax_amount: z.coerce.number().optional(),
  amount_incl_tax: z.coerce.number().optional(),
  invoice_type: z.string().optional(),
  seller: z.string().optional(),
  buyer: z.string().optional(),
  remark: z.string().optional(),
})

export const llmConfigSchema = z.object({
  model: z.string().min(1, '请填写模型'),
  provider: z.string().optional(),
  api_key: z.string().optional(),
  base_url: z.string().optional(),
  temperature: z.coerce.number().min(0).max(2).optional(),
  max_tokens: z.coerce.number().int().positive().optional(),
})

export type LoginInput = z.infer<typeof loginSchema>
export type InvoiceInput = z.infer<typeof invoiceSchema>
export type LLMConfigInput = z.infer<typeof llmConfigSchema>