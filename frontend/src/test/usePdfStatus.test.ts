import { renderHook, act, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';

vi.mock('../config/api_client', () => ({
    default: { get: vi.fn() },
}));

import apiClient from '../config/api_client';
import { usePdfStatus } from '../hooks/usePdfStatus';

const mockedGet = apiClient.get as ReturnType<typeof vi.fn>;

describe('usePdfStatus', () => {
    beforeEach(() => {
        mockedGet.mockReset();
        vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    it('enabled=false（既定）ではマウント時にフェッチしない', () => {
        renderHook(() => usePdfStatus('/some/dir'));
        expect(mockedGet).not.toHaveBeenCalled();
    });

    it('enabled=true でマウント時にフェッチし items を反映する', async () => {
        mockedGet.mockResolvedValue({
            items: [
                { name: 'a.pdf', type: 'pdf', status: 'completed' as const },
                { name: 'b', type: 'folder', status: 'in_progress' as const },
            ],
        });
        const { result } = renderHook(() => usePdfStatus('/some/dir', true));

        await waitFor(() => expect(mockedGet).toHaveBeenCalled());
        expect(mockedGet).toHaveBeenCalledWith('/api/status', {
            params: { source_dir: '/some/dir' },
        });
        await waitFor(() => expect(result.current.statusItems).toHaveLength(2));
    });

    it('sourceDir が空文字なら fetch をスキップする', async () => {
        const { result } = renderHook(() => usePdfStatus('', true));

        // refetch を呼んでも空 sourceDir で何も呼ばれない
        await result.current.refetch();
        expect(mockedGet).not.toHaveBeenCalled();
    });

    it('items 不在のレスポンスは空配列にフォールバック', async () => {
        mockedGet.mockResolvedValue({}); // items 欠落
        const { result } = renderHook(() => usePdfStatus('/x', true));

        await waitFor(() => expect(mockedGet).toHaveBeenCalled());
        expect(result.current.statusItems).toEqual([]);
    });

    it('GET が throw しても hook は壊れない（statusItems は初期値）', async () => {
        mockedGet.mockRejectedValue(new Error('boom'));
        const { result } = renderHook(() => usePdfStatus('/x', true));

        await waitFor(() => expect(mockedGet).toHaveBeenCalled());
        expect(result.current.statusItems).toEqual([]);
    });

    it('refetch で手動フェッチできる', async () => {
        mockedGet.mockResolvedValueOnce({ items: [] });
        mockedGet.mockResolvedValueOnce({
            items: [{ name: 'x', type: 'pdf', status: 'completed' as const }],
        });
        const { result } = renderHook(() => usePdfStatus('/x', true));
        await waitFor(() => expect(mockedGet).toHaveBeenCalledTimes(1));

        await act(async () => {
            await result.current.refetch();
        });
        expect(result.current.statusItems).toHaveLength(1);
    });
});
