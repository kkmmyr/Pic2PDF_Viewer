import React from 'react';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi, describe, it, expect, beforeEach } from 'vitest';

vi.mock('../config/api_client', () => ({
    default: { get: vi.fn(), post: vi.fn() },
}));

import apiClient from '@/config/api_client';
import { useOcrStatus } from '@/hooks/useOcrStatus';

const mockedGet = apiClient.get as ReturnType<typeof vi.fn>;
const mockedPost = apiClient.post as ReturnType<typeof vi.fn>;

const createWrapper = () => {
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false, staleTime: 0, gcTime: 30_000 } },
    });
    return ({ children }: { children: React.ReactNode }) =>
        React.createElement(QueryClientProvider, { client: queryClient }, children);
};

describe('useOcrStatus', () => {
    beforeEach(() => {
        mockedGet.mockReset();
        mockedPost.mockReset();
    });

    it('マウント時に GET /api/ocr/status が呼ばれ、status と logs が反映される', async () => {
        mockedGet.mockResolvedValue({
            status: 'idle',
            last_return_code: 0,
            logs: ['line1', 'line2'],
        });
        const { result } = renderHook(() => useOcrStatus(), { wrapper: createWrapper() });

        await waitFor(() => expect(mockedGet).toHaveBeenCalledWith('/api/ocr/status'));
        await waitFor(() => expect(result.current.logs).toEqual(['line1', 'line2']));
        expect(result.current.status).toBe('idle');
    });

    it('running ステータスもそのまま反映される', async () => {
        mockedGet.mockResolvedValue({
            status: 'running',
            last_return_code: null,
            logs: [],
        });
        const { result } = renderHook(() => useOcrStatus(), { wrapper: createWrapper() });

        await waitFor(() => expect(result.current.status).toBe('running'));
    });

    it('GET が throw しても hook は壊れない（status は初期値 idle のまま）', async () => {
        mockedGet.mockRejectedValue(new Error('boom'));
        const { result } = renderHook(() => useOcrStatus(), { wrapper: createWrapper() });

        // 初期 idle のまま
        expect(result.current.status).toBe('idle');
        expect(result.current.logs).toEqual([]);
    });

    it('startOcr で POST /api/ocr/run（target_dir 付き）', async () => {
        mockedGet.mockResolvedValue({ status: 'idle', last_return_code: null, logs: [] });
        mockedPost.mockResolvedValue(undefined);

        const { result } = renderHook(() => useOcrStatus(), { wrapper: createWrapper() });
        await waitFor(() => expect(mockedGet).toHaveBeenCalled());

        await act(async () => {
            await result.current.startOcr('/some/dir');
        });

        expect(mockedPost).toHaveBeenCalledWith('/api/ocr/run', { target_dir: '/some/dir' });
    });

    it('startOcr で target_dir 省略時は undefined が渡る', async () => {
        mockedGet.mockResolvedValue({ status: 'idle', last_return_code: null, logs: [] });
        mockedPost.mockResolvedValue(undefined);

        const { result } = renderHook(() => useOcrStatus(), { wrapper: createWrapper() });
        await waitFor(() => expect(mockedGet).toHaveBeenCalled());

        await act(async () => {
            await result.current.startOcr();
        });

        expect(mockedPost).toHaveBeenCalledWith('/api/ocr/run', { target_dir: undefined });
    });

    it('stopOcr で POST /api/ocr/stop', async () => {
        mockedGet.mockResolvedValue({ status: 'idle', last_return_code: null, logs: [] });
        mockedPost.mockResolvedValue(undefined);

        const { result } = renderHook(() => useOcrStatus(), { wrapper: createWrapper() });
        await waitFor(() => expect(mockedGet).toHaveBeenCalled());

        await act(async () => {
            await result.current.stopOcr();
        });

        expect(mockedPost).toHaveBeenCalledWith('/api/ocr/stop');
    });

    it('refetch で手動フェッチできる', async () => {
        mockedGet.mockResolvedValue({ status: 'idle', last_return_code: null, logs: [] });
        const { result } = renderHook(() => useOcrStatus(), { wrapper: createWrapper() });
        await waitFor(() => expect(mockedGet).toHaveBeenCalledTimes(1));

        await act(async () => {
            await result.current.refetch();
        });
        expect(mockedGet).toHaveBeenCalledTimes(2);
    });
});
