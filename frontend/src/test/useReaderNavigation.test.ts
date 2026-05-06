/**
 * useReaderNavigation フックのユニットテスト
 */
import { renderHook, act } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { useReaderNavigation } from '../hooks/useReaderNavigation';

const defaults = { numPages: 10, isSpread: false, direction: 'ltr' as const, isActive: false };

describe('useReaderNavigation — single page mode', () => {
    it('初期ページは 1', () => {
        const { result } = renderHook(() => useReaderNavigation(defaults));
        expect(result.current.pageNumber).toBe(1);
    });

    it('handleNext でページが増える', () => {
        const { result } = renderHook(() => useReaderNavigation(defaults));
        act(() => result.current.handleNext());
        expect(result.current.pageNumber).toBe(2);
    });

    it('最終ページで handleNext しても超えない', () => {
        const { result } = renderHook(() => useReaderNavigation({ ...defaults, numPages: 1 }));
        act(() => result.current.handleNext());
        expect(result.current.pageNumber).toBe(1);
    });

    it('handlePrev でページが減る', () => {
        const { result } = renderHook(() => useReaderNavigation(defaults));
        act(() => result.current.setPageNumber(5));
        act(() => result.current.handlePrev());
        expect(result.current.pageNumber).toBe(4);
    });

    it('1ページ目で handlePrev しても 0 にならない', () => {
        const { result } = renderHook(() => useReaderNavigation(defaults));
        act(() => result.current.handlePrev());
        expect(result.current.pageNumber).toBe(1);
    });

    it('resetPage で 1 に戻る', () => {
        const { result } = renderHook(() => useReaderNavigation(defaults));
        act(() => result.current.setPageNumber(7));
        act(() => result.current.resetPage());
        expect(result.current.pageNumber).toBe(1);
    });
});

describe('useReaderNavigation — spread mode RTL', () => {
    const spread = { numPages: 10, isSpread: true, direction: 'rtl' as const, isActive: false };

    it('1ページ目から Next で 2 へ', () => {
        const { result } = renderHook(() => useReaderNavigation(spread));
        act(() => result.current.handleNext());
        expect(result.current.pageNumber).toBe(2);
    });

    it('2ページ目から Next で 4 へ (2ページ進む)', () => {
        const { result } = renderHook(() => useReaderNavigation(spread));
        act(() => result.current.setPageNumber(2));
        act(() => result.current.handleNext());
        expect(result.current.pageNumber).toBe(4);
    });

    it('2ページ目から Prev で 1 へ', () => {
        const { result } = renderHook(() => useReaderNavigation(spread));
        act(() => result.current.setPageNumber(2));
        act(() => result.current.handlePrev());
        expect(result.current.pageNumber).toBe(1);
    });
});
