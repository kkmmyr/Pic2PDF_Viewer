import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
    testDir: './e2e',
    timeout: 30_000,
    retries: 1,
    use: {
        baseURL: 'http://localhost:8090',
        headless: true,
        viewport: { width: 1280, height: 800 },
        // スクリーンショットはテスト失敗時のみ保存
        screenshot: 'only-on-failure',
        // 失敗時のトレースを保存
        trace: 'on-first-retry',
    },
    projects: [
        {
            name: 'chromium',
            use: { ...devices['Desktop Chrome'] },
        },
    ],
    // レポートは html 形式で playwright-report/ に出力
    reporter: [['html', { open: 'never' }], ['list']],
    outputDir: 'playwright-output/',
});
