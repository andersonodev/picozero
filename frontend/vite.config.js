// frontend/vite.config.js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// O proxy já aponta para o Django (E7/E9). Na prévia ele não é usado.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/sim': 'http://127.0.0.1:8000',
    },
  },
})
