import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
    plugins: [react()],
    server: {
        port: 5176,
        strictPort: true,
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
