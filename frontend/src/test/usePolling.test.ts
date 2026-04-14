/**
 * usePolling フックのユニットテスト
 *
 * 実行方法:
 *   cd frontend && npx vitest run
 */
import { renderHook, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { usePolling } from '../hooks/usePolling';

describe('usePolling', () => {
    beforeEach(() => { vi.useFakeTimers(); });
    afterEach(() => { vi.useRealTimers(); });

    it('enabled=true のとき即時フェッチする', async () => {
        const fetcher = vi.fn().mockResolvedValue(undefined);
        renderHook(() => usePolling(fetcher, { enabled: true, interval: 1000 }));

        await act(async () => { await Promise.resolve(); });
        expect(fetcher).toHaveBeenCalledTimes(1);
    });

    it('enabled=false のときフェッチしない', () => {
        const fetcher = vi.fn().mockResolvedValue(undefined);
        renderHook(() => usePolling(fetcher, { enabled: false, interval: 1000 }));
        expect(fetcher).not.toHaveBeenCalled();
    });

    it('interval ごとに繰り返しフェッチする', async () => {
        const fetcher = vi.fn().mockResolvedValue(undefined);
        renderHook(() => usePolling(fetcher, { enabled: true, interval: 1000 }));

        await act(async () => { await Promise.resolve(); });
        expect(fetcher).toHaveBeenCalledTimes(1);

        await act(async () => { vi.advanceTimersByTime(1000); await Promise.resolve(); });
        expect(fetcher).toHaveBeenCalledTimes(2);

        await act(async () => { vi.advanceTimersByTime(1000); await Promise.resolve(); });
        expect(fetcher).toHaveBeenCalledTimes(3);
    });

    it('アンマウント時にインターバルをクリアする', async () => {
        const fetcher = vi.fn().mockResolvedValue(undefined);
        const { unmount } = renderHook(() =>
            usePolling(fetcher, { enabled: true, interval: 1000 })
        );

        await act(async () => { await Promise.resolve(); });
        unmount();

        await act(async () => { vi.advanceTimersByTime(3000); });
        // アンマウント後は追加呼び出しなし
        expect(fetcher).toHaveBeenCalledTimes(1);
    });

    it('enabled が false に切り替わるとインターバルを停止する', async () => {
        const fetcher = vi.fn().mockResolvedValue(undefined);
        let enabled = true;
        const { rerender } = renderHook(() =>
            usePolling(fetcher, { enabled, interval: 1000 })
        );

        await act(async () => { await Promise.resolve(); });
        expect(fetcher).toHaveBeenCalledTimes(1);

        enabled = false;
        rerender();

        await act(async () => { vi.advanceTimersByTime(3000); });
        expect(fetcher).toHaveBeenCalledTimes(1);
    });

    it('refetch を呼ぶと手動でフェッチできる', async () => {
        const fetcher = vi.fn().mockResolvedValue(undefined);
        const { result } = renderHook(() =>
            usePolling(fetcher, { enabled: false })
        );

        await act(async () => { await result.current.refetch(); });
        expect(fetcher).toHaveBeenCalledTimes(1);
    });
});
