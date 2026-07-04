import React from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi, describe, it, expect, beforeEach } from 'vitest';

vi.mock('../config/generate_api_client', () => ({
    default: { get: vi.fn() },
}));

import generateApiClient from '@/config/generate_api_client';
import { useDoujinWatcher } from '@/hooks/useDoujinWatcher';
import type { DoujinWatcherStatus } from '@/types';

const mockedGet = generateApiClient.get as ReturnType<typeof vi.fn>;

const buildWatcher = (overrides: Partial<DoujinWatcherStatus> = {}): DoujinWatcherStatus => ({
    enabled: true,
    state: 'idle',
    interval_sec: 15,
    last_scan_at: null,
    pending_items: [],
    active_job_id: null,
    last_auto_job: null,
    retry_blocked: false,
    ...overrides,
});

const createWrapper = () => {
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false, staleTime: 0, gcTime: 30_000 } },
    });
    return ({ children }: { children: React.ReactNode }) =>
        React.createElement(QueryClientProvider, { client: queryClient }, children);
};

describe('useDoujinWatcher', () => {
    beforeEach(() => {
        mockedGet.mockReset();
    });

    it('成功時にレスポンスが watcher として反映される', async () => {
        const watcherStatus = buildWatcher({ state: 'running', active_job_id: 'job-1' });
        mockedGet.mockResolvedValue(watcherStatus);

        const { result } = renderHook(() => useDoujinWatcher(), { wrapper: createWrapper() });

        await waitFor(() => expect(result.current.watcher).not.toBeNull());
        expect(result.current.watcher?.state).toBe('running');
        expect(result.current.watcher?.active_job_id).toBe('job-1');
        expect(result.current.isError).toBe(false);
    });

    it('GET 失敗時は throw せず watcher=null のまま返す', async () => {
        mockedGet.mockRejectedValue(new Error('network down'));

        const { result } = renderHook(() => useDoujinWatcher(), { wrapper: createWrapper() });

        await waitFor(() => expect(result.current.isError).toBe(true));
        expect(result.current.watcher).toBeNull();
    });
});
