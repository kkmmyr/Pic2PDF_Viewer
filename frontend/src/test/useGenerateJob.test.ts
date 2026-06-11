import React from 'react';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi, describe, it, expect, beforeEach } from 'vitest';

vi.mock('../config/generate_api_client', () => ({
    default: { get: vi.fn() },
}));

import generateApiClient from '@/config/generate_api_client';
import { ApiError } from '@/config/api_client';
import { useGenerateJob } from '@/hooks/useGenerateJob';
import type { GenerateJob } from '@/types';

const mockedGet = generateApiClient.get as ReturnType<typeof vi.fn>;

const STORAGE_KEY = 'generator_active_job';

const buildJob = (overrides: Partial<GenerateJob> = {}): GenerateJob => ({
    job_id: 'jid-1',
    status: 'pending',
    current_item: null,
    files: [],
    failed_items: [],
    message: '',
    error: null,
    ...overrides,
});

const createWrapper = () => {
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false, staleTime: 0, gcTime: 30_000 } },
    });
    return ({ children }: { children: React.ReactNode }) =>
        React.createElement(QueryClientProvider, { client: queryClient }, children);
};

describe('useGenerateJob', () => {
    beforeEach(() => {
        mockedGet.mockReset();
        localStorage.clear();
    });

    it('初期状態: localStorage が空なら currentJob=null', () => {
        const { result } = renderHook(() => useGenerateJob(vi.fn(), vi.fn()), {
            wrapper: createWrapper(),
        });
        expect(result.current.currentJob).toBeNull();
        expect(result.current.isGenerating).toBe(false);
        expect(result.current.isRestoredJob).toBe(false);
    });

    it('startJob で localStorage に保存され、currentJob が pending 状態になる', () => {
        const { result } = renderHook(() => useGenerateJob(vi.fn(), vi.fn()), {
            wrapper: createWrapper(),
        });
        act(() => {
            result.current.startJob('jid-1');
        });
        expect(result.current.currentJob?.job_id).toBe('jid-1');
        expect(result.current.currentJob?.status).toBe('pending');
        expect(result.current.isGenerating).toBe(true);

        const stored = JSON.parse(localStorage.getItem(STORAGE_KEY)!);
        expect(stored).toEqual({ job_id: 'jid-1' });
    });

    it('localStorage に既存ジョブがあるとマウント時に復元される（isRestoredJob=true）', () => {
        localStorage.setItem(STORAGE_KEY, JSON.stringify({ job_id: 'restored' }));
        const { result } = renderHook(() => useGenerateJob(vi.fn(), vi.fn()), {
            wrapper: createWrapper(),
        });
        expect(result.current.currentJob?.job_id).toBe('restored');
        expect(result.current.isGenerating).toBe(true);
        expect(result.current.isRestoredJob).toBe(true);
    });

    it('clearCurrentJob で localStorage と state が消える', () => {
        localStorage.setItem(STORAGE_KEY, JSON.stringify({ job_id: 'jid-1' }));
        const { result } = renderHook(() => useGenerateJob(vi.fn(), vi.fn()), {
            wrapper: createWrapper(),
        });
        expect(result.current.currentJob).not.toBeNull();

        act(() => {
            result.current.clearCurrentJob();
        });
        expect(result.current.currentJob).toBeNull();
        expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
    });

    it('completed 検知で onCompleted が呼ばれ、localStorage が消える', async () => {
        const onCompleted = vi.fn();
        const onFailed = vi.fn();
        mockedGet.mockResolvedValue(buildJob({ status: 'completed', files: ['a.pdf'] }));

        const { result } = renderHook(() => useGenerateJob(onCompleted, onFailed), {
            wrapper: createWrapper(),
        });
        act(() => {
            result.current.startJob('jid-1');
        });

        await waitFor(() => expect(onCompleted).toHaveBeenCalledTimes(1));
        expect(onCompleted.mock.calls[0][0].status).toBe('completed');
        expect(onFailed).not.toHaveBeenCalled();
        expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
    });

    it('failed 検知で onFailed が呼ばれ、localStorage が消える', async () => {
        const onCompleted = vi.fn();
        const onFailed = vi.fn();
        mockedGet.mockResolvedValue(buildJob({ status: 'failed', error: 'oops' }));

        const { result } = renderHook(() => useGenerateJob(onCompleted, onFailed), {
            wrapper: createWrapper(),
        });
        act(() => {
            result.current.startJob('jid-1');
        });

        await waitFor(() => expect(onFailed).toHaveBeenCalledTimes(1));
        expect(onCompleted).not.toHaveBeenCalled();
        expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
    });

    it('404 エラーでジョブをクリアする（サーバー再起動時のリセット）', async () => {
        const onCompleted = vi.fn();
        const onFailed = vi.fn();
        mockedGet.mockRejectedValue(new ApiError('not found', 404, 'client'));

        const { result } = renderHook(() => useGenerateJob(onCompleted, onFailed), {
            wrapper: createWrapper(),
        });
        act(() => {
            result.current.startJob('jid-1');
        });

        await waitFor(() => expect(result.current.currentJob).toBeNull());
        expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
        expect(onCompleted).not.toHaveBeenCalled();
        expect(onFailed).not.toHaveBeenCalled();
    });

    it('500 エラーではジョブをクリアしない（リトライ可能）', async () => {
        mockedGet.mockRejectedValue(new ApiError('server error', 500, 'server'));

        const { result } = renderHook(() => useGenerateJob(vi.fn(), vi.fn()), {
            wrapper: createWrapper(),
        });
        act(() => {
            result.current.startJob('jid-1');
        });

        await waitFor(() => expect(mockedGet).toHaveBeenCalled());

        // currentJob はそのまま残る（pending stub）
        expect(result.current.currentJob?.job_id).toBe('jid-1');
    });
});
