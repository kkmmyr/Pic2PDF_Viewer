import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vitejs.dev/config/
export default defineConfig({
    plugins: [react(), tailwindcss()],
    server: {
        port: 5176,
        strictPort: true,
        // 静的ファイル（画像 / サムネイル / PDF）は backend が StaticFiles で配信する
        // ため、dev 時は backend の :8766 へ proxy する。
        // API は apiClient.ts で絶対 URL を使うため proxy 不要だが、`/api` も
        // 念のため含めておく（環境変数で BASE_URL を空にした場合の保険）。
        proxy: {
            '/api': 'http://localhost:8766',
            '/kindle_novel': 'http://localhost:8766',
            '/kindle': 'http://localhost:8766',
            '/images': 'http://localhost:8766',
            '/thumbnails': 'http://localhost:8766',
        },
    },
    test: {
        environment: 'jsdom',
        globals: true,
        setupFiles: './src/test/setup.ts',
        coverage: {
            provider: 'v8',
            reporter: ['text', 'html'],
            include: ['src/**/*.{ts,tsx}'],
            exclude: [
                'src/test/**',
                'src/**/*.test.{ts,tsx}',
                'src/types/**',
                'src/main.tsx',
                'src/vite-env.d.ts',
            ],
            reportsDirectory: 'coverage',
        },
    },
})
