import { useRef, useCallback } from 'react';

const SWIPE_THRESHOLD_PX = 50;

interface UseTouchSwipeProps {
    onSwipeLeft: () => void;
    onSwipeRight: () => void;
}

export function useTouchSwipe({ onSwipeLeft, onSwipeRight }: UseTouchSwipeProps) {
    const startXRef = useRef<number | null>(null);
    const startYRef = useRef<number | null>(null);

    const onTouchStart = useCallback((e: React.TouchEvent) => {
        startXRef.current = e.touches[0].clientX;
        startYRef.current = e.touches[0].clientY;
    }, []);

    const onTouchEnd = useCallback(
        (e: React.TouchEvent) => {
            if (startXRef.current === null || startYRef.current === null) return;
            const dx = e.changedTouches[0].clientX - startXRef.current;
            const dy = e.changedTouches[0].clientY - startYRef.current;
            startXRef.current = null;
            startYRef.current = null;

            const absDx = Math.abs(dx);
            const absDy = Math.abs(dy);

            if (absDy > absDx || absDx < SWIPE_THRESHOLD_PX) return;

            e.preventDefault();
            if (dx < 0) onSwipeLeft();
            else onSwipeRight();
        },
        [onSwipeLeft, onSwipeRight],
    );

    // ブラウザがスクロール等でタッチを横取りした際にリセット
    const onTouchCancel = useCallback(() => {
        startXRef.current = null;
        startYRef.current = null;
    }, []);

    return { onTouchStart, onTouchEnd, onTouchCancel };
}
