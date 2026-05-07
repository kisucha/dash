// vite.config.js — Vite 빌드 설정 및 개발 서버 프록시 구성
// /api 요청을 FastAPI 백엔드(localhost:8000)로 포워딩한다
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      // /api로 시작하는 모든 요청을 백엔드로 프록시
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
