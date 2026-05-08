import { renderHook, act, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';

vi.mock('../config/api_client', () => ({
    default: { get: vi.fn() },
}));

import apiClient from '../config/api_client';
import { useUnresolvedSeriesCandidates } from '../hooks/useUnresolvedSeriesCandidates';

const mockedGet = apiClient.get as ReturnType<typeof vi.fn>;

describe('useUnresolvedSeriesCandidates', () => {
    beforeEach(() => {
        mockedGet.mockReset();
    });

    it('初期状態は candidates=null / loading=false / error=null', () => {
        const { result } = renderHook(() => useUnresolvedSeriesCandidates('generated'));
        expect(result.current.candidates).toBeNull();
        expect(result.current.loading).toBe(false);
        expect(result.current.error).toBeNull();
    });

    it('refresh() で API を叩き candidates をセットする', async () => {
        mockedGet.mockResolvedValue({
            candidates: [
                {
                    reason: 'short_prefix',
                    score: 0.75,
                    common_prefix: 'ABC',
                    books: [
                        { path: '', name: 'ABC1.pdf', title: 'ABC1' },
                        { path: '', name: 'ABC2.pdf', title: 'ABC2' },
                    ],
                },
            ],
        });
        const { result } = renderHook(() => useUnresolvedSeriesCandidates('generated'));
        await act(async () => {
            await result.current.refresh();
        });
        expect(mockedGet).toHaveBeenCalledWith('/api/series/unresolved-candidates', {
            params: { source: 'generated' },
        });
        expect(result.current.candidates).toHaveLength(1);
        expect(result.current.candidates![0].common_prefix).toBe('ABC');
    });

    it('refresh() 中は loading=true', async () => {
        let resolveFn!: (v: unknown) => void;
        mockedGet.mockReturnValue(
            new Promise((res) => {
                resolveFn = res;
            }),
        );
        const { result } = renderHook(() => useUnresolvedSeriesCandidates('generated'));
        act(() => {
            result.current.refresh();
        });
        await waitFor(() => expect(result.current.loading).toBe(true));
        await act(async () => {
            resolveFn({ candidates: [] });
        });
        await waitFor(() => expect(result.current.loading).toBe(false));
    });

    it('GET 失敗で error がセットされ candidates は null のまま', async () => {
        mockedGet.mockRejectedValue(new Error('boom'));
        const { result } = renderHook(() => useUnresolvedSeriesCandidates('generated'));
        await act(async () => {
            await result.current.refresh();
        });
        expect(result.current.error).toBe('boom');
        expect(result.current.candidates).toBeNull();
    });

    it('reset() で candidates と error をクリアする', async () => {
        mockedGet.mockResolvedValue({ candidates: [] });
        const { result } = renderHook(() => useUnresolvedSeriesCandidates('generated'));
        await act(async () => {
            await result.current.refresh();
        });
        expect(result.current.candidates).toEqual([]);
        act(() => {
            result.current.reset();
        });
        expect(result.current.candidates).toBeNull();
        expect(result.current.error).toBeNull();
    });
});
