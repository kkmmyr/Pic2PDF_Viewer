// ESLint v9 flat config
// 実行: cd frontend && npm run lint
import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import prettierConfig from 'eslint-config-prettier';
import globals from 'globals';

export default tseslint.config(
    {
        ignores: ['dist', 'node_modules', 'coverage', '*.config.js', 'public'],
    },
    js.configs.recommended,
    ...tseslint.configs.recommended,
    {
        files: ['**/*.{ts,tsx}'],
        languageOptions: {
            ecmaVersion: 2022,
            globals: { ...globals.browser, ...globals.node },
        },
        plugins: {
            'react-hooks': reactHooks,
            'react-refresh': reactRefresh,
        },
        rules: {
            ...reactHooks.configs.recommended.rules,
            'react-refresh/only-export-components': [
                'warn',
                { allowConstantExport: true },
            ],
            // any 禁止（プロジェクトポリシー: frontend-conventions）
            '@typescript-eslint/no-explicit-any': 'error',
            // 未使用変数: _ プレフィックスは許可
            '@typescript-eslint/no-unused-vars': [
                'error',
                {
                    argsIgnorePattern: '^_',
                    varsIgnorePattern: '^_',
                    caughtErrorsIgnorePattern: '^_',
                },
            ],
            // catch (error) で型を指定しない unknown はデフォルト OK
        },
    },
    // テストファイルは緩める
    {
        files: ['**/*.test.{ts,tsx}', '**/test/**/*.{ts,tsx}'],
        rules: {
            '@typescript-eslint/no-explicit-any': 'off',
        },
    },
    // Prettier と衝突するスタイル系ルールを無効化（最後に置く）
    prettierConfig,
);
