import { contractApi } from '@/api/contract'
import { invoiceApi } from '@/api/invoice'
import type { Contract, Invoice } from '@/types'

import { createInflightRegistry } from './inflightByKey'

/** 合同「重新审查」按 contractId 合并进行中请求 */
export const contractReReviewInflight = createInflightRegistry<Contract>()

/** 发票「重新识别」按 invoiceId 合并进行中请求 */
export const invoiceRerecognizeInflight = createInflightRegistry<Invoice>()

/** 发起或复用合同重新审查请求 */
export function runContractReReview(contractId: string): Promise<Contract> {
  return contractReReviewInflight.run(contractId, () =>
    contractApi.reReview(contractId),
  )
}

/** 发起或复用发票重新识别请求 */
export function runInvoiceRerecognize(invoiceId: string): Promise<Invoice> {
  return invoiceRerecognizeInflight.run(invoiceId, () =>
    invoiceApi.rerecognize(invoiceId),
  )
}
