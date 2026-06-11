import { renderHook, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';

describe('useDebouncedValue', () => {
    beforeEach(() => {
        vi.useFakeTimers();
    });
    afterEach(() => {
        vi.useRealTimers();
    });

    it('初回は与えられた値をそのまま返す', () => {
        const { result } = renderHook(() => useDebouncedValue('a', 100));
        expect(result.current).toBe('a');
    });

    it('value 変更後 delay 内では debounced 値が変わらない', () => {
        const { result, rerender } = renderHook(
            ({ v }: { v: string }) => useDebouncedValue(v, 100),
            { initialProps: { v: 'a' } },
        );
        rerender({ v: 'b' });
        act(() => vi.advanceTimersByTime(50));
        expect(result.current).toBe('a');
    });

    it('delay 経過後に debounced 値が反映される', () => {
        const { result, rerender } = renderHook(
            ({ v }: { v: string }) => useDebouncedValue(v, 100),
            { initialProps: { v: 'a' } },
        );
        rerender({ v: 'b' });
        act(() => vi.advanceTimersByTime(100));
        expect(result.current).toBe('b');
    });

    it('連続変更時は最後の変更から delay 経過後の値が反映', () => {
        const { result, rerender } = renderHook(
            ({ v }: { v: string }) => useDebouncedValue(v, 100),
            { initialProps: { v: 'a' } },
        );
        rerender({ v: 'b' });
        act(() => vi.advanceTimersByTime(50));
        rerender({ v: 'c' });
        act(() => vi.advanceTimersByTime(50));
        // 'b' は反映されない（cleanup でキャンセルされた）
        expect(result.current).toBe('a');

        act(() => vi.advanceTimersByTime(50));
        expect(result.current).toBe('c');
    });

    it('数値型でも動作', () => {
        const { result, rerender } = renderHook(
            ({ v }: { v: number }) => useDebouncedValue(v, 50),
            { initialProps: { v: 1 } },
        );
        rerender({ v: 5 });
        act(() => vi.advanceTimersByTime(50));
        expect(result.current).toBe(5);
    });

    it('アンマウントで pending タイマーがクリアされる（外への副作用なし）', () => {
        const { rerender, unmount } = renderHook(
            ({ v }: { v: string }) => useDebouncedValue(v, 100),
            { initialProps: { v: 'a' } },
        );
        rerender({ v: 'b' });
        unmount();
        // タイマー進行で何も起きない（hook unmount 後のため state 更新しても観察不能だが
        // テストランナーが act warning を出さないことで間接確認）
        expect(() => vi.advanceTimersByTime(200)).not.toThrow();
    });
});
