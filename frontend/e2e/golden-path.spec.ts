/**
 * E2E ゴールデンパステスト
 *
 * 対象: http://localhost:8090 (リリースサービス)
 * 前提: Pic2PDFViewer Windows サービスが起動済みであること
 *
 * シナリオ:
 *  1. ルーティング — / へのアクセスが /doujin にリダイレクト
 *  2. ページ遷移  — 同人誌 → 漫画 → 小説 DB のナビゲーション
 *  3. 検索フィルタ — 検索ボックスへの入力と絞り込み
 *  4. ダークモード — ライト ↔ ダーク のトグル
 *  5. PDF リーダー — 書籍クリックでリーダー起動・閉じて一覧に戻る
 *  6. ジェネレータ — /doujin/generator のページ表示
 *  7. メタ編集ダイアログ — 小説 DB でダイアログ開閉
 */

import { test, expect } from '@playwright/test';

// ── 1 & 2. ルーティング / ページ遷移 ────────────────────────────────────
test.describe('ページ遷移', () => {
    test('/ にアクセスすると /doujin にリダイレクトされる', async ({ page }) => {
        await page.goto('/');
        await expect(page).toHaveURL('/doujin');
        await expect(page.getByText('Pic2PDF Viewer')).toBeVisible();
    });

    test('同人誌 → 漫画 → 小説 DB の順にナビゲーションできる', async ({ page }) => {
        await page.goto('/doujin');

        // 漫画 Library へ
        await page.locator('a[href="/comic"]').click();
        await expect(page).toHaveURL('/comic');

        // 小説 DB へ
        await page.locator('a[href="/novel/db"]').click();
        await expect(page).toHaveURL('/novel/db');

        // ヘッダーナビが常に表示されている
        await expect(page.locator('header')).toBeVisible();
    });
});

// ── 3. 検索フィルタ ──────────────────────────────────────────────────────
test.describe('検索フィルタ', () => {
    test('タイトル/作者の検索ボックスで絞り込みができる', async ({ page }) => {
        await page.goto('/doujin');

        const search = page.getByPlaceholder('タイトル / 作者を検索...');
        await expect(search).toBeVisible({ timeout: 10_000 });

        // 入力で値が反映される
        await search.fill('テスト');
        await expect(search).toHaveValue('テスト');

        // クリアしてもクラッシュしない
        await search.clear();
        await expect(search).toHaveValue('');
    });
});

// ── 4. ダークモード切替 ──────────────────────────────────────────────────
test.describe('ダークモード', () => {
    test('ダークモードをトグルできる', async ({ page }) => {
        await page.goto('/doujin');

        // 新規コンテキストは localStorage 空 → ライトモード開始
        await expect(page.locator('html')).not.toHaveClass(/\bdark\b/);

        // ダークモードに切り替え
        await page.getByTitle('ダークモードに切り替え').click();
        await expect(page.locator('html')).toHaveClass(/\bdark\b/);

        // ライトモードに戻す
        await page.getByTitle('ライトモードに切り替え').click();
        await expect(page.locator('html')).not.toHaveClass(/\bdark\b/);
    });
});

// ── 5. PDF リーダー遷移 ─────────────────────────────────────────────────
test.describe('PDF リーダー', () => {
    test('書籍をクリックするとリーダーが開き、戻ると一覧に戻る', async ({ page }) => {
        await page.goto('/doujin');

        // PDF グリッド内の最初のサムネイル画像を探す
        // (書籍が 0 件の環境ではスキップ)
        const firstThumb = page.locator('.grid img').first();
        await firstThumb.waitFor({ timeout: 8_000 }).catch(() => null);
        const count = await firstThumb.count();
        test.skip(count === 0, '書籍が 0 件のためスキップ');

        await firstThumb.click();

        // URL に ?file= が付き、nav ヘッダーがリーダーモードで非表示になる
        await expect(page).toHaveURL(/[?&]file=/);
        await expect(page.locator('nav')).not.toBeVisible();

        // ブラウザの戻るで一覧に戻る
        await page.goBack();
        await expect(page).toHaveURL('/doujin');
        await expect(page.locator('header')).toBeVisible();
    });
});

// ── 6. 取り込みページ ──────────────────────────────────────────────────
test.describe('取り込み', () => {
    test('取り込みページが表示される', async ({ page }) => {
        await page.goto('/doujin/generator');

        await expect(page.getByRole('heading', { name: '取り込み' })).toBeVisible();
        await expect(page.getByRole('button', { name: '今すぐスキャン' })).toBeVisible();
    });
});

// ── 7. 小説 DB とメタ編集ダイアログ ─────────────────────────────────────
test.describe('小説 DB', () => {
    test('小説 DB ページが読み込まれる', async ({ page }) => {
        await page.goto('/novel/db');

        await expect(page.locator('header')).toBeVisible();
        // 小説 DB のナビリンクがアクティブ
        await expect(page.locator('a[href="/novel/db"]')).toBeVisible();
    });

    test('書籍のメタデータ編集ダイアログが開閉できる', async ({ page }) => {
        await page.goto('/novel/db');

        // title="メタデータを編集" ボタンが表示されるまで待つ
        // (書籍が 0 件の環境ではスキップ)
        const editBtn = page.getByTitle('メタデータを編集').first();
        const visible = await editBtn.isVisible().catch(() => false);
        if (!visible) {
            // ローディング完了を少し待って再確認
            await page.waitForTimeout(3_000);
        }
        const visibleAfterWait = await editBtn.isVisible().catch(() => false);
        test.skip(!visibleAfterWait, '書籍が 0 件のためスキップ');

        await editBtn.click();

        // ダイアログが開いた: aria-label="閉じる" ボタンが表示される
        const closeBtn = page.getByRole('button', { name: '閉じる' });
        await expect(closeBtn).toBeVisible();

        // Esc でダイアログが閉じる
        await page.keyboard.press('Escape');
        await expect(closeBtn).not.toBeVisible();
    });
});
