/**
 * useDiscussion: B-28 番組台本生成の SSE モック + 削除フロー。
 *
 * 注意: 初回レンダーで履歴フェッチが走るため、reject させると偽陽性
 * unhandledRejection が出る。「初回成功 → await act でエラー」パターンを使う。
 */
import { renderHook, act, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('../features/novel_db/sse', () => ({
    streamDiscussion: vi.fn(),
}));
vi.mock('../features/novel_db/api', () => ({
    fetchDiscussionHistory: vi.fn(),
    deleteDiscussion: vi.fn(),
}));

import { toast } from 'sonner';

import { deleteDiscussion, fetchDiscussionHistory } from '@/features/novel_db/api';
import { streamDiscussion } from '@/features/novel_db/sse';
import { useDiscussion } from '@/hooks/novel_db/useDiscussion';

function makeWrapper(initialEntry = '/novel/discussion?book=テスト本') {
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    return function Wrapper({ children }: { children: React.ReactNode }) {
        return (
            <QueryClientProvider client={queryClient}>
                <MemoryRouter initialEntries={[initialEntry]}>{children}</MemoryRouter>
            </QueryClientProvider>
        );
    };
}

describe('useDiscussion', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(fetchDiscussionHistory).mockResolvedValue([]);
    });

    it('URL の ?book= が selectedBook の初期値になり canGenerate が true', async () => {
        const { result } = renderHook(() => useDiscussion(), { wrapper: makeWrapper() });
        expect(result.current.selectedBook).toBe('テスト本');
        expect(result.current.canGenerate).toBe(true);
        await waitFor(() => {
            expect(fetchDiscussionHistory).toHaveBeenCalledWith('テスト本');
        });
    });

    it('書籍未選択では canGenerate が false', () => {
        const { result } = renderHook(() => useDiscussion(), {
            wrapper: makeWrapper('/novel/discussion'),
        });
        expect(result.current.canGenerate).toBe(false);
    });

    it('status/segment/turn/done イベントで state が更新される', async () => {
        vi.mocked(streamDiscussion).mockImplementation(async (_body, handlers) => {
            handlers.onStatus('planning');
            handlers.onSegment({ id: 'op_hook', title: 'OPフック' });
            handlers.onStatus('scripting');
            handlers.onTurn({ speaker: 'A', text: 'つかみ', segment: 'op_hook' });
            handlers.onTurn({ speaker: 'B', text: '返し', segment: 'op_hook' });
            handlers.onDone({
                saved_path: 'p.json',
                checks: {
                    passed: false,
                    results: [
                        { id: 'M1', label: '字数 3,000〜4,500', passed: false, detail: '2,681字' },
                    ],
                },
            });
        });

        const { result } = renderHook(() => useDiscussion(), { wrapper: makeWrapper() });

        await act(async () => {
            result.current.handleGenerate();
        });

        await waitFor(() => {
            expect(result.current.isGenerating).toBe(false);
        });
        expect(result.current.turns).toEqual([
            { speaker: 'A', text: 'つかみ', segment: 'op_hook' },
            { speaker: 'B', text: '返し', segment: 'op_hook' },
        ]);
        expect(result.current.segments).toEqual({ op_hook: 'OPフック' });
        expect(result.current.checks).toEqual({
            passed: false,
            results: [{ id: 'M1', label: '字数 3,000〜4,500', passed: false, detail: '2,681字' }],
        });
        expect(result.current.stage).toBe(null);
        // 完了後に履歴を再取得する（初回 + done 後）
        await waitFor(() => expect(fetchDiscussionHistory).toHaveBeenCalledTimes(2));
    });

    it('リクエスト body は book_name のみ', async () => {
        vi.mocked(streamDiscussion).mockImplementation(async (_body, handlers) => {
            handlers.onDone({ checks: null });
        });
        const { result } = renderHook(() => useDiscussion(), { wrapper: makeWrapper() });

        await act(async () => {
            result.current.handleGenerate();
        });

        expect(streamDiscussion).toHaveBeenCalledWith(
            { book_name: 'テスト本' },
            expect.anything(),
            expect.anything(),
        );
    });

    it('生成中は stage が更新される', async () => {
        let capturedHandlers: Parameters<typeof streamDiscussion>[1] | undefined;
        vi.mocked(streamDiscussion).mockImplementation(async (_body, handlers) => {
            capturedHandlers = handlers;
            return new Promise<void>(() => {}); // 解決しない
        });

        const { result } = renderHook(() => useDiscussion(), { wrapper: makeWrapper() });

        act(() => {
            result.current.handleGenerate();
        });
        expect(result.current.isGenerating).toBe(true);

        act(() => {
            capturedHandlers!.onStatus('planning');
        });
        expect(result.current.stage).toBe('planning');

        act(() => {
            capturedHandlers!.onStatus('scripting');
        });
        expect(result.current.stage).toBe('scripting');
    });

    it('onError で error が設定され stage がリセットされる', async () => {
        vi.mocked(streamDiscussion).mockImplementation(async (_body, handlers) => {
            handlers.onStatus('planning');
            handlers.onError(new Error('LLM unavailable'));
        });

        const { result } = renderHook(() => useDiscussion(), { wrapper: makeWrapper() });

        await act(async () => {
            result.current.handleGenerate();
        });

        await waitFor(() => {
            expect(result.current.error).toBe('LLM unavailable');
            expect(result.current.isGenerating).toBe(false);
            expect(result.current.stage).toBe(null);
        });
    });

    it('handleCancel で AbortController.abort が呼ばれる', async () => {
        let capturedSignal: AbortSignal | undefined;
        vi.mocked(streamDiscussion).mockImplementation(async (_body, _handlers, signal) => {
            capturedSignal = signal;
            return new Promise<void>(() => {});
        });

        const { result } = renderHook(() => useDiscussion(), { wrapper: makeWrapper() });

        act(() => {
            result.current.handleGenerate();
        });

        await waitFor(() => {
            expect(capturedSignal).toBeDefined();
            expect(capturedSignal!.aborted).toBe(false);
        });

        act(() => {
            result.current.handleCancel();
        });

        expect(capturedSignal!.aborted).toBe(true);
        expect(result.current.isGenerating).toBe(false);
    });

    it('handleDelete: 削除 → toast.success → 履歴再取得', async () => {
        vi.mocked(deleteDiscussion).mockResolvedValue({ status: 'deleted' });

        const { result } = renderHook(() => useDiscussion(), { wrapper: makeWrapper() });
        await waitFor(() => {
            expect(fetchDiscussionHistory).toHaveBeenCalledTimes(1);
        });

        await act(async () => {
            await result.current.handleDelete('20260707_script.json');
        });

        expect(deleteDiscussion).toHaveBeenCalledWith('テスト本', '20260707_script.json');
        expect(toast.success).toHaveBeenCalled();
        expect(fetchDiscussionHistory).toHaveBeenCalledTimes(2);
    });

    it('handleDelete 失敗時は toast.error（初回成功 → await act でエラー）', async () => {
        const { result } = renderHook(() => useDiscussion(), { wrapper: makeWrapper() });
        await waitFor(() => {
            expect(fetchDiscussionHistory).toHaveBeenCalledTimes(1);
        });

        vi.mocked(deleteDiscussion).mockRejectedValueOnce(new Error('404 not found'));

        await act(async () => {
            await result.current.handleDelete('missing.json');
        });

        expect(toast.error).toHaveBeenCalledWith('404 not found');
        expect(fetchDiscussionHistory).toHaveBeenCalledTimes(1); // 再取得しない
    });
});
