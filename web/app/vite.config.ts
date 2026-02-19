/// <reference types="vitest" />

import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { TanStackRouterVite } from '@tanstack/router-plugin/vite'
import path from 'path'

export default defineConfig({
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
      'src/lib/utils/**/*.test.ts',
      'src/lib/utils/formUtils/**/*.test.ts',
      'src/lib/components/**/*.test.ts',
      'src/lib/hooks/**/*.test.ts',
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
        'src/lib/utils/revisionTree.ts',
        'src/lib/utils/customization.ts',
        'src/lib/utils/virtualization.ts',
        'src/lib/utils/formUtils/paths.ts',
        'src/lib/utils/formUtils/converters.ts',
        'src/lib/utils/formUtils/fieldTypeRegistry.ts',
        'src/lib/utils/formUtils/fieldGrouping.ts',
        'src/lib/utils/formUtils/transformers.ts',
        'src/lib/utils/formUtils/validators.ts',
        'src/lib/utils/formUtils/depthTransition.ts',
        'src/lib/components/FieldRenderer/resolveFieldKind.ts',
        'src/lib/components/DetailFieldRenderer/BinaryFieldDisplay.tsx',
        'src/lib/components/resource-table/searchUtils.ts',
        'src/lib/hooks/useAdvancedSearch.ts',
        'src/lib/components/Field/CellFieldRenderer/index.tsx',
        'src/lib/components/Field/CellFieldRenderer/helpers.tsx',
      ],
    },
  },
  server: {
    host: true,
    port: 5173,
    strictPort: true,
  },
})
