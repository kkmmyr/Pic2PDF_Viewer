import { renderHook, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { useToast } from '../hooks/useToast';

describe('useToast', () => {
    beforeEach(() => {
        vi.useFakeTimers();
    });
    afterEach(() => {
        vi.useRealTimers();
    });

    it('初期状態はトーストなし', () => {
        const { result } = renderHook(() => useToast());
        expect(result.current.toasts).toHaveLength(0);
    });

    it('showToast でトーストが追加される', () => {
        const { result } = renderHook(() => useToast());
        act(() => {
            result.current.showToast('保存しました', 'success');
        });
        expect(result.current.toasts).toHaveLength(1);
        expect(result.current.toasts[0].message).toBe('保存しました');
        expect(result.current.toasts[0].type).toBe('success');
    });

    it('type を省略すると "info" になる', () => {
        const { result } = renderHook(() => useToast());
        act(() => {
            result.current.showToast('情報');
        });
        expect(result.current.toasts[0].type).toBe('info');
    });

    it('複数のトーストを同時に保持できる', () => {
        const { result } = renderHook(() => useToast());
        act(() => {
            result.current.showToast('A', 'success');
            result.current.showToast('B', 'error');
        });
        expect(result.current.toasts).toHaveLength(2);
        expect(result.current.toasts.map((t) => t.message)).toEqual(['A', 'B']);
    });

    it('各トーストには一意な id が振られる', () => {
        const { result } = renderHook(() => useToast());
        act(() => {
            result.current.showToast('A');
            result.current.showToast('B');
        });
        const ids = result.current.toasts.map((t) => t.id);
        expect(new Set(ids).size).toBe(2);
    });

    it('dismissToast で指定した id のトーストだけ削除される', () => {
        const { result } = renderHook(() => useToast());
        act(() => {
            result.current.showToast('A');
            result.current.showToast('B');
        });
        const idA = result.current.toasts[0].id;
        act(() => {
            result.current.dismissToast(idA);
        });
        expect(result.current.toasts).toHaveLength(1);
        expect(result.current.toasts[0].message).toBe('B');
    });

    it('4000ms 経過後にトーストが自動削除される', () => {
        const { result } = renderHook(() => useToast());
        act(() => {
            result.current.showToast('自動消去');
        });
        expect(result.current.toasts).toHaveLength(1);
        act(() => {
            vi.advanceTimersByTime(4000);
        });
        expect(result.current.toasts).toHaveLength(0);
    });

    it('4000ms 未満では自動削除されない', () => {
        const { result } = renderHook(() => useToast());
        act(() => {
            result.current.showToast('残る');
        });
        act(() => {
            vi.advanceTimersByTime(3999);
        });
        expect(result.current.toasts).toHaveLength(1);
    });

    it('手動 dismiss 後は自動削除タイマーが発火しても影響なし', () => {
        const { result } = renderHook(() => useToast());
        act(() => {
            result.current.showToast('X');
        });
        const id = result.current.toasts[0].id;
        act(() => {
            result.current.dismissToast(id);
        });
        expect(result.current.toasts).toHaveLength(0);
        act(() => {
            vi.advanceTimersByTime(4000);
        });
        expect(result.current.toasts).toHaveLength(0);
    });
});
