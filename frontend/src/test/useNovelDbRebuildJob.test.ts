/**
 * useNovelDbRebuildJob フックのユニットテスト（55-8）
 *
 * テスト観点:
 * - enqueue 成功 → polling → onJobCompleted 呼び出し
 * - enqueue エラー → error state にセット
 * - cancel → polling 停止
 */
import React from 'react';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';

import * as api from '@/features/novel_db/api';
import { useNovelDbRebuildJob } from '@/hooks/novel_db/useNovelDbRebuildJob';
import type { RebuildStatus } from '@/features/novel_db/types';

const IDLE_STATUS: RebuildStatus = {
    is_running: false,
    current_job: null,
    queued_jobs: [],
    recent_finished: [],
};

const RUNNING_STATUS: RebuildStatus = {
    is_running: true,
    current_job: { id: 1, type: 'book', target_id: 'テスト本', mode: 'rebuild' },
    queued_jobs: [],
    recent_finished: [],
};

const createWrapper = () => {
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false, staleTime: 0, gcTime: 30_000 } },
    });
    return ({ children }: { children: React.ReactNode }) =>
        React.createElement(QueryClientProvider, { client: queryClient }, children);
};

describe('useNovelDbRebuildJob', () => {
    beforeEach(() => {
        vi.useFakeTimers({ shouldAdvanceTime: true });
        vi.spyOn(api, 'fetchRebuildStatus').mockResolvedValue(IDLE_STATUS);
        vi.spyOn(api, 'postRebuild').mockResolvedValue({ job_id: 1, queued_position: 0 });
        vi.spyOn(api, 'cancelRebuild').mockResolvedValue(undefined);
    });

    afterEach(() => {
        vi.useRealTimers();
        vi.restoreAllMocks();
    });

    it('マウント直後に fetchRebuildStatus を呼んで status をセットする', async () => {
        const { result } = renderHook(() => useNovelDbRebuildJob(), { wrapper: createWrapper() });

        await waitFor(() => {
            expect(api.fetchRebuildStatus).toHaveBeenCalledTimes(1);
            expect(result.current.status).toEqual(IDLE_STATUS);
        });
        expect(result.current.isLoading).toBe(false);
        expect(result.current.error).toBeNull();
    });

    it('5 秒間隔で polling する', async () => {
        renderHook(() => useNovelDbRebuildJob(), { wrapper: createWrapper() });

        await act(async () => {
            await Promise.resolve();
            await Promise.resolve();
        });
        expect(api.fetchRebuildStatus).toHaveBeenCalledTimes(1);

        await act(async () => {
            await vi.advanceTimersByTimeAsync(5000);
        });
        expect(api.fetchRebuildStatus).toHaveBeenCalledTimes(2);

        await act(async () => {
            await vi.advanceTimersByTimeAsync(5000);
        });
        expect(api.fetchRebuildStatus).toHaveBeenCalledTimes(3);
    });

    it('running → !running の遷移で onJobCompleted が呼ばれる', async () => {
        // 1 回目: running、2 回目: idle で完了検知
        vi.spyOn(api, 'fetchRebuildStatus')
            .mockResolvedValueOnce(RUNNING_STATUS)
            .mockResolvedValue(IDLE_STATUS);

        const onCompleted = vi.fn();
        const { result } = renderHook(() => useNovelDbRebuildJob(onCompleted), {
            wrapper: createWrapper(),
        });

        // 1 回目 fetch: running — wait for state to propagate
        await waitFor(() => {
            expect(result.current.status?.is_running).toBe(true);
        });
        expect(onCompleted).not.toHaveBeenCalled();

        // 2 回目 fetch: idle → 完了検知
        await act(async () => {
            await vi.advanceTimersByTimeAsync(5000);
        });
        await waitFor(() => {
            expect(onCompleted).toHaveBeenCalledTimes(1);
        });
    });

    it('enqueue → postRebuild + refresh が呼ばれ job_id を返す', async () => {
        const { result } = renderHook(() => useNovelDbRebuildJob(), { wrapper: createWrapper() });
        await act(async () => {
            await Promise.resolve();
            await Promise.resolve();
        });

        let res: { job_id: number; queued_position: number } | undefined;
        await act(async () => {
            res = await result.current.enqueue({ type: 'book', target_id: 'テスト本' });
        });

        expect(api.postRebuild).toHaveBeenCalledWith({ type: 'book', target_id: 'テスト本' });
        expect(res?.job_id).toBe(1);
        // enqueue 後に refresh も呼ばれる（合計 2 回以上）
        await waitFor(() => expect(api.fetchRebuildStatus).toHaveBeenCalledTimes(2));
    });

    it('enqueue 失敗時に error がセットされる', async () => {
        vi.spyOn(api, 'postRebuild').mockRejectedValue(new Error('server error'));

        const { result } = renderHook(() => useNovelDbRebuildJob(), { wrapper: createWrapper() });
        await act(async () => {
            await Promise.resolve();
            await Promise.resolve();
        });

        await act(async () => {
            await expect(
                result.current.enqueue({ type: 'book', target_id: 'テスト本' }),
            ).rejects.toThrow('server error');
        });
    });

    it('cancel → cancelRebuild + refresh が呼ばれる', async () => {
        const { result } = renderHook(() => useNovelDbRebuildJob(), { wrapper: createWrapper() });
        await act(async () => {
            await Promise.resolve();
            await Promise.resolve();
        });

        await act(async () => {
            await result.current.cancel(42);
        });

        expect(api.cancelRebuild).toHaveBeenCalledWith(42);
        await waitFor(() => expect(api.fetchRebuildStatus).toHaveBeenCalledTimes(2));
    });

    it('アンマウント後は polling が止まる', async () => {
        const { unmount } = renderHook(() => useNovelDbRebuildJob(), { wrapper: createWrapper() });
        await act(async () => {
            await Promise.resolve();
            await Promise.resolve();
        });
        unmount();

        await act(async () => {
            await vi.advanceTimersByTimeAsync(15000);
        });
        expect(api.fetchRebuildStatus).toHaveBeenCalledTimes(1);
    });
});
