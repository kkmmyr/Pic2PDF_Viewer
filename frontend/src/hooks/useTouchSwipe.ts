import { useRef, useCallback } from 'react';

const SWIPE_THRESHOLD_PX = 50;

interface UseTouchSwipeProps {
    onSwipeLeft: () => void;
    onSwipeRight: () => void;
}

/**
 * 左右スワイプを検出してページ送りに使うフック。
 *
 * - |dx| が閾値（50px）以上かつ縦方向より横方向の移動が大きければスワイプと判定
 * - touchend で e.preventDefault() を呼び、後続のクリックイベントを抑止する
 * - 縦スクロール・ピンチ操作には干渉しない
 */
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

            // 縦スクロール or 閾値未満のタップは無視
            if (Math.abs(dy) > Math.abs(dx) || Math.abs(dx) < SWIPE_THRESHOLD_PX) return;

            // 横スワイプ確定: 後続クリックを抑止してページ送り
            e.preventDefault();
            if (dx < 0) onSwipeLeft();
            else onSwipeRight();
        },
        [onSwipeLeft, onSwipeRight],
    );

    return { onTouchStart, onTouchEnd };
}
