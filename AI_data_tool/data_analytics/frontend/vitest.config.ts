import { configDefaults, defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    globals: true,
    // _ui_refresh_backup/ holds a local backup copy of src/, never test it
    exclude: [...configDefaults.exclude, '_ui_refresh_backup/**'],
  },
})
