/// <reference types="vitest" />

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { TanStackRouterVite } from '@tanstack/router-plugin/vite'

export default defineConfig({
  plugins: [
    TanStackRouterVite({ quoteStyle: 'single' }),
    react(),
  ],
  test: {
    environment: 'node',
    include: ['src/lib/utils/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      lines: 90,
      functions: 90,
      branches: 90,
      statements: 90,
      include: [
        'src/lib/utils/revisionTree.ts',
        'src/lib/utils/customization.ts',
        'src/lib/utils/virtualization.ts',
      ],
    },
  },
  server: {
    host: true,
    port: 5173,
    strictPort: true,
  },
})
