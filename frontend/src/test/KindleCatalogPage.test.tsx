import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/hooks/useKindleCatalog', () => ({
    useKindleBooks: vi.fn(),
    useKindleLinking: vi.fn(),
    useKindleLinkCandidates: vi.fn(),
    useKindleCaptureJobs: vi.fn(),
    useKindleImports: vi.fn(),
}));

import {
    useKindleBooks,
    useKindleCaptureJobs,
    useKindleImports,
    useKindleLinkCandidates,
    useKindleLinking,
} from '@/hooks/useKindleCatalog';
import KindleCapturePage from '@/pages/KindleCapturePage';
import KindleCatalogPage from '@/pages/KindleCatalogPage';
import KindleImportsPage from '@/pages/KindleImportsPage';
import KindleLinksPage from '@/pages/KindleLinksPage';

const mockedUseKindleBooks = vi.mocked(useKindleBooks);
const mockedUseKindleLinking = vi.mocked(useKindleLinking);
const mockedUseKindleLinkCandidates = vi.mocked(useKindleLinkCandidates);
const mockedUseKindleCaptureJobs = vi.mocked(useKindleCaptureJobs);
const mockedUseKindleImports = vi.mocked(useKindleImports);
const link = vi.fn();
const importOrders = vi.fn();
const importKindleInfo = vi.fn();
const importAutobuy = vi.fn();
const createCaptureJob = vi.fn();

const book = {
    asin: 'B000TEST01',
    title: 'テスト作品 1巻',
    authors: ['著者A'],
    genres: ['女性マンガ'],
    publisher: '出版社A',
    book_type: 'comic',
    kindle_acquisition_date: '2026-07-25',
    is_completed: false,
    ownership: 'purchased' as const,
    capture_state: 'not_captured' as const,
    series_id: 1,
    series_name: 'テスト作品',
    volume_number: 1,
    volume_label: '1',
};

function renderWithRouter(ui: React.ReactNode, initialEntry = '/kindle/catalog') {
    return render(<MemoryRouter initialEntries={[initialEntry]}>{ui}</MemoryRouter>);
}

describe('Kindle catalog pages', () => {
    beforeEach(() => {
        link.mockReset();
        importOrders.mockReset();
        importKindleInfo.mockReset();
        importAutobuy.mockReset();
        createCaptureJob.mockReset();
        link.mockResolvedValue({
            source: 'comic',
            book_id: 'existing-book',
            asin: 'B000TEST01',
        });
        importOrders.mockResolvedValue({
            run_id: 1,
            status: 'succeeded',
            files_processed: 1,
            files_skipped: 0,
            records_processed: 2,
            records_skipped: 0,
            files: [],
        });
        importKindleInfo.mockResolvedValue({
            run_id: 2,
            status: 'succeeded',
            files_processed: 1,
            files_skipped: 0,
            records_processed: 3,
            records_skipped: 0,
            files: [],
        });
        importAutobuy.mockResolvedValue({
            run_id: 3,
            status: 'succeeded',
            files_processed: 1,
            files_skipped: 0,
            records_processed: 1,
            records_skipped: 0,
            files: [],
        });
        createCaptureJob.mockResolvedValue({
            id: 'job-new',
            asin: 'B000TEST01',
            source: 'comic',
            status: 'queued',
            direction: 'left',
            expected_screens: null,
            requested_at: '2026-07-25T12:10:00+09:00',
            claimed_at: null,
            heartbeat_at: null,
            started_at: null,
            completed_at: null,
            agent_id: null,
            book_id: null,
            captured_screens: null,
            error_code: null,
            error_message: null,
            title: 'テスト作品 1巻',
        });
        mockedUseKindleBooks.mockReturnValue({
            data: {
                items: [book],
                total: 1,
                page: 1,
                page_size: 25,
            },
            isLoading: false,
            isFetching: false,
            error: null,
        } as ReturnType<typeof useKindleBooks>);
        mockedUseKindleLinking.mockReturnValue({
            unlinked: [
                {
                    source: 'comic',
                    book_id: 'existing-book',
                    title: 'テスト作品 1巻',
                    authors: ['著者A'],
                    series_title: 'テスト作品',
                },
            ],
            isLoading: false,
            error: null,
            link,
            linking: false,
        });
        mockedUseKindleLinkCandidates.mockReturnValue({
            data: {
                items: [
                    {
                        asin: 'B000TEST01',
                        title: 'テスト作品 1巻',
                        authors: ['著者A'],
                        book_type: 'comic',
                        score: 120,
                        reasons: ['タイトル一致', '種別一致'],
                    },
                ],
            },
            isLoading: false,
            error: null,
        } as ReturnType<typeof useKindleLinkCandidates>);
        mockedUseKindleCaptureJobs.mockReturnValue({
            jobs: [
                {
                    id: 'job-1',
                    asin: 'B000TEST01',
                    source: 'comic',
                    status: 'queued',
                    direction: 'left',
                    expected_screens: null,
                    requested_at: '2026-07-25T12:00:00+09:00',
                    claimed_at: null,
                    heartbeat_at: null,
                    started_at: null,
                    completed_at: null,
                    agent_id: null,
                    book_id: null,
                    captured_screens: null,
                    error_code: null,
                    error_message: null,
                    title: 'テスト作品 1巻',
                },
            ],
            isLoading: false,
            error: null,
            createCaptureJob,
            creatingCaptureJob: false,
        });
        mockedUseKindleImports.mockReturnValue({
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
                amazon_data_configured: true,
            },
            runs: [],
            loading: false,
            error: null,
            preview: vi.fn(),
            previewing: false,
            commit: vi.fn(),
            committing: false,
            importOrders,
            importingOrders: false,
            importKindleInfo,
            importingKindleInfo: false,
            importAutobuy,
            importingAutobuy: false,
        });
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    it('購入一覧を検索中心で表示し、行から詳細を確認できる', () => {
        renderWithRouter(<KindleCatalogPage />);

        expect(screen.getByText('テスト作品 1巻')).toBeInTheDocument();
        expect(screen.getByText('著者A')).toBeInTheDocument();
        expect(screen.getAllByText('漫画').length).toBeGreaterThan(0);
        expect(screen.queryByRole('button', { name: '漫画撮影' })).not.toBeInTheDocument();

        fireEvent.click(screen.getByRole('button', { name: 'テスト作品 1巻' }));

        expect(screen.getByRole('dialog')).toBeInTheDocument();
        expect(screen.getByText('この書籍は待機中です')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: '撮影して取り込む' })).toBeDisabled();
    });

    it('購入書籍詳細で登録先と方向を確認してジョブを作成する', async () => {
        mockedUseKindleCaptureJobs.mockReturnValue({
            jobs: [],
            isLoading: false,
            error: null,
            createCaptureJob,
            creatingCaptureJob: false,
        });
        renderWithRouter(<KindleCatalogPage />);

        fireEvent.click(screen.getByRole('button', { name: 'テスト作品 1巻' }));
        fireEvent.change(screen.getByLabelText('撮影後の登録先'), {
            target: { value: 'novel' },
        });
        fireEvent.change(screen.getByLabelText('ページ送り方向'), {
            target: { value: 'right' },
        });
        fireEvent.click(screen.getByRole('button', { name: '撮影して取り込む' }));

        expect(screen.getByText('Kindle撮影を開始しますか？')).toBeInTheDocument();
        expect(screen.getByText(/登録先: 小説/)).toBeInTheDocument();
        expect(screen.getByText(/ページ送り: 右送り/)).toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', { name: 'ジョブを作成' }));

        await waitFor(() =>
            expect(createCaptureJob).toHaveBeenCalledWith({
                asin: 'B000TEST01',
                source: 'novel',
                direction: 'right',
            }),
        );
    });

    it('検索語をデバウンスして一覧クエリへ反映する', async () => {
        vi.useFakeTimers();
        renderWithRouter(<KindleCatalogPage />);

        fireEvent.change(screen.getByPlaceholderText('タイトル・ASIN・著者を検索'), {
            target: { value: '著者A' },
        });

        await act(async () => {
            await vi.advanceTimersByTimeAsync(350);
        });

        expect(mockedUseKindleBooks).toHaveBeenLastCalledWith(
            expect.objectContaining({ q: '著者A', page: 1, pageSize: 25 }),
        );
    });

    it('URLから検索条件と表示件数を復元する', () => {
        renderWithRouter(
            <KindleCatalogPage />,
            '/kindle/catalog?q=作品&book_type=comic&page=2&page_size=50',
        );

        expect(mockedUseKindleBooks).toHaveBeenLastCalledWith(
            expect.objectContaining({
                q: '作品',
                bookType: 'comic',
                page: 2,
                pageSize: 50,
            }),
        );
        expect(screen.getByLabelText('表示件数')).toHaveValue('50');
    });

    it('既存画像と候補を比較して確認後に紐付ける', async () => {
        renderWithRouter(<KindleLinksPage />, '/kindle/links');

        fireEvent.click(screen.getByRole('button', { name: /テスト作品 1巻/ }));
        expect(screen.getByText('比較中の既存画像')).toBeInTheDocument();
        expect(screen.getByText('スコア 120')).toBeInTheDocument();

        fireEvent.click(screen.getByRole('button', { name: 'この候補を選択' }));
        expect(screen.getByText('このASINを紐付けますか？')).toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', { name: 'ASINを紐付け' }));

        await waitFor(() =>
            expect(link).toHaveBeenCalledWith({
                source: 'comic',
                bookId: 'existing-book',
                asin: 'B000TEST01',
            }),
        );
    });

    it('キャプチャページで自動工程と進捗を表示する', () => {
        mockedUseKindleCaptureJobs.mockReturnValue({
            jobs: [
                {
                    id: 'job-1',
                    asin: 'B000TEST01',
                    source: 'comic',
                    status: 'locating_book',
                    direction: 'left',
                    expected_screens: null,
                    requested_at: '2026-07-25T12:00:00+09:00',
                    claimed_at: '2026-07-25T12:00:05+09:00',
                    heartbeat_at: '2026-07-25T12:00:10+09:00',
                    started_at: null,
                    completed_at: null,
                    agent_id: 'windows-test',
                    book_id: null,
                    captured_screens: 0,
                    error_code: null,
                    error_message: null,
                    title: 'テスト作品 1巻',
                },
            ],
            isLoading: false,
            error: null,
            createCaptureJob,
            creatingCaptureJob: false,
        });
        renderWithRouter(<KindleCapturePage />, '/kindle/capture');

        expect(screen.getByText('書籍を検索中')).toBeInTheDocument();
        expect(screen.getByText('KindleライブラリでASINを照合しています。')).toBeInTheDocument();
        expect(screen.getByText('0 画面')).toBeInTheDocument();
        expect(screen.getByText('windows-test')).toBeInTheDocument();
    });

    it('失敗ジョブは原因と対処を表示し、確認後に新しいジョブで再実行する', async () => {
        mockedUseKindleCaptureJobs.mockReturnValue({
            jobs: [
                {
                    id: 'job-failed',
                    asin: 'B000TEST01',
                    source: 'novel',
                    status: 'failed',
                    direction: 'left',
                    expected_screens: null,
                    requested_at: '2026-07-25T12:00:00+09:00',
                    claimed_at: '2026-07-25T12:00:05+09:00',
                    heartbeat_at: '2026-07-25T12:01:00+09:00',
                    started_at: null,
                    completed_at: '2026-07-25T12:01:00+09:00',
                    agent_id: 'windows-test',
                    book_id: null,
                    captured_screens: 0,
                    error_code: 'download_timeout',
                    error_message: 'ダウンロードが期限内に完了しませんでした',
                    title: 'テスト作品 1巻',
                },
            ],
            isLoading: false,
            error: null,
            createCaptureJob,
            creatingCaptureJob: false,
        });
        renderWithRouter(<KindleCapturePage />, '/kindle/capture');

        expect(
            screen.getByText('ダウンロード完了後に新しいジョブとして再実行してください。'),
        ).toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', { name: '同じ条件で再実行' }));
        expect(screen.getByText('新しいジョブとして再実行しますか？')).toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', { name: '再実行ジョブを作成' }));

        await waitFor(() =>
            expect(createCaptureJob).toHaveBeenCalledWith({
                asin: 'B000TEST01',
                source: 'novel',
                direction: 'left',
                expectedScreens: undefined,
            }),
        );
    });

    it('すべて差分取込で3処理を順に実行する', async () => {
        renderWithRouter(<KindleImportsPage />, '/kindle/imports');

        fireEvent.click(screen.getByRole('button', { name: 'すべて差分取込' }));

        await waitFor(() => {
            expect(importKindleInfo).toHaveBeenCalledTimes(1);
            expect(importOrders).toHaveBeenCalledTimes(1);
            expect(importAutobuy).toHaveBeenCalledTimes(1);
        });
        expect(screen.getByText('3 件更新')).toBeInTheDocument();
        expect(screen.getByText('2 件更新')).toBeInTheDocument();
        expect(screen.getByText('1 件更新')).toBeInTheDocument();
    });
});
