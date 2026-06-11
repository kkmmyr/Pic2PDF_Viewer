import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
    plugins: [react(), tailwindcss()],
    resolve: {
        alias: {
            '@': fileURLToPath(new URL('./src', import.meta.url)),
        },
    },
    build: {
        chunkSizeWarningLimit: 600,
        rollupOptions: {
            output: {
                manualChunks(id) {
                    if (!id.includes('node_modules')) return;
                    if (id.includes('vis-network') || id.includes('vis-data')) return 'chunk-vis';
                    if (id.includes('react-pdf') || id.includes('pdfjs-dist')) return 'chunk-pdf';
                    if (id.includes('@tanstack')) return 'chunk-tanstack';
                    if (id.includes('@dnd-kit')) return 'chunk-dnd';
                    if (id.includes('lucide-react')) return 'chunk-lucide';
                    return 'chunk-vendor';
                },
            },
        },
    },
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
        exclude: ['**/node_modules/**', 'e2e/**'],
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
