import { useEffect, useRef, type RefObject } from 'react';
import { UI_CONFIG } from '@/constants';

interface UseWheelPageNavigationProps {
    targetRef: RefObject<HTMLElement | null>;
    enabled: boolean;
    onNext: () => void;
    onPrev: () => void;
}

function normalizeWheelDelta(event: WheelEvent, target: HTMLElement): number {
    if (event.deltaMode === event.DOM_DELTA_LINE) {
        return event.deltaY * UI_CONFIG.READER_WHEEL_LINE_PX;
    }
    if (event.deltaMode === event.DOM_DELTA_PAGE) {
        return event.deltaY * Math.max(target.clientHeight, 1);
    }
    return event.deltaY;
}

/**
 * Reader本文上の縦wheel gestureを、前後1回のpage移動へ変換する。
 * React 19のdelegated wheel listenerはpassiveのため、native listenerを明示的に使う。
 */
export function useWheelPageNavigation({
    targetRef,
    enabled,
    onNext,
    onPrev,
}: UseWheelPageNavigationProps): void {
    const callbacksRef = useRef({ onNext, onPrev });
    useEffect(() => {
        callbacksRef.current = { onNext, onPrev };
    }, [onNext, onPrev]);

    useEffect(() => {
        const target = targetRef.current;
        if (!enabled || !target) return;

        let accumulatedDelta = 0;
        let gestureDirection = 0;
        let gestureHandled = false;
        let gestureEndTimer: ReturnType<typeof setTimeout> | null = null;

        const resetGesture = () => {
            accumulatedDelta = 0;
            gestureDirection = 0;
            gestureHandled = false;
            gestureEndTimer = null;
        };

        const handleWheel = (event: WheelEvent) => {
            if (event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
            if (event.deltaY === 0 || Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return;

            event.preventDefault();

            if (gestureEndTimer !== null) clearTimeout(gestureEndTimer);
            gestureEndTimer = setTimeout(resetGesture, UI_CONFIG.READER_WHEEL_GESTURE_END_MS);

            if (gestureHandled) return;

            const normalizedDelta = normalizeWheelDelta(event, target);
            const nextDirection = Math.sign(normalizedDelta);
            if (gestureDirection !== 0 && gestureDirection !== nextDirection) {
                accumulatedDelta = 0;
            }
            gestureDirection = nextDirection;
            accumulatedDelta += normalizedDelta;

            if (Math.abs(accumulatedDelta) < UI_CONFIG.READER_WHEEL_THRESHOLD_PX) return;

            gestureHandled = true;
            if (accumulatedDelta > 0) callbacksRef.current.onNext();
            else callbacksRef.current.onPrev();
        };

        target.addEventListener('wheel', handleWheel, { passive: false });
        return () => {
            target.removeEventListener('wheel', handleWheel);
            if (gestureEndTimer !== null) clearTimeout(gestureEndTimer);
        };
    }, [enabled, targetRef]);
}
