import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        // ws: true enables WebSocket proxying — required for the /api/play/game/{id}/ws endpoint.
        ws: true,
      },
      '/openapi.json': 'http://localhost:8000',
    },
  },
})
