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
      'src/specstar/lib/*.test.ts',
      'src/specstar/lib/utils/**/*.test.{ts,tsx}',
      'src/specstar/lib/utils/formUtils/**/*.test.ts',
      'src/specstar/lib/components/**/*.test.{ts,tsx}',
      'src/specstar/lib/hooks/**/*.test.ts',
    ],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      thresholds: {
        perFile: true,
        lines: 50,
        functions: 50,
        branches: 30,
        statements: 50,
      },
      include: [
        'src/specstar/lib/**/*.{ts,tsx}',
      ],
      exclude: [
        '**/*.test.{ts,tsx}',
        '**/*.d.ts',
        // Barrel re-export files (no runtime logic)
        'src/specstar/lib/**/index.ts',
        // Shim re-export files at components root
        'src/specstar/lib/components/JobTable.tsx',
        'src/specstar/lib/components/PendingJobsAccordion.tsx',
        'src/specstar/lib/components/ResourceCreate.tsx',
        'src/specstar/lib/components/ResourceDetail.tsx',
        // Pure type definition files (no runtime logic)
        'src/specstar/lib/types/**',
        'src/specstar/lib/hooks/types.ts',
        'src/specstar/lib/utils/formUtils/types.ts',
        // User customization file (not library logic)
        'src/specstar/lib/resourceCustomization.ts',
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
