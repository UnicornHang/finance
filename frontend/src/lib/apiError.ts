/** 业务错误文案在 response.data.message，不要回落到 Axios 的 status code 句子。 */
export function readApiMessage(err: unknown): string | null {
  if (!err || typeof err !== 'object' || !('response' in err)) return null
  const data = (err as { response?: { data?: { message?: unknown; detail?: unknown } } }).response
    ?.data
  if (typeof data?.message === 'string' && data.message.trim()) return data.message
  if (typeof data?.detail === 'string' && data.detail.trim()) return data.detail
  return null
}
