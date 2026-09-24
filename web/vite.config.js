import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// 开发时前端在 5173，接口在后端 8000，用代理把 /api 转过去，
// 这样开发和生产同源，后端不需要开 CORS。
const BACKEND = process.env.BACKEND_URL || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [vue()],
  // 相对路径引用资源：后端用 StaticFiles 挂载 dist 时不用关心挂在哪个前缀下。
  base: './',
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: { '/api': { target: BACKEND, changeOrigin: true } },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    // 单文件产物便于直接提交进仓库，后端开箱即可托管。
    chunkSizeWarningLimit: 900,
  },
})
