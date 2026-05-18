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

    const showHeaderOn = useCallback(() => setShowHeader(true), []);
    const showHeaderOff = useCallback(() => setShowHeader(false), []);
    const showSliderOn = useCallback(() => setShowSlider(true), []);
    const showSliderOff = useCallback(() => setShowSlider(false), []);

    // タッチ用: 表示して 3 秒後に自動的に非表示にする
    const showHeaderOnTouch = useCallback(() => {
        setShowHeader(true);
        if (headerTimerRef.current !== null) clearTimeout(headerTimerRef.current);
        headerTimerRef.current = setTimeout(() => setShowHeader(false), TOUCH_AUTO_HIDE_MS);
    }, []);

    const showSliderOnTouch = useCallback(() => {
        setShowSlider(true);
        if (sliderTimerRef.current !== null) clearTimeout(sliderTimerRef.current);
        sliderTimerRef.current = setTimeout(() => setShowSlider(false), TOUCH_AUTO_HIDE_MS);
    }, []);

    // スライダードラッグ中はタイマーを停止して黒帯を維持する
    const pauseSliderTimer = useCallback(() => {
        if (sliderTimerRef.current !== null) {
            clearTimeout(sliderTimerRef.current);
            sliderTimerRef.current = null;
        }
    }, []);

    // ドラッグ終了後にタイマーを再開する
    const resumeSliderTimer = useCallback(() => {
        if (sliderTimerRef.current !== null) clearTimeout(sliderTimerRef.current);
        sliderTimerRef.current = setTimeout(() => setShowSlider(false), TOUCH_AUTO_HIDE_MS);
    }, []);

    return {
        showHeader,
        showHeaderOn,
        showHeaderOff,
        showHeaderOnTouch,
        showSlider,
        showSliderOn,
        showSliderOff,
        showSliderOnTouch,
        pauseSliderTimer,
        resumeSliderTimer,
        isSearchOpen,
        openSearch,
        closeSearch,
        toggleSearch,
        isHelpOpen,
        openHelp,
        closeHelp,
    };
}
