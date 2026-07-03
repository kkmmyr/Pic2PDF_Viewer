/**
 * useNovelBuildQueue フックのユニットテスト。
 * SSE ストリームは connectBuildStream をモックして状態変化をシミュレートする。
 */
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../config/api_client', () => ({
    default: { post: vi.fn(), delete: vi.fn() },
}));

vi.mock('../features/novel_build/sse', () => ({
    connectBuildStream: vi.fn(),
}));

import apiClient from '@/config/api_client';
import { connectBuildStream } from '@/features/novel_build/sse';
import type { BuildQueueStatus } from '@/features/novel_build/sse';
import { useNovelBuildQueue } from '@/hooks/novel_build/useNovelBuildQueue';

const mockedPost = apiClient.post as ReturnType<typeof vi.fn>;
const mockedDelete = apiClient.delete as ReturnType<typeof vi.fn>;
const mockedConnect = connectBuildStream as ReturnType<typeof vi.fn>;

const EMPTY_STATUS: BuildQueueStatus = {
    is_running: false,
    current_job: null,
    queued_jobs: [],
    recent_finished: [],
};

describe('useNovelBuildQueue', () => {
    let capturedOnStatus: ((s: BuildQueueStatus) => void) | null = null;
    const mockClose = vi.fn();

    beforeEach(() => {
        capturedOnStatus = null;
        mockClose.mockReset();
        mockedPost.mockReset();
        mockedDelete.mockReset();
        mockedConnect.mockImplementation(
            (handlers: { onStatus: (s: BuildQueueStatus) => void }) => {
                capturedOnStatus = handlers.onStatus;
                return mockClose;
            },
        );
    });

    it('マウント時に connectBuildStream が呼ばれる', () => {
        renderHook(() => useNovelBuildQueue());
        expect(mockedConnect).toHaveBeenCalledTimes(1);
    });

    it('SSE イベント受信で status が更新される', async () => {
        const { result } = renderHook(() => useNovelBuildQueue());
        expect(result.current.status.is_running).toBe(false);

        const newStatus: BuildQueueStatus = {
            is_running: true,
            current_job: { id: 1, target_id: '花太郎', progress_done: 0, progress_total: 1 },
            queued_jobs: [],
            recent_finished: [],
        };

        act(() => {
            capturedOnStatus?.(newStatus);
        });

        expect(result.current.status.is_running).toBe(true);
        expect(result.current.status.current_job?.target_id).toBe('花太郎');
    });

    it('アンマウント時に close が呼ばれる', () => {
        const { unmount } = renderHook(() => useNovelBuildQueue());
        unmount();
        expect(mockClose).toHaveBeenCalledTimes(1);
    });

    it('SSE エラー時に旧接続を close してから再接続する（接続リーク防止）', () => {
        // React の内部スケジューラは setTimeout/MessageChannel に依存するため、
        // 対象を setTimeout/clearTimeout のみに絞ってフェイクする（全体フェイクだと mount 自体が壊れる）。
        vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
        try {
            let capturedOnError: (() => void) | null = null;
            const closeFns = [vi.fn(), vi.fn()];
            let callCount = 0;
            mockedConnect.mockImplementation(
                (handlers: { onStatus: (s: BuildQueueStatus) => void; onError: () => void }) => {
                    capturedOnStatus = handlers.onStatus;
                    capturedOnError = handlers.onError;
                    return closeFns[callCount++];
                },
            );
            mockedConnect.mockClear(); // 前のテストの呼び出し回数を引き継がないようリセット

            renderHook(() => useNovelBuildQueue());
            expect(mockedConnect).toHaveBeenCalledTimes(1);

            // 1 回目の接続でエラー発生 → 旧接続が即座に close され、3 秒後に再接続される
            act(() => {
                capturedOnError?.();
            });
            expect(closeFns[0]).toHaveBeenCalledTimes(1);
            expect(mockedConnect).toHaveBeenCalledTimes(1); // まだ再接続していない

            act(() => {
                vi.advanceTimersByTime(3000);
            });
            expect(mockedConnect).toHaveBeenCalledTimes(2);
            expect(closeFns[1]).not.toHaveBeenCalled();
        } finally {
            vi.useRealTimers();
        }
    });

    it('enqueue — 成功時に POST が呼ばれ isEnqueuing が戻る', async () => {
        mockedPost.mockResolvedValue({ job_id: 10, queued_position: 1 });
        const { result } = renderHook(() => useNovelBuildQueue());

        await act(async () => {
            await result.current.enqueue('花太郎', false);
        });

        expect(mockedPost).toHaveBeenCalledWith('/api/novel/build/enqueue', {
            book_name: '花太郎',
            all_books: false,
            mode: 'full_build',
        });
        expect(result.current.isEnqueuing).toBe(false);
        expect(result.current.enqueueError).toBeNull();
    });

    it('enqueue — 失敗時に enqueueError が設定される', async () => {
        mockedPost.mockRejectedValue({
            response: { data: { detail: 'already queued or running' } },
        });
        const { result } = renderHook(() => useNovelBuildQueue());

        await act(async () => {
            await result.current.enqueue('花太郎', false);
        });

        expect(result.current.enqueueError).toBe('already queued or running');
        expect(result.current.isEnqueuing).toBe(false);
    });

    it('cancel — DELETE が呼ばれる', async () => {
        mockedDelete.mockResolvedValue(undefined);
        const { result } = renderHook(() => useNovelBuildQueue());

        await act(async () => {
            await result.current.cancel(5);
        });

        expect(mockedDelete).toHaveBeenCalledWith('/api/novel/build/jobs/5');
    });

    it('cancel — 失敗しても hook は壊れない', async () => {
        mockedDelete.mockRejectedValue(new Error('404'));
        const { result } = renderHook(() => useNovelBuildQueue());

        await expect(
            act(async () => {
                await result.current.cancel(99);
            }),
        ).resolves.not.toThrow();
    });

    it('初期 status は EMPTY_STATUS', () => {
        const { result } = renderHook(() => useNovelBuildQueue());
        expect(result.current.status).toEqual(EMPTY_STATUS);
    });

    it('全冊 enqueue は all_books=true で送信する', async () => {
        mockedPost.mockResolvedValue({ job_id: 20, queued_position: 1 });
        const { result } = renderHook(() => useNovelBuildQueue());

        await act(async () => {
            await result.current.enqueue(null, true);
        });

        expect(mockedPost).toHaveBeenCalledWith('/api/novel/build/enqueue', {
            book_name: null,
            all_books: true,
            mode: 'full_build',
        });
    });

    it('SSE で queued_jobs が更新されると待機中リストが増える', async () => {
        const { result } = renderHook(() => useNovelBuildQueue());

        const updated: BuildQueueStatus = {
            ...EMPTY_STATUS,
            queued_jobs: [
                { id: 2, target_id: '千の刀' },
                { id: 3, target_id: '海辺のカフカ' },
            ],
        };

        act(() => {
            capturedOnStatus?.(updated);
        });

        await waitFor(() => {
            expect(result.current.status.queued_jobs).toHaveLength(2);
        });
    });
});
