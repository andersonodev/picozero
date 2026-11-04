// frontend/vite.config.js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Em dev, tudo que é do motor (FastAPI em 127.0.0.1:8000) passa pelo proxy, igual ao deploy único.
const MOTOR = 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': MOTOR,
      '/sim': MOTOR,
      '/mcp': MOTOR,
      '/docs': MOTOR,
      '/openapi.json': MOTOR,
    },
  },
})
