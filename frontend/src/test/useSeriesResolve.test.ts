import { renderHook, act, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';

vi.mock('../config/api_client', () => ({
    default: { get: vi.fn(), post: vi.fn() },
}));

import apiClient from '../config/api_client';
import { useSeriesResolve } from '../hooks/useSeriesResolve';

const mockedGet = apiClient.get as ReturnType<typeof vi.fn>;
const mockedPost = apiClient.post as ReturnType<typeof vi.fn>;

const IDLE = {
    status: 'idle' as const,
    total: 0,
    done: 0,
    created: 0,
    current: '',
    error: '',
};

describe('useSeriesResolve', () => {
    beforeEach(() => {
        mockedGet.mockReset();
        mockedPost.mockReset();
    });

    it('マウント時に GET /api/series/resolve/status を呼ぶ', async () => {
        mockedGet.mockResolvedValue(IDLE);
        renderHook(() => useSeriesResolve('generated'));

        await waitFor(() => expect(mockedGet).toHaveBeenCalled());
        expect(mockedGet).toHaveBeenCalledWith('/api/series/resolve/status', {
            params: { source: 'generated' },
        });
    });

    it('startResolve(true) で use_gemma=true が params に乗る', async () => {
        mockedGet.mockResolvedValue(IDLE);
        mockedPost.mockResolvedValue(undefined);

        const { result } = renderHook(() => useSeriesResolve('generated'));
        await waitFor(() => expect(mockedGet).toHaveBeenCalled());

        await act(async () => {
            await result.current.startResolve(true);
        });

        expect(mockedPost).toHaveBeenCalledWith('/api/series/resolve', null, {
            params: { source: 'generated', use_gemma: true },
        });
    });

    it('startResolve のデフォルトは use_gemma=false', async () => {
        mockedGet.mockResolvedValue(IDLE);
        mockedPost.mockResolvedValue(undefined);

        const { result } = renderHook(() => useSeriesResolve('generated'));
        await waitFor(() => expect(mockedGet).toHaveBeenCalled());

        await act(async () => {
            await result.current.startResolve();
        });

        expect(mockedPost.mock.calls[0][2].params.use_gemma).toBe(false);
    });

    it('jobStatus.status が running なら反映される', async () => {
        mockedGet.mockResolvedValue({ ...IDLE, status: 'running', total: 5, done: 2 });
        const { result } = renderHook(() => useSeriesResolve('generated'));

        await waitFor(() => expect(result.current.jobStatus.status).toBe('running'));
        expect(result.current.jobStatus.total).toBe(5);
        expect(result.current.jobStatus.done).toBe(2);
    });
});
