import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // The Results screen is loaded on demand. Without this, the dev server first meets these
  // libraries when results open and reloads the page, which clears the app's state.
  optimizeDeps: { include: ['recharts', 'framer-motion'] },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
})
