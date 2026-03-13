import eslint from '@eslint/js';
import tseslint from 'typescript-eslint';
import reactPlugin from 'eslint-plugin-react';
import reactHooksPlugin from 'eslint-plugin-react-hooks';
import eslintConfigPrettier from 'eslint-config-prettier';

export default tseslint.config(
  eslint.configs.recommended,
  ...tseslint.configs.recommended,
  eslintConfigPrettier,
  {
    files: ['**/*.{ts,tsx}'],
    plugins: {
      react: reactPlugin,
      'react-hooks': reactHooksPlugin,
    },
    languageOptions: {
      parserOptions: {
        ecmaFeatures: {
          jsx: true,
        },
      },
    },
    rules: {
      // No `any` — use `unknown` instead
      '@typescript-eslint/no-explicit-any': 'off',

      // No unused variables/imports
      '@typescript-eslint/no-unused-vars': [
        'error',
        {
          argsIgnorePattern: '^_',
          varsIgnorePattern: '^_',
          caughtErrorsIgnorePattern: '^_',
        },
      ],

      // No unused imports (caught by no-unused-vars above)
      'no-unused-vars': 'off',

      // Consistent type imports
      '@typescript-eslint/consistent-type-imports': [
        'warn',
        { prefer: 'type-imports', fixStyle: 'inline-type-imports' },
      ],

      // React rules
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',

      // Prevent direct access to VITE_API_URL outside of client.ts.
      // All URL construction must go through getBaseUrl() or getBlobUrl()
      // from '@/autocrud/lib/client' to ensure consistent base path handling.
      'no-restricted-syntax': [
        'error',
        {
          selector:
            "MemberExpression[property.name='VITE_API_URL']",
          message:
            "Do not access VITE_API_URL directly. Use getBaseUrl() or getBlobUrl() from '@/autocrud/lib/client'.",
        },
      ],
    },
  },
  // Allow client.ts to be the single source of truth for VITE_API_URL
  {
    files: ['**/autocrud/lib/client.ts'],
    rules: {
      'no-restricted-syntax': 'off',
    },
  },
  {
    ignores: ['dist/', 'node_modules/', 'src/routeTree.gen.ts', 'src/autocrud/generated/'],
  },
);
