import { useState, useEffect, useCallback } from 'react';
import { STORAGE_KEYS } from '@/constants';

const STORAGE_KEY = STORAGE_KEYS.DARK_MODE;

/** localStorage + html クラスを同期する純粋関数（副作用あり） */
function applyDark(isDark: boolean) {
    const root = document.documentElement;
    if (isDark) {
        root.classList.add('dark');
    } else {
        root.classList.remove('dark');
    }
    localStorage.setItem(STORAGE_KEY, String(isDark));
}

function readInitialDark(): boolean {
    try {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored !== null) return stored === 'true';
        return window.matchMedia('(prefers-color-scheme: dark)').matches;
    } catch {
        return false;
    }
}

/**
 * ダークモード管理フック。
 * - index.html のインラインスクリプトと連携してフラッシュなしで初期化
 * - useState 初期化時に即座に classList を適用（useEffect 待ちのラグを排除）
 * - localStorage に設定を永続化
 */
export function useDarkMode() {
    const [isDark, setIsDark] = useState<boolean>(() => {
        const initial = readInitialDark();
        // useState 初期化フェーズで即適用（SSR非対応だが本アプリはCSRのみ）
        applyDark(initial);
        return initial;
    });

    // isDark が変わるたびに html クラスと localStorage を同期
    useEffect(() => {
        applyDark(isDark);
    }, [isDark]);

    const toggle = useCallback(() => setIsDark((prev) => !prev), []);

    return { isDark, toggle };
}
