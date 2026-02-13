import eslint from '@eslint/js';
import tseslint from 'typescript-eslint';
import eslintConfigPrettier from 'eslint-config-prettier';
import eslintPluginPrettier from 'eslint-plugin-prettier/recommended';

export default tseslint.config(
  eslint.configs.recommended,
  ...tseslint.configs.recommended,
  eslintConfigPrettier,
  eslintPluginPrettier,
  {
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      // No `any` — use `unknown` instead
      '@typescript-eslint/no-explicit-any': 'warn',

      // No unused variables/imports
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],

      // No unused imports (caught by no-unused-vars above)
      'no-unused-vars': 'off',

      // Consistent type imports
      '@typescript-eslint/consistent-type-imports': [
        'warn',
        { prefer: 'type-imports' },
      ],

      // Prettier formatting
      'prettier/prettier': 'warn',
    },
  },
  {
    ignores: ['dist/', 'templates/', 'node_modules/'],
  },
);
