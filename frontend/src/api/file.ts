import { apiClient } from './client'

export interface FileUploadResponse {
  id: string
  file_hash: string
  file_url: string
  original_filename: string
  content_type: string
  size: number
  recognize_status: string
  status: 'uploaded'
}

export interface FileRef {
  id: string
  file_url: string
  file_hash: string
  file_meta: Record<string, unknown>
}

export interface FilePresignResponse {
  url: string
  expires_in: number
}

/** 通用文件上传（图片 / PDF / Word 等），落到 MinIO 后由 chat_service 决定后续动作。 */
export const fileApi = {
  /** `signal` 可选：传入 AbortController.signal 用于取消进行中的上传。

   * 注意：上传 FormData 时**不要**手动设 `Content-Type` —— axios 会自动加上
   * `multipart/form-data; boundary=...`，手设反而会让浏览器/代理拒掉请求
   * （症状：`net::ERR_*` + 0 kB + 几毫秒）。
   */
  upload: (file: File, sessionId: string, signal?: AbortSignal) => {
    const form = new FormData()
    form.append('file', file)
    form.append('session_id', sessionId)
    return apiClient
      .post<FileUploadResponse>('/files/upload', form, { signal })
      .then((r) => r.data)
  },

  /** 根据 s3:// URL 换取临时预览/下载链接 */
  presign: (fileUrl: string, expires = 3600) =>
    apiClient
      .get<FilePresignResponse>('/files/presign', {
        params: { file_url: fileUrl, expires },
      })
      .then((r) => r.data),
}
