import { renderHook, act, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';

vi.mock('../config/api_client', () => ({
    default: { get: vi.fn(), post: vi.fn() },
}));

import apiClient from '../config/api_client';
import { useAutoFillAuthors } from '../hooks/useAutoFillAuthors';

const mockedGet = apiClient.get as ReturnType<typeof vi.fn>;
const mockedPost = apiClient.post as ReturnType<typeof vi.fn>;

describe('useAutoFillAuthors', () => {
    beforeEach(() => {
        mockedGet.mockReset();
        mockedPost.mockReset();
    });

    it('マウント時に GET /api/meta/auto-fill/status を呼ぶ', async () => {
        mockedGet.mockResolvedValue({
            status: 'idle',
            total: 0,
            done: 0,
            skipped: 0,
            current: '',
            results: [],
            error: '',
        });
        renderHook(() => useAutoFillAuthors('generated'));

        await waitFor(() => expect(mockedGet).toHaveBeenCalled());
        expect(mockedGet).toHaveBeenCalledWith('/api/meta/auto-fill/status', {
            params: { source: 'generated' },
        });
    });

    it('startAutoFill で POST /api/meta/auto-fill が呼ばれ、mode が params に乗る', async () => {
        mockedGet.mockResolvedValue({
            status: 'idle',
            total: 0,
            done: 0,
            skipped: 0,
            current: '',
            results: [],
            error: '',
        });
        mockedPost.mockResolvedValue(undefined);

        const { result } = renderHook(() => useAutoFillAuthors('generated'));
        await waitFor(() => expect(mockedGet).toHaveBeenCalled());

        await act(async () => {
            await result.current.startAutoFill('overwrite_all');
        });

        expect(mockedPost).toHaveBeenCalledWith('/api/meta/auto-fill', null, {
            params: { source: 'generated', mode: 'overwrite_all' },
        });
    });

    it('startAutoFill のデフォルト mode は unknown_only', async () => {
        mockedGet.mockResolvedValue({
            status: 'idle',
            total: 0,
            done: 0,
            skipped: 0,
            current: '',
            results: [],
            error: '',
        });
        mockedPost.mockResolvedValue(undefined);

        const { result } = renderHook(() => useAutoFillAuthors('generated'));
        await waitFor(() => expect(mockedGet).toHaveBeenCalled());

        await act(async () => {
            await result.current.startAutoFill();
        });

        const params = mockedPost.mock.calls[0][2].params;
        expect(params.mode).toBe('unknown_only');
    });

    it('idle 状態をそのまま jobStatus に反映する', async () => {
        mockedGet.mockResolvedValue({
            status: 'running',
            total: 10,
            done: 3,
            skipped: 1,
            current: 'book.pdf',
            results: [],
            error: '',
        });
        const { result } = renderHook(() => useAutoFillAuthors('generated'));

        await waitFor(() => expect(result.current.jobStatus.status).toBe('running'));
        expect(result.current.jobStatus.total).toBe(10);
        expect(result.current.jobStatus.current).toBe('book.pdf');
    });
});
