import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/features/kindle/queries', () => ({
    useKindleBooks: vi.fn(),
    useKindleLinking: vi.fn(),
    useKindleLinkCandidates: vi.fn(),
    useKindleCaptureJobs: vi.fn(),
    useKindleCaptureQualityWarnings: vi.fn(),
    useKindleImports: vi.fn(),
}));

import {
    useKindleBooks,
    useKindleCaptureJobs,
    useKindleCaptureQualityWarnings,
    useKindleImports,
    useKindleLinkCandidates,
    useKindleLinking,
} from '@/features/kindle/queries';
import KindleCapturePage from '@/pages/KindleCapturePage';
import KindleCatalogPage from '@/pages/KindleCatalogPage';
import KindleImportsPage from '@/pages/KindleImportsPage';
import KindleLinksPage from '@/pages/KindleLinksPage';

const mockedUseKindleBooks = vi.mocked(useKindleBooks);
const mockedUseKindleLinking = vi.mocked(useKindleLinking);
const mockedUseKindleLinkCandidates = vi.mocked(useKindleLinkCandidates);
const mockedUseKindleCaptureJobs = vi.mocked(useKindleCaptureJobs);
const mockedUseKindleCaptureQualityWarnings = vi.mocked(useKindleCaptureQualityWarnings);
const mockedUseKindleImports = vi.mocked(useKindleImports);
const link = vi.fn();
const importOrders = vi.fn();
const importKindleInfo = vi.fn();
const importAutobuy = vi.fn();
const createCaptureJob = vi.fn();
const updateWarningRead = vi.fn();

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
        updateWarningRead.mockReset();
        updateWarningRead.mockResolvedValue(undefined);
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
        mockedUseKindleCaptureQualityWarnings.mockReturnValue({
            warnings: [],
            total: 0,
            unreadCount: 0,
            readCount: 0,
            isLoading: false,
            error: null,
            updateRead: updateWarningRead,
            updatingWarningId: null,
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
        expect(screen.getByText('著者：著者A')).toHaveClass('lg:hidden');
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

    it('他ASINのactive jobを表示して撮影開始を無効化する', () => {
        mockedUseKindleCaptureJobs.mockReturnValue({
            jobs: [
                {
                    id: 'job-other',
                    asin: 'B000OTHER1',
                    source: 'novel',
                    status: 'capturing',
                    direction: 'left',
                    expected_screens: null,
                    requested_at: '2026-07-25T12:00:00+09:00',
                    claimed_at: '2026-07-25T12:00:05+09:00',
                    heartbeat_at: '2026-07-25T12:01:00+09:00',
                    started_at: '2026-07-25T12:00:10+09:00',
                    completed_at: null,
                    agent_id: 'windows-test',
                    book_id: null,
                    captured_screens: 42,
                    error_code: null,
                    error_message: null,
                    title: '別の処理中作品',
                },
            ],
            isLoading: false,
            error: null,
            createCaptureJob,
            creatingCaptureJob: false,
        });
        renderWithRouter(<KindleCatalogPage />);

        fireEvent.click(screen.getByRole('button', { name: 'テスト作品 1巻' }));

        expect(screen.getByText('別の書籍は撮影中です')).toBeInTheDocument();
        expect(screen.getByText(/別の処理中作品/)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: '撮影して取り込む' })).toBeDisabled();
        expect(screen.getByRole('button', { name: '処理中ジョブを確認' })).toBeInTheDocument();
    });

    it('確認表示後に他ASINのactive jobが判明したら確定を無効化する', () => {
        mockedUseKindleCaptureJobs.mockReturnValue({
            jobs: [],
            isLoading: false,
            error: null,
            createCaptureJob,
            creatingCaptureJob: false,
        });
        const view = renderWithRouter(<KindleCatalogPage />);
        fireEvent.click(screen.getByRole('button', { name: 'テスト作品 1巻' }));
        fireEvent.click(screen.getByRole('button', { name: '撮影して取り込む' }));
        expect(screen.getByRole('button', { name: 'ジョブを作成' })).toBeEnabled();

        mockedUseKindleCaptureJobs.mockReturnValue({
            jobs: [
                {
                    id: 'job-other',
                    asin: 'B000OTHER1',
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
                    title: '別の処理中作品',
                },
            ],
            isLoading: false,
            error: null,
            createCaptureJob,
            creatingCaptureJob: false,
        });
        view.rerender(
            <MemoryRouter initialEntries={['/kindle/catalog']}>
                <KindleCatalogPage />
            </MemoryRouter>,
        );

        const confirmButton = screen.getByRole('button', { name: 'ジョブを作成' });
        expect(confirmButton).toBeDisabled();
        fireEvent.click(confirmButton);
        expect(createCaptureJob).not.toHaveBeenCalled();
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

    it('品質warningを確認管理し、comicの候補ページを直接開ける', async () => {
        mockedUseKindleCaptureQualityWarnings.mockReturnValue({
            warnings: [
                {
                    id: 11,
                    audit_id: 7,
                    job_id: 'job-quality',
                    asin: 'B000TEST01',
                    title: 'テスト作品 1巻',
                    source: 'comic',
                    book_id: 'テスト作品 1巻.pdf',
                    warning_policy_version: 'kindle-image-warning-v2',
                    created_at: '2026-08-22T12:00:00+09:00',
                    code: 'transient_bottom_right_overlay_candidate',
                    finding_count: 2,
                    files: ['001.png', '003.png'],
                    pages: [1, 3],
                    findings: [],
                    is_read: false,
                    read_at: null,
                },
            ],
            total: 1,
            unreadCount: 1,
            readCount: 0,
            isLoading: false,
            error: null,
            updateRead: updateWarningRead,
            updatingWarningId: null,
        });
        renderWithRouter(<KindleCapturePage />, '/kindle/capture');

        expect(screen.getByText('短時間の右下通知候補')).toBeInTheDocument();
        expect(screen.getByText(/正常なページも含まれます/)).toBeInTheDocument();
        fireEvent.change(screen.getByLabelText(/候補ページ/), { target: { value: '3' } });
        const pageLink = screen.getByRole('link', {
            name: 'テスト作品 1巻の3ページを開く',
        });
        const href = pageLink.getAttribute('href') ?? '';
        expect(decodeURIComponent(href.replaceAll('+', ' '))).toBe(
            '/comic?file=テスト作品 1巻.pdf&page=3',
        );
        expect(pageLink).toHaveAttribute('target', '_blank');

        fireEvent.click(screen.getByRole('button', { name: '確認済みにする' }));
        await waitFor(() =>
            expect(updateWarningRead).toHaveBeenCalledWith({ warningId: 11, isRead: true }),
        );

        fireEvent.click(screen.getByRole('button', { name: '確認済み 0' }));
        expect(mockedUseKindleCaptureQualityWarnings).toHaveBeenLastCalledWith('read');
    });

    it('novelの品質warningは拡張子を除いたreader導線を使う', () => {
        mockedUseKindleCaptureQualityWarnings.mockReturnValue({
            warnings: [
                {
                    id: 12,
                    audit_id: 8,
                    job_id: 'job-novel-quality',
                    asin: 'B000NOVEL1',
                    title: '小説作品',
                    source: 'novel',
                    book_id: '小説作品.pdf',
                    warning_policy_version: 'kindle-image-warning-v1',
                    created_at: '2026-08-22T12:00:00+09:00',
                    code: 'novel_edge_content_candidate',
                    finding_count: 1,
                    files: ['005.png'],
                    pages: [5],
                    findings: [],
                    is_read: false,
                    read_at: null,
                },
            ],
            total: 1,
            unreadCount: 1,
            readCount: 0,
            isLoading: false,
            error: null,
            updateRead: updateWarningRead,
            updatingWarningId: null,
        });
        renderWithRouter(<KindleCapturePage />, '/kindle/capture');

        const pageLink = screen.getByRole('link', { name: '小説作品の5ページを開く' });
        expect(decodeURIComponent(pageLink.getAttribute('href') ?? '')).toBe(
            '/novel/reader/小説作品?page=5',
        );
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
