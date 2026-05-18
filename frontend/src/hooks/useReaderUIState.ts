import { useState, useCallback, useRef } from 'react';

const TOUCH_AUTO_HIDE_MS = 3000;

/**
 * リーダー画面の UI トグル系状態（ヘッダー / スライダー / 検索 / ヘルプ）を集約するフック。
 *
 * `direction` などリーダー本体の本質的状態は集約しない。
 */
export function useReaderUIState() {
    const [showHeader, setShowHeader] = useState(false);
    const [showSlider, setShowSlider] = useState(false);
    const [isSearchOpen, setIsSearchOpen] = useState(false);
    const [isHelpOpen, setIsHelpOpen] = useState(false);

    const headerTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const sliderTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    const openSearch = useCallback(() => setIsSearchOpen(true), []);
    const closeSearch = useCallback(() => setIsSearchOpen(false), []);
    const toggleSearch = useCallback(() => setIsSearchOpen((s) => !s), []);

    const openHelp = useCallback(() => setIsHelpOpen(true), []);
    const closeHelp = useCallback(() => setIsHelpOpen(false), []);

    const showHeaderOff = useCallback(() => setShowHeader(false), []);
    const showSliderOff = useCallback(() => setShowSlider(false), []);

    // スライダードラッグ中はヘッダー・スライダー両方のタイマーを停止して黒帯を維持する
    const pauseSliderTimer = useCallback(() => {
        if (headerTimerRef.current !== null) {
            clearTimeout(headerTimerRef.current);
            headerTimerRef.current = null;
        }
        if (sliderTimerRef.current !== null) {
            clearTimeout(sliderTimerRef.current);
            sliderTimerRef.current = null;
        }
    }, []);

    // ドラッグ終了後にヘッダー・スライダー両方のタイマーを再開する
    const resumeSliderTimer = useCallback(() => {
        if (headerTimerRef.current !== null) clearTimeout(headerTimerRef.current);
        if (sliderTimerRef.current !== null) clearTimeout(sliderTimerRef.current);
        headerTimerRef.current = setTimeout(() => setShowHeader(false), TOUCH_AUTO_HIDE_MS);
        sliderTimerRef.current = setTimeout(() => setShowSlider(false), TOUCH_AUTO_HIDE_MS);
    }, []);

    // 中央ゾーンタップ用: 両方表示中なら非表示に、そうでなければ表示して 3 秒後に自動非表示
    const toggleBothUI = useCallback((currentHeader: boolean, currentSlider: boolean) => {
        if (currentHeader && currentSlider) {
            if (headerTimerRef.current !== null) clearTimeout(headerTimerRef.current);
            if (sliderTimerRef.current !== null) clearTimeout(sliderTimerRef.current);
            setShowHeader(false);
            setShowSlider(false);
        } else {
            if (headerTimerRef.current !== null) clearTimeout(headerTimerRef.current);
            if (sliderTimerRef.current !== null) clearTimeout(sliderTimerRef.current);
            setShowHeader(true);
            setShowSlider(true);
            headerTimerRef.current = setTimeout(() => setShowHeader(false), TOUCH_AUTO_HIDE_MS);
            sliderTimerRef.current = setTimeout(() => setShowSlider(false), TOUCH_AUTO_HIDE_MS);
        }
    }, []);

    return {
        showHeader,
        showHeaderOff,
        showSlider,
        showSliderOff,
        pauseSliderTimer,
        resumeSliderTimer,
        toggleBothUI,
        isSearchOpen,
        openSearch,
        closeSearch,
        toggleSearch,
        isHelpOpen,
        openHelp,
        closeHelp,
    };
}
