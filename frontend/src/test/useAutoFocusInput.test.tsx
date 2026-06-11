import { renderHook, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { useRef } from 'react';
import { useAutoFocusInput } from '@/hooks/useAutoFocusInput';

describe('useAutoFocusInput', () => {
    let input: HTMLInputElement;

    beforeEach(() => {
        vi.useFakeTimers();
        input = document.createElement('input');
        document.body.appendChild(input);
    });

    afterEach(() => {
        vi.useRealTimers();
        input.remove();
    });

    const renderWithRef = (
        shouldFocus: boolean,
        options: { delay?: number; select?: boolean } = {},
    ) =>
        renderHook(
            ({ flag }: { flag: boolean }) => {
                const ref = useRef<HTMLInputElement | null>(input);
                useAutoFocusInput(ref, flag, options);
                return ref;
            },
            { initialProps: { flag: shouldFocus } },
        );

    it('shouldFocus=true で setTimeout 後に focus() が呼ばれる', () => {
        const focusSpy = vi.spyOn(input, 'focus');
        renderWithRef(true);

        act(() => {
            vi.advanceTimersByTime(0);
        });
        expect(focusSpy).toHaveBeenCalledTimes(1);
    });

    it('shouldFocus=false なら focus は呼ばれない', () => {
        const focusSpy = vi.spyOn(input, 'focus');
        renderWithRef(false);

        act(() => vi.advanceTimersByTime(100));
        expect(focusSpy).not.toHaveBeenCalled();
    });

    it('select=true で focus + select の両方が呼ばれる', () => {
        const focusSpy = vi.spyOn(input, 'focus');
        const selectSpy = vi.spyOn(input, 'select');
        renderWithRef(true, { select: true });

        act(() => vi.advanceTimersByTime(0));
        expect(focusSpy).toHaveBeenCalled();
        expect(selectSpy).toHaveBeenCalled();
    });

    it('delay を超えると focus が走る、超えないと走らない', () => {
        const focusSpy = vi.spyOn(input, 'focus');
        renderWithRef(true, { delay: 100 });

        act(() => vi.advanceTimersByTime(50));
        expect(focusSpy).not.toHaveBeenCalled();

        act(() => vi.advanceTimersByTime(50));
        expect(focusSpy).toHaveBeenCalled();
    });

    it('shouldFocus=true → false 切替時に setTimeout がクリアされ focus は呼ばれない', () => {
        const focusSpy = vi.spyOn(input, 'focus');
        const { rerender } = renderWithRef(true, { delay: 100 });

        // 50ms 経過 → タイマー進行中、まだ focus されてない
        act(() => vi.advanceTimersByTime(50));
        expect(focusSpy).not.toHaveBeenCalled();

        // shouldFocus=false に切り替え → effect cleanup で clearTimeout
        rerender({ flag: false });

        // 残り 50ms 進めても focus は呼ばれない
        act(() => vi.advanceTimersByTime(100));
        expect(focusSpy).not.toHaveBeenCalled();
    });

    it('ref.current が null なら focus は呼ばれない（クラッシュもしない）', () => {
        const { result: _result } = renderHook(() => {
            const ref = useRef<HTMLInputElement | null>(null);
            useAutoFocusInput(ref, true);
            return ref;
        });

        expect(() => act(() => vi.advanceTimersByTime(0))).not.toThrow();
    });
});
