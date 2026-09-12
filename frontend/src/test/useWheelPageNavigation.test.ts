import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { UI_CONFIG } from '@/constants';
import { useWheelPageNavigation } from '@/hooks/reader/useWheelPageNavigation';

const DOM_DELTA_LINE = 1;

function dispatchWheel(target: HTMLElement, init: WheelEventInit): WheelEvent {
    const event = new WheelEvent('wheel', { bubbles: true, cancelable: true, ...init });
    act(() => target.dispatchEvent(event));
    return event;
}

function setup(enabled = true) {
    const target = document.createElement('div');
    Object.defineProperty(target, 'clientHeight', { value: 800 });
    document.body.append(target);
    const targetRef = { current: target };
    const onNext = vi.fn();
    const onPrev = vi.fn();
    const hook = renderHook(
        ({ isEnabled }) =>
            useWheelPageNavigation({
                targetRef,
                enabled: isEnabled,
                onNext,
                onPrev,
            }),
        { initialProps: { isEnabled: enabled } },
    );
    return { target, onNext, onPrev, ...hook };
}

afterEach(() => {
    vi.useRealTimers();
    document.body.innerHTML = '';
});

describe('useWheelPageNavigation', () => {
    it('下方向と上方向のgestureを、それぞれ次pageと前pageへ変換する', () => {
        vi.useFakeTimers();
        const { target, onNext, onPrev } = setup();

        const down = dispatchWheel(target, { deltaY: UI_CONFIG.READER_WHEEL_THRESHOLD_PX });
        expect(down.defaultPrevented).toBe(true);
        expect(onNext).toHaveBeenCalledTimes(1);

        act(() => vi.advanceTimersByTime(UI_CONFIG.READER_WHEEL_GESTURE_END_MS));
        const up = dispatchWheel(target, { deltaY: -UI_CONFIG.READER_WHEEL_THRESHOLD_PX });
        expect(up.defaultPrevented).toBe(true);
        expect(onPrev).toHaveBeenCalledTimes(1);
    });

    it('小さいdeltaを累積し、閾値到達までpageを移動しない', () => {
        const { target, onNext } = setup();
        const half = UI_CONFIG.READER_WHEEL_THRESHOLD_PX / 2;

        dispatchWheel(target, { deltaY: half });
        expect(onNext).not.toHaveBeenCalled();
        dispatchWheel(target, { deltaY: half });
        expect(onNext).toHaveBeenCalledTimes(1);
    });

    it('同一gestureの慣性eventではpageを追加移動しない', () => {
        vi.useFakeTimers();
        const { target, onNext } = setup();

        dispatchWheel(target, { deltaY: 100 });
        dispatchWheel(target, { deltaY: 80 });
        dispatchWheel(target, { deltaY: 40 });
        expect(onNext).toHaveBeenCalledTimes(1);

        act(() => vi.advanceTimersByTime(UI_CONFIG.READER_WHEEL_GESTURE_END_MS - 1));
        dispatchWheel(target, { deltaY: 30 });
        expect(onNext).toHaveBeenCalledTimes(1);

        act(() => vi.advanceTimersByTime(UI_CONFIG.READER_WHEEL_GESTURE_END_MS));
        dispatchWheel(target, { deltaY: 100 });
        expect(onNext).toHaveBeenCalledTimes(2);
    });

    it('page更新でcallbackが変わっても同一gestureのlockを維持する', () => {
        vi.useFakeTimers();
        const target = document.createElement('div');
        document.body.append(target);
        const targetRef = { current: target };
        const firstNext = vi.fn();
        const secondNext = vi.fn();
        const onPrev = vi.fn();
        const { rerender } = renderHook(
            ({ onNext }) => useWheelPageNavigation({ targetRef, enabled: true, onNext, onPrev }),
            { initialProps: { onNext: firstNext } },
        );

        dispatchWheel(target, { deltaY: 100 });
        expect(firstNext).toHaveBeenCalledTimes(1);

        rerender({ onNext: secondNext });
        dispatchWheel(target, { deltaY: 100 });
        expect(secondNext).not.toHaveBeenCalled();

        act(() => vi.advanceTimersByTime(UI_CONFIG.READER_WHEEL_GESTURE_END_MS));
        dispatchWheel(target, { deltaY: 100 });
        expect(secondNext).toHaveBeenCalledTimes(1);
    });

    it('line単位のdeltaをpixel相当へ正規化する', () => {
        const { target, onNext } = setup();

        dispatchWheel(target, { deltaY: 3, deltaMode: DOM_DELTA_LINE });
        expect(onNext).toHaveBeenCalledTimes(1);
    });

    it('横方向優位と修飾キー付きのwheelは標準操作へ委ねる', () => {
        const { target, onNext, onPrev } = setup();

        const horizontal = dispatchWheel(target, { deltaX: 50, deltaY: 20 });
        const zoom = dispatchWheel(target, { deltaY: 100, ctrlKey: true });
        const shifted = dispatchWheel(target, { deltaY: -100, shiftKey: true });

        expect(horizontal.defaultPrevented).toBe(false);
        expect(zoom.defaultPrevented).toBe(false);
        expect(shifted.defaultPrevented).toBe(false);
        expect(onNext).not.toHaveBeenCalled();
        expect(onPrev).not.toHaveBeenCalled();
    });

    it('無効時はwheel listenerを登録せず、再有効化すると処理する', () => {
        const { target, onNext, rerender } = setup(false);

        const disabled = dispatchWheel(target, { deltaY: 100 });
        expect(disabled.defaultPrevented).toBe(false);
        expect(onNext).not.toHaveBeenCalled();

        rerender({ isEnabled: true });
        const enabled = dispatchWheel(target, { deltaY: 100 });
        expect(enabled.defaultPrevented).toBe(true);
        expect(onNext).toHaveBeenCalledTimes(1);
    });
});
