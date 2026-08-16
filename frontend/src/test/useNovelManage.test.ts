/**
 * useNovelManage フックのユニットテスト。
 * useNovelBuildQueue / useOcrStatus / fetchBooks をモックしてロジック単体を検証する。
 */
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../hooks/novel_build/useNovelBuildQueue', () => ({
    useNovelBuildQueue: vi.fn(),
}));

vi.mock('../hooks/useOcrStatus', () => ({
    useOcrStatus: vi.fn(),
}));

vi.mock('../features/novel_db/api', () => ({
    fetchBooks: vi.fn(),
}));

import { useNovelBuildQueue } from '@/hooks/novel_build/useNovelBuildQueue';
import { useOcrStatus } from '@/hooks/useOcrStatus';
import { fetchBooks } from '@/features/novel_db/api';
import { useNovelManage } from '@/hooks/useNovelManage';
import type { BuildQueueStatus } from '@/features/novel_build/types';
import type { BookSummary } from '@/features/novel_db/types';
import { createQueryWrapper } from '@/test/queryTestUtils';

const mockedUseBuildQueue = useNovelBuildQueue as ReturnType<typeof vi.fn>;
const mockedUseOcrStatus = useOcrStatus as ReturnType<typeof vi.fn>;
const mockedFetchBooks = fetchBooks as ReturnType<typeof vi.fn>;

const EMPTY_STATUS: BuildQueueStatus = {
    is_running: false,
    current_job: null,
    queued_jobs: [],
    recent_finished: [],
};

const mockEnqueue = vi.fn();
const mockCancel = vi.fn();

function makeBook(overrides: Partial<BookSummary> = {}): BookSummary {
    return {
        name: '書籍A',
        authors: [],
        series_id: null,
        series_title: null,
        is_indexed: false,
        page_count: null,
        indexed_at: null,
        thumbnail_url: null,
        ocr_done_at: '2024-01-01',
        volume: null,
        publisher: null,
        asin: null,
        series_index: null,
        read_state: 'unread',
        ...overrides,
    };
}

function setupMocks(ocrStatus: string = 'idle', buildStatus: Partial<BuildQueueStatus> = {}) {
    mockedUseOcrStatus.mockReturnValue({ status: ocrStatus, logs: [] });
    mockedUseBuildQueue.mockReturnValue({
        status: { ...EMPTY_STATUS, ...buildStatus },
        isEnqueuing: false,
        enqueueError: null,
        enqueue: mockEnqueue,
        cancel: mockCancel,
    });
}

function renderNovelManage() {
    return renderHook(() => useNovelManage(), { wrapper: createQueryWrapper() });
}

describe('useNovelManage', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockedFetchBooks.mockResolvedValue([]);
        setupMocks();
    });

    // --- タブ切り替え & lazy-activation ---

    it('初期 activeTab は ocr', () => {
        const { result } = renderNovelManage();
        expect(result.current.activeTab).toBe('ocr');
    });

    it('handleTabChange("build") で activeTab が build になる', () => {
        const { result } = renderNovelManage();
        act(() => {
            result.current.handleTabChange('build');
        });
        expect(result.current.activeTab).toBe('build');
    });

    it('handleTabChange("build") 後に useNovelBuildQueue が enabled=true で呼ばれる', () => {
        const { result } = renderNovelManage();
        // 初回は enabled=false
        expect(mockedUseBuildQueue).toHaveBeenLastCalledWith(false);

        act(() => {
            result.current.handleTabChange('build');
        });
        expect(mockedUseBuildQueue).toHaveBeenLastCalledWith(true);
    });

    it('ocr タブに戻っても buildEnabled は true のまま', () => {
        const { result } = renderNovelManage();
        act(() => {
            result.current.handleTabChange('build');
        });
        act(() => {
            result.current.handleTabChange('ocr');
        });
        expect(mockedUseBuildQueue).toHaveBeenLastCalledWith(true);
    });

    // --- fetchBooks & 書籍選択 ---

    it('fetchBooks の結果から ocr_done_at / indexed_at ありの書籍のみを books にセットする', async () => {
        mockedFetchBooks.mockResolvedValue([
            makeBook({ name: '対象A', ocr_done_at: '2024-01-01', indexed_at: null }),
            makeBook({ name: '対象B', ocr_done_at: null, indexed_at: '2024-02-01' }),
            makeBook({ name: '除外C', ocr_done_at: null, indexed_at: null }),
        ]);

        const { result } = renderNovelManage();
        await waitFor(() => expect(result.current.books).toHaveLength(2));
        expect(result.current.books.map((b) => b.name)).toEqual(['対象A', '対象B']);
    });

    it('初期 selectedBook / selectedBookCtx はともに未ビルドの最初の書籍', async () => {
        mockedFetchBooks.mockResolvedValue([
            makeBook({ name: '未完了1', ocr_done_at: '2024-01-01', indexed_at: null }),
            makeBook({ name: '完了済み', ocr_done_at: null, indexed_at: '2024-02-01' }),
        ]);

        const { result } = renderNovelManage();
        await waitFor(() => expect(result.current.selectedBook).toBe('未完了1'));
        expect(result.current.selectedBookCtx).toBe('未完了1');
    });

    // --- handleShowBuiltChange ---

    it('handleShowBuiltChange(true) で filteredBooks が完了済みに切り替わり selectedBook が更新される', async () => {
        mockedFetchBooks.mockResolvedValue([
            makeBook({ name: '未完了', ocr_done_at: '2024-01-01', indexed_at: null }),
            makeBook({ name: '完了', ocr_done_at: null, indexed_at: '2024-02-01' }),
        ]);

        const { result } = renderNovelManage();
        await waitFor(() => expect(result.current.books).toHaveLength(2));

        act(() => {
            result.current.handleShowBuiltChange(true);
        });

        expect(result.current.filteredBooks.map((b) => b.name)).toEqual(['完了']);
        expect(result.current.selectedBook).toBe('完了');
    });

    it('handleShowBuiltChange(false) で filteredBooks が未完了に戻る', async () => {
        mockedFetchBooks.mockResolvedValue([
            makeBook({ name: '未完了', ocr_done_at: '2024-01-01', indexed_at: null }),
            makeBook({ name: '完了', ocr_done_at: null, indexed_at: '2024-02-01' }),
        ]);

        const { result } = renderNovelManage();
        await waitFor(() => expect(result.current.books).toHaveLength(2));

        act(() => {
            result.current.handleShowBuiltChange(true);
        });
        act(() => {
            result.current.handleShowBuiltChange(false);
        });

        expect(result.current.filteredBooks.map((b) => b.name)).toEqual(['未完了']);
        expect(result.current.selectedBook).toBe('未完了');
    });

    // --- handleEnqueueBuild ---

    it('handleEnqueueBuild — selectedBook あり allBooks=false で enqueue(book, false, full_build) が呼ばれる', async () => {
        mockedFetchBooks.mockResolvedValue([
            makeBook({ name: '花太郎', ocr_done_at: '2024-01-01', indexed_at: null }),
        ]);
        mockEnqueue.mockResolvedValue(undefined);

        const { result } = renderNovelManage();
        await waitFor(() => expect(result.current.selectedBook).toBe('花太郎'));

        act(() => {
            result.current.handleEnqueueBuild();
        });

        expect(mockEnqueue).toHaveBeenCalledWith('花太郎', false, 'full_build');
    });

    it('handleEnqueueBuild — allBooks=true で enqueue(null, true, full_build) が呼ばれる', () => {
        mockEnqueue.mockResolvedValue(undefined);
        const { result } = renderNovelManage();

        act(() => {
            result.current.setAllBooks(true);
        });
        act(() => {
            result.current.handleEnqueueBuild();
        });

        expect(mockEnqueue).toHaveBeenCalledWith(null, true, 'full_build');
    });

    it('handleEnqueueBuild — selectedBook が空で allBooks=false のとき enqueue を呼ばない', () => {
        const { result } = renderNovelManage();

        act(() => {
            result.current.handleEnqueueBuild();
        });

        expect(mockEnqueue).not.toHaveBeenCalled();
    });

    // --- handleEnqueueCtx ---

    it('handleEnqueueCtx — selectedBookCtx あり allBooksCtx=false で enqueue(book, false, generate_contexts) が呼ばれる', async () => {
        mockedFetchBooks.mockResolvedValue([
            makeBook({ name: '花太郎', ocr_done_at: '2024-01-01', indexed_at: null }),
        ]);
        mockEnqueue.mockResolvedValue(undefined);

        const { result } = renderNovelManage();
        await waitFor(() => expect(result.current.selectedBookCtx).toBe('花太郎'));

        act(() => {
            result.current.handleEnqueueCtx();
        });

        expect(mockEnqueue).toHaveBeenCalledWith('花太郎', false, 'generate_contexts');
    });

    it('handleEnqueueCtx — allBooksCtx=true で enqueue(null, true, generate_contexts) が呼ばれる', () => {
        mockEnqueue.mockResolvedValue(undefined);
        const { result } = renderNovelManage();

        act(() => {
            result.current.setAllBooksCtx(true);
        });
        act(() => {
            result.current.handleEnqueueCtx();
        });

        expect(mockEnqueue).toHaveBeenCalledWith(null, true, 'generate_contexts');
    });

    it('handleEnqueueCtx — selectedBookCtx が空で allBooksCtx=false のとき enqueue を呼ばない', () => {
        const { result } = renderNovelManage();

        act(() => {
            result.current.handleEnqueueCtx();
        });

        expect(mockEnqueue).not.toHaveBeenCalled();
    });

    it('handleEnqueueBuild と handleEnqueueCtx は独立して動作する', async () => {
        mockedFetchBooks.mockResolvedValue([
            makeBook({ name: '本A', ocr_done_at: '2024-01-01', indexed_at: null }),
        ]);
        mockEnqueue.mockResolvedValue(undefined);

        const { result } = renderNovelManage();
        await waitFor(() => expect(result.current.selectedBook).toBe('本A'));

        act(() => {
            result.current.setAllBooks(true); // Full Build は全冊
            result.current.setAllBooksCtx(false); // コンテキストは個別
        });

        act(() => {
            result.current.handleEnqueueBuild();
        });
        act(() => {
            result.current.handleEnqueueCtx();
        });

        expect(mockEnqueue).toHaveBeenNthCalledWith(1, null, true, 'full_build');
        expect(mockEnqueue).toHaveBeenNthCalledWith(2, '本A', false, 'generate_contexts');
    });

    // --- unifiedRows 構築 ---

    it('ocrStatus=running のとき OCR 実行中行が含まれる', () => {
        setupMocks('running');
        const { result } = renderNovelManage();

        const row = result.current.unifiedRows.find((r) => r.key === 'ocr-running');
        expect(row).toBeDefined();
        expect(row?.state).toBe('実行中');
        expect(row?.type).toBe('OCR');
    });

    it('ocrStatus=error のとき OCR エラー行が含まれる', () => {
        setupMocks('error');
        const { result } = renderNovelManage();

        const row = result.current.unifiedRows.find((r) => r.key === 'ocr-error');
        expect(row).toBeDefined();
        expect(row?.state).toBe('エラー');
    });

    it('current_job があるとき build 実行中行が含まれる', () => {
        setupMocks('idle', {
            current_job: {
                id: 1,
                target_id: '海辺のカフカ',
                mode: 'full_build',
                progress_done: 0,
                progress_total: 1,
            },
        });
        const { result } = renderNovelManage();

        const row = result.current.unifiedRows.find((r) => r.key === 'build-running-1');
        expect(row).toBeDefined();
        expect(row?.target).toBe('海辺のカフカ');
        expect(row?.type).toBe('Full Build');
        expect(row?.state).toBe('実行中');
    });

    it('recent_finished の completed/failed/canceled が正しくラベル付けされる', () => {
        setupMocks('idle', {
            recent_finished: [
                {
                    id: 10,
                    target_id: 'A',
                    mode: 'full_build',
                    state: 'completed',
                    finished_at: '2024-01-01T00:00:00',
                    error_message: null,
                },
                {
                    id: 11,
                    target_id: 'B',
                    mode: 'full_build',
                    state: 'failed',
                    finished_at: '2024-01-02T00:00:00',
                    error_message: null,
                },
                {
                    id: 12,
                    target_id: 'C',
                    mode: 'generate_contexts',
                    state: 'canceled',
                    finished_at: '2024-01-03T00:00:00',
                    error_message: null,
                },
            ],
        });
        const { result } = renderNovelManage();

        const rows = result.current.unifiedRows;
        expect(rows.find((r) => r.key === 'build-finished-10')?.state).toBe('完了');
        expect(rows.find((r) => r.key === 'build-finished-11')?.state).toBe('失敗');
        expect(rows.find((r) => r.key === 'build-finished-12')?.state).toBe('キャンセル');
        expect(rows.find((r) => r.key === 'build-finished-12')?.type).toBe('コンテキスト生成');
    });

    it('target_id が null のとき target は "全冊"', () => {
        setupMocks('idle', {
            current_job: {
                id: 99,
                target_id: null,
                mode: 'full_build',
                progress_done: 0,
                progress_total: 1,
            },
        });
        const { result } = renderNovelManage();

        const row = result.current.unifiedRows.find((r) => r.key === 'build-running-99');
        expect(row?.target).toBe('全冊');
    });
});
