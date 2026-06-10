import { renderHook, act } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { useReaderUIState } from '../hooks/reader/useReaderUIState';

describe('useReaderUIState', () => {
    it('初期状態は全部 false', () => {
        const { result } = renderHook(() => useReaderUIState());
        expect(result.current.showHeader).toBe(false);
        expect(result.current.showSlider).toBe(false);
        expect(result.current.isSearchOpen).toBe(false);
        expect(result.current.isHelpOpen).toBe(false);
    });

    it('showHeaderOff でヘッダーを非表示にできる', () => {
        const { result } = renderHook(() => useReaderUIState());
        act(() => result.current.toggleBothUI(false, false));
        expect(result.current.showHeader).toBe(true);
        act(() => result.current.showHeaderOff());
        expect(result.current.showHeader).toBe(false);
    });

    it('showSliderOff でスライダーを非表示にできる', () => {
        const { result } = renderHook(() => useReaderUIState());
        act(() => result.current.toggleBothUI(false, false));
        expect(result.current.showSlider).toBe(true);
        act(() => result.current.showSliderOff());
        expect(result.current.showSlider).toBe(false);
    });

    it('toggleBothUI: 非表示→表示', () => {
        const { result } = renderHook(() => useReaderUIState());
        act(() => result.current.toggleBothUI(false, false));
        expect(result.current.showHeader).toBe(true);
        expect(result.current.showSlider).toBe(true);
    });

    it('toggleBothUI: 両方表示中→非表示', () => {
        const { result } = renderHook(() => useReaderUIState());
        act(() => result.current.toggleBothUI(false, false));
        act(() => result.current.toggleBothUI(true, true));
        expect(result.current.showHeader).toBe(false);
        expect(result.current.showSlider).toBe(false);
    });

    it('openSearch / closeSearch', () => {
        const { result } = renderHook(() => useReaderUIState());
        act(() => result.current.openSearch());
        expect(result.current.isSearchOpen).toBe(true);
        act(() => result.current.closeSearch());
        expect(result.current.isSearchOpen).toBe(false);
    });

    it('toggleSearch で on/off', () => {
        const { result } = renderHook(() => useReaderUIState());
        act(() => result.current.toggleSearch());
        expect(result.current.isSearchOpen).toBe(true);
        act(() => result.current.toggleSearch());
        expect(result.current.isSearchOpen).toBe(false);
    });

    it('openHelp / closeHelp', () => {
        const { result } = renderHook(() => useReaderUIState());
        act(() => result.current.openHelp());
        expect(result.current.isHelpOpen).toBe(true);
        act(() => result.current.closeHelp());
        expect(result.current.isHelpOpen).toBe(false);
    });

    it('Header / Slider / Search / Help は互いに独立', () => {
        const { result } = renderHook(() => useReaderUIState());
        act(() => result.current.openSearch());
        act(() => result.current.openHelp());
        expect(result.current.isSearchOpen).toBe(true);
        expect(result.current.isHelpOpen).toBe(true);
        expect(result.current.showHeader).toBe(false);
    });
});
