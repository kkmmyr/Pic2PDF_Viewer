import { useState, useEffect, useCallback } from 'react';

interface UseFullscreenReturn {
    isFullscreen: boolean;
    /** ブラウザのフルスクリーン（document）をトグルする */
    toggleFullscreen: () => Promise<void>;
}

/**
 * ブラウザのフルスクリーン API ラッパー。
 *
 * - Document Fullscreen API を使い、F11 とほぼ同等の体験を実現する。
 * - Esc キーまたはブラウザ UI からの解除もちゃんと検知して `isFullscreen` を更新する。
 */
export function useFullscreen(): UseFullscreenReturn {
    const [isFullscreen, setIsFullscreen] = useState(
        () => typeof document !== 'undefined' && !!document.fullscreenElement
    );

    useEffect(() => {
        const handler = () => setIsFullscreen(!!document.fullscreenElement);
        document.addEventListener('fullscreenchange', handler);
        return () => document.removeEventListener('fullscreenchange', handler);
    }, []);

    const toggleFullscreen = useCallback(async () => {
        try {
            if (document.fullscreenElement) {
                await document.exitFullscreen();
            } else {
                await document.documentElement.requestFullscreen();
            }
        } catch {
            // ユーザー拒否やブラウザ制限の場合は無視（黙ってスキップ）
        }
    }, []);

    return { isFullscreen, toggleFullscreen };
}
