import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        // Recharts and d3 are the bulk of the bundle and change far less often than
        // app code, so splitting them out lets a returning visitor reuse a cached
        // vendor chunk instead of re-downloading the charting library on every deploy.
        manualChunks: {
          charts: ['recharts', 'd3-cloud'],
          vendor: ['react', 'react-dom', 'react-router-dom', 'axios'],
        },
      },
    },
  },
  server: {
    host: '0.0.0.0',
    port: 3000,
    watch: {
      usePolling: true,
      interval: 500,
    },
  },
})
