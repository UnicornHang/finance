import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

/**
 * 注意：vite.config.ts 里读不到 .env 文件里的变量（Vite 是在配置文件之后才加载的），
 * 必须显式调用 loadEnv。否则 .env.local 里的 VITE_API_PROXY_TARGET 会被忽略，
 * 代理静默回退到默认值，表现为前端所有 /api 请求返回 500（ECONNREFUSED）。
 */
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, __dirname)
  // 优先级：shell 环境变量 > .env/.env.local > 默认值（后端跑 Windows 本机时的端口）
  const apiTarget =
    process.env.VITE_API_PROXY_TARGET || env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8001'

  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      host: '0.0.0.0',
      port: 5173,
      proxy: {
        '/api': {
          // 容器内走服务名 backend:8000；本机直跑走后端端口；
          // 后端在虚拟机里则由 .env.local 指定 http://<VM-IP>:8000
          target: apiTarget,
          changeOrigin: true,
          ws: true,
        },
        '/metrics': {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
    test: {
      globals: true,
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
    },
  }
})