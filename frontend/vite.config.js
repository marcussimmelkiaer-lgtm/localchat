import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In dev (`npm run dev`), proxy API + health to the local FastAPI server so the
// dev server mirrors production's same-origin assumption (no CORS). The built
// bundle is served directly by FastAPI from ../backend/static, so base is './'.
const API_PORT = process.env.LOCALCHAT_PORT || '8765'
const target = `http://127.0.0.1:${API_PORT}`

export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: '../backend/static',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api': { target, changeOrigin: true },
      '/healthz': { target, changeOrigin: true },
    },
  },
})
