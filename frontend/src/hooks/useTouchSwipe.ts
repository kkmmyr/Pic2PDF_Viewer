import { useRef, useCallback } from 'react';

const SWIPE_THRESHOLD_PX = 50;
const TAP_THRESHOLD_PX = 10;

interface UseTouchSwipeProps {
    onSwipeLeft: () => void;
    onSwipeRight: () => void;
    /** 指がほぼ動かずに離れた（タップ）場合に呼ばれる */
    onTap?: () => void;
}

/**
 * 左右スワイプ・タップを検出するフック。
 *
 * - |dx| >= 50px かつ縦より横の移動が大きければスワイプ → ページ送り
 * - |dx| < 10px かつ |dy| < 10px ならタップ → onTap()
 * - それ以外（縦スクロール・中間的なジェスチャー）は無視
 */
export function useTouchSwipe({ onSwipeLeft, onSwipeRight, onTap }: UseTouchSwipeProps) {
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

            // タップ判定: 指がほぼ動いていない
            if (absDx < TAP_THRESHOLD_PX && absDy < TAP_THRESHOLD_PX) {
                onTap?.();
                return;
            }

            // 縦スクロール or 横移動が閾値未満 → 無視
            if (absDy > absDx || absDx < SWIPE_THRESHOLD_PX) return;

            // 横スワイプ確定: 後続クリックを抑止してページ送り
            e.preventDefault();
            if (dx < 0) onSwipeLeft();
            else onSwipeRight();
        },
        [onSwipeLeft, onSwipeRight, onTap],
    );

    return { onTouchStart, onTouchEnd };
}
