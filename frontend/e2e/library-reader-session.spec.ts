import { test, expect, type Page } from '@playwright/test';

// 実アプリを起動して実行する。APIと書籍画像だけを隔離し、実データへ書き込まない。
async function installFixture(page: Page, mode: 'image' | 'pdf' = 'image') {
    const requests: {
        method: string;
        path: string;
        source: string | null;
        body: Record<string, unknown> | null;
    }[] = [];
    const unexpected: string[] = [];
    let pageCount = 4;
    const svg =
        '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="900"><rect width="600" height="900" fill="#f0eadb"/><text x="60" y="150" font-size="40">N6 Reader fixture</text></svg>';
    await page.route('**/api/**', async (route) => {
        const request = route.request();
        const url = new URL(request.url());
        const body = request.postDataJSON() as Record<string, unknown> | null;
        requests.push({
            method: request.method(),
            path: url.pathname,
            source: url.searchParams.get('source'),
            body,
        });
        const json = (value: unknown) => route.fulfill({ json: value });
        if (url.pathname.includes('/n6-fixture/') || url.pathname.includes('/thumbnail')) {
            return route.fulfill({ contentType: 'image/svg+xml', body: svg });
        }
        if (url.pathname.endsWith('/images')) {
            return json({
                images: Array.from(
                    { length: mode === 'image' ? pageCount : 0 },
                    (_, i) => `/api/n6-fixture/${i + 1}.svg`,
                ),
            });
        }
        if (url.pathname === '/api/pdfs' && request.method() === 'GET') {
            return json({
                files: Array.from({ length: 40 }, (_, i) => ({
                    name: `Book${String(i + 1).padStart(2, '0')}.pdf`,
                    thumbnail: null,
                    created_at: 1,
                })),
            });
        }
        if (url.pathname === '/api/meta') return json({});
        if (url.pathname === '/api/meta/view') return json({ view_count: 1, last_viewed_at: 1 });
        if (url.pathname === '/api/genres') return json([]);
        if (url.pathname === '/api/prefs')
            return json({
                read_state_filter: '',
                genre_filter: '',
                series_pins: {},
                author_pins: {},
            });
        if (url.pathname.endsWith('/delete_pages')) {
            pageCount -= (body?.page_indices as number[]).length;
            return json({ total_pages: pageCount });
        }
        unexpected.push(`${request.method()} ${url.pathname}`);
        return route.fulfill({ status: 501, json: { detail: 'Unconfigured fixture request' } });
    });
    // image query到着前のPDF先読みも隔離する。
    await page.route(/\/pdfs\/[^?]+\.pdf(?:\?.*)?$/, (route) =>
        route.fulfill({
            contentType: 'application/pdf',
            body: Buffer.from(
                'JVBERi0xLjcKJcK1wrYKJSBXcml0dGVuIGJ5IE11UERGIDEuMjkuMAoKMSAwIG9iago8PC9UeXBlL0NhdGFsb2cvUGFnZXMgMiAwIFIvSW5mbzw8L1Byb2R1Y2VyKE11UERGIDEuMjkuMCk+Pj4+CmVuZG9iagoKMiAwIG9iago8PC9UeXBlL1BhZ2VzL0NvdW50IDQvS2lkc1s0IDAgUiA2IDAgUiA4IDAgUiAxMCAwIFJdPj4KZW5kb2JqCgozIDAgb2JqCjw8Pj4KZW5kb2JqCgo0IDAgb2JqCjw8L1R5cGUvUGFnZS9NZWRpYUJveFswIDAgNjAwIDkwMF0vUm90YXRlIDAvUmVzb3VyY2VzIDMgMCBSL1BhcmVudCAyIDAgUj4+CmVuZG9iagoKNSAwIG9iago8PD4+CmVuZG9iagoKNiAwIG9iago8PC9UeXBlL1BhZ2UvTWVkaWFCb3hbMCAwIDYwMCA5MDBdL1JvdGF0ZSAwL1Jlc291cmNlcyA1IDAgUi9QYXJlbnQgMiAwIFI+PgplbmRvYmoKCjcgMCBvYmoKPDw+PgplbmRvYmoKCjggMCBvYmoKPDwvVHlwZS9QYWdlL01lZGlhQm94WzAgMCA2MDAgOTAwXS9Sb3RhdGUgMC9SZXNvdXJjZXMgNyAwIFIvUGFyZW50IDIgMCBSPj4KZW5kb2JqCgo5IDAgb2JqCjw8Pj4KZW5kb2JqCgoxMCAwIG9iago8PC9UeXBlL1BhZ2UvTWVkaWFCb3hbMCAwIDYwMCA5MDBdL1JvdGF0ZSAwL1Jlc291cmNlcyA5IDAgUi9QYXJlbnQgMiAwIFI+PgplbmRvYmoKCnhyZWYKMCAxMQowMDAwMDAwMDAwIDY1NTM1IGYgCjAwMDAwMDAwNDIgMDAwMDAgbiAKMDAwMDAwMDEyMCAwMDAwMCBuIAowMDAwMDAwMTkxIDAwMDAwIG4gCjAwMDAwMDAyMTIgMDAwMDAgbiAKMDAwMDAwMDMwMyAwMDAwMCBuIAowMDAwMDAwMzI0IDAwMDAwIG4gCjAwMDAwMDA0MTUgMDAwMDAgbiAKMDAwMDAwMDQzNiAwMDAwMCBuIAowMDAwMDAwNTI3IDAwMDAwIG4gCjAwMDAwMDA1NDggMDAwMDAgbiAKCnRyYWlsZXIKPDwvU2l6ZSAxMS9Sb290IDEgMCBSL0lEWzxDM0EzQzM4ODNDQzJBNDFFQzNCMjMzN0E2MDJCMjkzRj48NTk2ODVBMDhGRjk5NTMyOTQwRDU5Q0I4NDA3OTY0QkE+XT4+CnN0YXJ0eHJlZgo2NDAKJSVFT0YK',
                'base64',
            ),
        }),
    );
    return { requests, unexpected };
}

for (const width of [1280, 390]) {
    test.describe(`Library/Reader session ${width}px`, () => {
        test.use({ viewport: { width, height: 844 } });

        test('一覧の保持、履歴、読了、編集、キャッシュ済み再開', async ({ page }, testInfo) => {
            const fixture = await installFixture(page);
            const errors: string[] = [];
            page.on('pageerror', (error) => errors.push(error.message));
            page.on('console', (message) => {
                if (message.type() === 'error') errors.push(message.text());
            });
            await page.goto('/comic');
            const search = page.getByRole('searchbox', { name: '書籍を検索' });
            await search.fill('Book');
            if (width === 390) {
                await page.getByRole('button', { name: /絞り込み/ }).click();
                const dialog = page.getByRole('dialog');
                await expect(dialog).toBeVisible();
                await page.keyboard.press('Tab');
                await page.keyboard.press('Shift+Tab');
                await expect
                    .poll(() =>
                        dialog.evaluate((element) => element.contains(document.activeElement)),
                    )
                    .toBe(true);
                const bounds = await dialog.boundingBox();
                expect(bounds!.x).toBeGreaterThanOrEqual(16);
                expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width - 16);
                await page.keyboard.press('Escape');
                await expect(dialog).not.toBeVisible();
            }
            await page.screenshot({ path: testInfo.outputPath(`library-${width}.png`) });
            const openBook = page.getByRole('button', { name: 'Book15 を読む', exact: true });
            await openBook.scrollIntoViewIfNeeded();
            await openBook.focus();
            const scrollY = await page.evaluate(() => window.scrollY);
            expect(scrollY).toBeGreaterThan(0);
            await page.keyboard.press('Enter');
            await expect(page).toHaveURL(/file=Book15.pdf/);
            await expect(page.getByRole('img', { name: 'Page 1', exact: true })).toBeVisible();
            await expect(page.getByText('1 / 4', { exact: true })).toBeAttached();
            await page.getByRole('button', { name: /^読書画面/ }).press('Enter');
            await expect
                .poll(
                    async () =>
                        (
                            await page
                                .locator('button')
                                .filter({ has: page.locator('svg.lucide-arrow-left') })
                                .boundingBox()
                        )?.y ?? -1,
                )
                .toBeGreaterThanOrEqual(0);
            await page.screenshot({ path: testInfo.outputPath(`reader-initial-${width}.png`) });
            await page.getByRole('button', { name: /^読書画面/ }).press('Enter');
            await page.keyboard.press('?');
            await expect(page.getByRole('dialog')).toBeVisible();
            await page.keyboard.press('Tab');
            await page.keyboard.press('Shift+Tab');
            await page.keyboard.press('Escape');
            await expect(page.getByRole('dialog')).not.toBeVisible();
            const readerContent = page.getByRole('button', { name: /^読書画面/ });
            await readerContent.hover();
            await page.mouse.wheel(0, 100);
            await expect(page.getByRole('img', { name: 'Page 2', exact: true })).toBeVisible();
            await page.waitForTimeout(250);
            await page.mouse.wheel(0, -100);
            await expect(page.getByRole('img', { name: 'Page 1', exact: true })).toBeVisible();
            await page.waitForTimeout(250);
            await page.keyboard.press('ArrowLeft');
            await expect(page.getByRole('img', { name: 'Page 2', exact: true })).toBeVisible();
            await page.keyboard.press('ArrowLeft');
            await expect(page.getByRole('img', { name: 'Page 4', exact: true })).toBeVisible();
            await expect
                .poll(() => fixture.requests.some((request) => request.body?.read_state === 'done'))
                .toBe(true);
            await page.keyboard.press('e');
            await expect(page.getByText('全 4 ページ / 0 件選択中')).toBeVisible();
            await page.getByRole('button', { name: 'Page 1 1', exact: true }).click();
            await page.getByRole('button', { name: '削除実行 (1)' }).click();
            await expect(page.getByRole('alertdialog')).toBeVisible();
            await page.getByRole('alertdialog').getByRole('button', { name: 'キャンセル' }).click();
            await expect(page.getByRole('alertdialog')).not.toBeVisible();
            await page.getByRole('button', { name: '閉じる', exact: true }).click();
            await page.screenshot({ path: testInfo.outputPath(`reader-${width}.png`) });
            // ReaderHeaderの戻るbutton（既存の無名icon）をキーボードで実行。
            const closeReader = page
                .locator('button')
                .filter({ has: page.locator('svg.lucide-arrow-left') });
            await closeReader.focus();
            await page.keyboard.press('Enter');
            await expect(search).toHaveValue('Book');
            await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(scrollY);
            await page.goBack();
            await expect(page.getByRole('img', { name: 'Page 1', exact: true })).toBeVisible();
            await expect(page.getByText('1 / 4', { exact: true })).toBeAttached();
            await page.goForward();
            await expect(search).toBeVisible();
            await openBook.focus();
            await page.keyboard.press('Enter');
            await expect(page.getByText('1 / 4', { exact: true })).toBeAttached();
            await page.keyboard.press('e');
            await expect(page.getByText('全 4 ページ / 0 件選択中')).toBeVisible();
            const readsBefore = fixture.requests.filter(
                (request) => request.path === '/api/pdfs',
            ).length;
            await page.getByRole('button', { name: 'Page 1 1', exact: true }).click();
            await page.getByRole('button', { name: '削除実行 (1)' }).click();
            await page.getByRole('alertdialog').getByRole('button', { name: /削除/ }).click();
            await expect(page.getByText('1 / 3', { exact: true })).toBeAttached();
            await expect
                .poll(
                    () => fixture.requests.filter((request) => request.path === '/api/pdfs').length,
                )
                .toBeGreaterThan(readsBefore);
            expect(
                fixture.requests.find((request) => request.path.endsWith('/delete_pages'))?.body,
            ).toEqual({ page_indices: [0] });
            expect(fixture.unexpected).toEqual([]);
            expect(errors).toEqual([]);
        });
    });
}

for (const mode of ['image', 'pdf'] as const) {
    test(`URL初期ページを適用する: ${mode}`, async ({ page }) => {
        const fixture = await installFixture(page, mode);
        const errors: string[] = [];
        page.on('pageerror', (error) => errors.push(error.message));
        page.on('console', (message) => {
            if (message.type() === 'error') errors.push(message.text());
        });
        await page.goto('/doujin?file=Book01.pdf&page=3');
        await expect(page.getByText('3 / 4', { exact: true })).toBeAttached();
        if (mode === 'image') {
            await expect(page.getByRole('img', { name: 'Page 3', exact: true })).toBeVisible();
        } else {
            await expect(page.locator('canvas').first()).toBeVisible();
        }
        await page.keyboard.press('ArrowRight');
        await expect(page.getByText('1 / 4', { exact: true })).toBeAttached();
        await page.getByRole('button', { name: /^読書画面/ }).hover();
        await page.mouse.wheel(0, 100);
        await expect(page.getByText('2 / 4', { exact: true })).toBeAttached();
        expect(fixture.requests.some((request) => request.source === 'doujin')).toBe(true);
        expect(fixture.unexpected).toEqual([]);
        expect(errors).toEqual([]);
    });
}
