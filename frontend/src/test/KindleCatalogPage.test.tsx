import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/hooks/useKindleCatalog', () => ({
    useKindleCatalog: vi.fn(),
    useKindleLinkCandidates: vi.fn(),
}));

import { useKindleCatalog, useKindleLinkCandidates } from '@/hooks/useKindleCatalog';
import KindleCatalogPage from '@/pages/KindleCatalogPage';

const mockedUseKindleCatalog = vi.mocked(useKindleCatalog);
const mockedUseKindleLinkCandidates = vi.mocked(useKindleLinkCandidates);
const preview = vi.fn();
const commit = vi.fn();
const link = vi.fn();
const importOrders = vi.fn();
const importKindleInfo = vi.fn();
const importAutobuy = vi.fn();
const createCaptureJob = vi.fn();

describe('KindleCatalogPage', () => {
    beforeEach(() => {
        preview.mockResolvedValue({
            configured: true,
            source_name: 'kindle.db',
            source_size: 100,
            fingerprint: 'a'.repeat(64),
            integrity: 'ok',
            counts: { books: 11419, purchases: 11415 },
            excluded_counts: { book_reviews: 15934 },
            missing_asin: 0,
            confirmation_token: 'token',
            expires_at: '2026-07-25T12:00:00+09:00',
            images_migrated: false,
        });
        commit.mockResolvedValue({
            run_id: 1,
            status: 'succeeded',
            records_processed: 1,
            records_skipped: 0,
            images_migrated: false,
        });
        mockedUseKindleLinkCandidates.mockReturnValue({
            data: undefined,
            isLoading: false,
        } as ReturnType<typeof useKindleLinkCandidates>);
        mockedUseKindleCatalog.mockReturnValue({
            books: {
                items: [
                    {
                        asin: 'B000TEST01',
                        title: 'テスト作品 1巻',
                        authors: ['著者A'],
                        genres: ['女性マンガ'],
                        publisher: null,
                        book_type: 'comic',
                        kindle_acquisition_date: null,
                        is_completed: null,
                        ownership: 'purchased',
                        capture_state: 'not_captured',
                        series_id: 1,
                        series_name: 'テスト作品',
                        volume_number: 1,
                        volume_label: '1',
                    },
                ],
                total: 1,
                page: 1,
                page_size: 50,
            },
            stats: {
                books: 1,
                purchases: 1,
                borrowings: 0,
                returns: 0,
                series: 1,
                captured: 0,
                last_import: null,
            },
            sources: {
                legacy_db_configured: true,
                legacy_db_available: true,
                legacy_db_name: 'kindle.db',
                amazon_data_configured: false,
            },
            unlinked: [],
            captureJobs: [],
            loading: false,
            error: null,
            preview,
            previewing: false,
            commit,
            committing: false,
            link,
            linking: false,
            importOrders,
            importingOrders: false,
            importKindleInfo,
            importingKindleInfo: false,
            importAutobuy,
            importingAutobuy: false,
            createCaptureJob,
            creatingCaptureJob: false,
        });
    });

    it('購入書籍と所有・画像状態を表示する', () => {
        render(<KindleCatalogPage />);

        expect(screen.getByText('テスト作品 1巻')).toBeInTheDocument();
        expect(screen.getByText('B000TEST01')).toBeInTheDocument();
        expect(screen.getAllByText('購入')).toHaveLength(2);
        expect(screen.getAllByText('画像なし')).toHaveLength(2);
    });

    it('検索語を一覧クエリへ反映する', () => {
        render(<KindleCatalogPage />);

        fireEvent.change(screen.getByPlaceholderText('タイトル・ASIN・著者を検索'), {
            target: { value: '著者A' },
        });

        expect(mockedUseKindleCatalog).toHaveBeenLastCalledWith(
            expect.objectContaining({ q: '著者A', page: 1 }),
        );
    });

    it('移行確認で旧アプリ画像を移行しないことを明示する', async () => {
        render(<KindleCatalogPage />);

        fireEvent.click(screen.getByRole('button', { name: '旧DB移行を確認' }));

        expect(
            await screen.findByText(/旧アプリの画像・表紙キャッシュは移行しません。/),
        ).toBeInTheDocument();
        expect(screen.getByText(/レビュー除外: 15,934 件/)).toBeInTheDocument();
    });
});
