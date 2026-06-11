// ESLint v9 flat config
// 実行: cd frontend && npm run lint
import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import jsxA11y from 'eslint-plugin-jsx-a11y';
import prettierConfig from 'eslint-config-prettier';
import globals from 'globals';

export default tseslint.config(
    {
        ignores: ['dist', 'node_modules', 'coverage', '*.config.js', 'public'],
    },
    js.configs.recommended,
    ...tseslint.configs.recommended,
    jsxA11y.flatConfigs.recommended,
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

            // react-hooks v7 で追加された新ルール。フォームリセットや非同期 fetch 起動など
            // 正当なパターンを多数フラグするため無効化する。
            'react-hooks/set-state-in-effect': 'off',

            // LAN 個人アプリのため div onClick パターンは warn のみ（error に昇格させない）
            'jsx-a11y/click-events-have-key-events': 'warn',
            'jsx-a11y/no-static-element-interactions': 'warn',
            'jsx-a11y/no-noninteractive-element-interactions': 'warn',
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
