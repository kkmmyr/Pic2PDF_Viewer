import { renderHook, act, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';

vi.mock('../config/api_client', () => ({
    default: { get: vi.fn(), post: vi.fn() },
}));

import apiClient from '../config/api_client';
import { useJobPolling } from '../hooks/useJobPolling';

const mockedGet = apiClient.get as ReturnType<typeof vi.fn>;
const mockedPost = apiClient.post as ReturnType<typeof vi.fn>;

interface FakeStatus {
    status: 'idle' | 'running' | 'done' | 'error';
    progress: number;
}
const IDLE: FakeStatus = { status: 'idle', progress: 0 };

const renderJobPolling = (onComplete?: () => void) =>
    renderHook(() =>
        useJobPolling<FakeStatus>({
            source: 'generated',
            statusUrl: '/api/fake/status',
            startUrl: '/api/fake/start',
            idleStatus: IDLE,
            onComplete,
        }),
    );

describe('useJobPolling', () => {
    beforeEach(() => {
        mockedGet.mockReset();
        mockedPost.mockReset();
        vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    it('マウント時に source の現在ステータスを取得する', async () => {
        mockedGet.mockResolvedValue(IDLE);
        const { result } = renderJobPolling();

        await waitFor(() => expect(mockedGet).toHaveBeenCalled());
        expect(mockedGet).toHaveBeenCalledWith('/api/fake/status', {
            params: { source: 'generated' },
        });
        expect(result.current.jobStatus.status).toBe('idle');
    });

    it('マウント時に running ステータスが返ればポーリングを開始する', async () => {
        mockedGet.mockResolvedValue({ status: 'running', progress: 1 });
        renderJobPolling();

        await waitFor(() => expect(mockedGet).toHaveBeenCalledTimes(1));

        // インターバル進行で 2 回目以降の get が呼ばれる
        await act(async () => {
            await vi.advanceTimersByTimeAsync(1500);
        });
        expect(mockedGet.mock.calls.length).toBeGreaterThanOrEqual(2);
    });

    it('startJob で POST → 直後に fetchStatus が走る', async () => {
        mockedGet.mockResolvedValue(IDLE);
        mockedPost.mockResolvedValue(undefined);

        const { result } = renderJobPolling();
        await waitFor(() => expect(mockedGet).toHaveBeenCalledTimes(1));

        // running を返す mock に切り替える
        mockedGet.mockResolvedValue({ status: 'running', progress: 5 });

        await act(async () => {
            await result.current.startJob({ extra: 'param' });
        });

        expect(mockedPost).toHaveBeenCalledWith('/api/fake/start', null, {
            params: { source: 'generated', extra: 'param' },
        });
        // fetchStatus が直後に呼ばれて running 状態になる
        await waitFor(() => expect(result.current.jobStatus.status).toBe('running'));
    });

    it('done ステータスで onComplete が呼ばれ、ポーリングが停止する', async () => {
        const onComplete = vi.fn();
        mockedGet.mockResolvedValue(IDLE);
        mockedPost.mockResolvedValue(undefined);

        const { result } = renderJobPolling(onComplete);
        await waitFor(() => expect(mockedGet).toHaveBeenCalledTimes(1));

        // running → done の流れに切り替える
        mockedGet.mockResolvedValueOnce({ status: 'running', progress: 50 });
        mockedGet.mockResolvedValueOnce({ status: 'done', progress: 100 });
        mockedGet.mockResolvedValue({ status: 'done', progress: 100 });

        await act(async () => {
            await result.current.startJob();
        });

        await act(async () => {
            await vi.advanceTimersByTimeAsync(1500);
        });
        await act(async () => {
            await vi.advanceTimersByTimeAsync(1500);
        });

        await waitFor(() => expect(onComplete).toHaveBeenCalled());

        // ポーリング停止後にさらに進めても get が増えない
        const callsAfterDone = mockedGet.mock.calls.length;
        await act(async () => {
            await vi.advanceTimersByTimeAsync(5000);
        });
        expect(mockedGet.mock.calls.length).toBe(callsAfterDone);
    });

    it('error ステータスでもポーリングが停止する（onComplete は呼ばれない）', async () => {
        const onComplete = vi.fn();
        mockedGet.mockResolvedValue({ status: 'error', progress: 0 });

        const { result } = renderJobPolling(onComplete);
        // useEffect の async IIFE が解決するのを待つ
        await act(async () => {
            await Promise.resolve();
            await Promise.resolve();
        });
        expect(result.current.jobStatus.status).toBe('error');

        const callsAfter = mockedGet.mock.calls.length;
        await act(async () => {
            await vi.advanceTimersByTimeAsync(5000);
        });
        expect(mockedGet.mock.calls.length).toBe(callsAfter);
        expect(onComplete).not.toHaveBeenCalled();
    });

    it('source 変更時に jobStatus が idle にリセットされ、再フェッチされる', async () => {
        mockedGet.mockResolvedValue(IDLE);
        const { result, rerender } = renderHook(
            ({ src }: { src: 'generated' | 'kindle' }) =>
                useJobPolling<FakeStatus>({
                    source: src,
                    statusUrl: '/api/fake/status',
                    startUrl: '/api/fake/start',
                    idleStatus: IDLE,
                }),
            { initialProps: { src: 'generated' } },
        );
        await waitFor(() => expect(mockedGet).toHaveBeenCalledTimes(1));

        rerender({ src: 'kindle' });
        await waitFor(() => expect(mockedGet).toHaveBeenCalledTimes(2));
        expect(result.current.jobStatus).toEqual(IDLE);
        expect(mockedGet.mock.calls[1][1]).toEqual({ params: { source: 'kindle' } });
    });

    it('アンマウントでポーリングが停止する', async () => {
        mockedGet.mockResolvedValue({ status: 'running', progress: 0 });
        const { unmount } = renderJobPolling();

        await waitFor(() => expect(mockedGet).toHaveBeenCalledTimes(1));
        unmount();

        const callsBefore = mockedGet.mock.calls.length;
        await act(async () => {
            await vi.advanceTimersByTimeAsync(5000);
        });
        expect(mockedGet.mock.calls.length).toBe(callsBefore);
    });
});
