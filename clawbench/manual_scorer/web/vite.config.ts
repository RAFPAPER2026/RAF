import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      // 开发环境代理到后端 FastAPI（端口 5002）
      '/api': {
        target: 'http://localhost:5002',
        changeOrigin: true,
      },
    },
  },
})
