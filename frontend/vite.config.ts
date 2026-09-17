import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  worker: { format: 'es' },
  // maplibre-gl chiếm phần lớn bundle; chấp nhận một chunk lớn thay vì cảnh báo
  build: { chunkSizeWarningLimit: 1600 },
})
