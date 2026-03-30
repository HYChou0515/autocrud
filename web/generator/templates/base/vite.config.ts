/// <reference types="vitest" />

import { defineConfig } from 'vitest/config'
import { loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { TanStackRouterVite } from '@tanstack/router-plugin/vite'
import path from 'path'

export default defineConfig(({ mode }) => {
  // Load all env vars (including non-VITE_ prefixed) for proxy config
  const env = loadEnv(mode, process.cwd(), '')
  const proxyTarget = env.API_PROXY_TARGET || 'http://localhost:8000'
  const proxyPath = env.VITE_API_URL || '/api'

  return {
  plugins: [
    TanStackRouterVite({ quoteStyle: 'single' }),
    react(),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    environment: 'happy-dom',
    include: [
      'src/autocrud/lib/*.test.ts',
      'src/autocrud/lib/utils/**/*.test.ts',
      'src/autocrud/lib/utils/formUtils/**/*.test.ts',
      'src/autocrud/lib/components/**/*.test.{ts,tsx}',
      'src/autocrud/lib/hooks/**/*.test.ts',
    ],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      thresholds: {
        lines: 85,
        functions: 85,
        branches: 70,
        statements: 85,
      },
      include: [
        'src/autocrud/lib/**/*.{ts,tsx}',
      ],
      exclude: [
        '**/*.test.{ts,tsx}',
        '**/*.d.ts',
      ],
    },
  },
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    proxy: {
      [proxyPath]: {
        target: proxyTarget,
        changeOrigin: true,
        rewrite: (p: string) => p.replace(new RegExp(`^${proxyPath}`), ''),
      },
    },
  },
}
})
