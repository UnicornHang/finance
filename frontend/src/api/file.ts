import { apiClient } from './client'

export interface FileUploadResponse {
  file_hash: string
  file_url: string
  original_filename: string
  content_type: string
  size: number
  status: 'uploaded'
}

export interface FileRef {
  file_url: string
  file_hash: string
  file_meta: Record<string, unknown>
}

/** 通用文件上传（图片 / PDF / Word 等），落到 MinIO 后由 chat_service 决定后续动作。 */
export const fileApi = {
  /** `signal` 可选：传入 AbortController.signal 用于取消进行中的上传。

   * 注意：上传 FormData 时**不要**手动设 `Content-Type` —— axios 会自动加上
   * `multipart/form-data; boundary=...`，手设反而会让浏览器/代理拒掉请求
   * （症状：`net::ERR_*` + 0 kB + 几毫秒）。
   */
  upload: (file: File, signal?: AbortSignal) => {
    const form = new FormData()
    form.append('file', file)
    return apiClient
      .post<FileUploadResponse>('/files/upload', form, { signal })
      .then((r) => r.data)
  },
}
