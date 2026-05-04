import { useState, useCallback } from 'react';

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

    const openSearch = useCallback(() => setIsSearchOpen(true), []);
    const closeSearch = useCallback(() => setIsSearchOpen(false), []);
    const toggleSearch = useCallback(() => setIsSearchOpen(s => !s), []);

    const openHelp = useCallback(() => setIsHelpOpen(true), []);
    const closeHelp = useCallback(() => setIsHelpOpen(false), []);

    const showHeaderOn = useCallback(() => setShowHeader(true), []);
    const showHeaderOff = useCallback(() => setShowHeader(false), []);
    const showSliderOn = useCallback(() => setShowSlider(true), []);
    const showSliderOff = useCallback(() => setShowSlider(false), []);

    return {
        showHeader, showHeaderOn, showHeaderOff,
        showSlider, showSliderOn, showSliderOff,
        isSearchOpen, openSearch, closeSearch, toggleSearch,
        isHelpOpen, openHelp, closeHelp,
    };
}
