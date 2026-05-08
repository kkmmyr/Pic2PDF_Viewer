/**
 * useReaderNavigation フックのユニットテスト
 */
import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
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

describe('useReaderNavigation — spread mode LTR', () => {
    const spread = { numPages: 10, isSpread: true, direction: 'ltr' as const, isActive: false };

    it('1ページ目から Next で 3 へ（LTR の見開きは奇数ページ単位）', () => {
        const { result } = renderHook(() => useReaderNavigation(spread));
        act(() => result.current.handleNext());
        expect(result.current.pageNumber).toBe(3);
    });

    it('3ページ目から Prev で 1 へ', () => {
        const { result } = renderHook(() => useReaderNavigation(spread));
        act(() => result.current.setPageNumber(3));
        act(() => result.current.handlePrev());
        expect(result.current.pageNumber).toBe(1);
    });

    it('5ページ目から Next で 7 へ（2 ページ進む）', () => {
        const { result } = renderHook(() => useReaderNavigation(spread));
        act(() => result.current.setPageNumber(5));
        act(() => result.current.handleNext());
        expect(result.current.pageNumber).toBe(7);
    });
});

describe('useReaderNavigation — onNextAtEnd', () => {
    it('単独ページモードで最終ページから Next 時に onNextAtEnd が呼ばれる', () => {
        const onNextAtEnd = vi.fn();
        const { result } = renderHook(() =>
            useReaderNavigation({ ...defaults, numPages: 3, onNextAtEnd }),
        );
        act(() => result.current.setPageNumber(3));
        act(() => result.current.handleNext());
        expect(onNextAtEnd).toHaveBeenCalledTimes(1);
        expect(result.current.pageNumber).toBe(3);
    });

    it('途中ページから Next では onNextAtEnd は呼ばれない', () => {
        const onNextAtEnd = vi.fn();
        const { result } = renderHook(() =>
            useReaderNavigation({ ...defaults, numPages: 5, onNextAtEnd }),
        );
        act(() => result.current.handleNext());
        expect(onNextAtEnd).not.toHaveBeenCalled();
        expect(result.current.pageNumber).toBe(2);
    });

    it('見開き RTL の最終スプレッドから Next で onNextAtEnd が呼ばれる', () => {
        const onNextAtEnd = vi.fn();
        const props = {
            numPages: 5,
            isSpread: true,
            direction: 'rtl' as const,
            isActive: false,
            onNextAtEnd,
        };
        const { result } = renderHook(() => useReaderNavigation(props));
        act(() => result.current.setPageNumber(4)); // 表示は 5|4
        act(() => result.current.handleNext());
        expect(onNextAtEnd).toHaveBeenCalledTimes(1);
    });

    it('見開き LTR の最終スプレッドから Next で onNextAtEnd が呼ばれる', () => {
        const onNextAtEnd = vi.fn();
        const props = {
            numPages: 4,
            isSpread: true,
            direction: 'ltr' as const,
            isActive: false,
            onNextAtEnd,
        };
        const { result } = renderHook(() => useReaderNavigation(props));
        // pageNumber+2 > numPages かつ pageNumber+1 > numPages を満たす最終位置に置く
        act(() => result.current.setPageNumber(4));
        act(() => result.current.handleNext());
        expect(onNextAtEnd).toHaveBeenCalledTimes(1);
    });
});

describe('useReaderNavigation — onPrevIntercept', () => {
    it('intercept が true を返すとページ戻し処理がスキップされる', () => {
        const onPrevIntercept = vi.fn(() => true);
        const { result } = renderHook(() => useReaderNavigation({ ...defaults, onPrevIntercept }));
        act(() => result.current.setPageNumber(5));
        act(() => result.current.handlePrev());
        expect(onPrevIntercept).toHaveBeenCalledTimes(1);
        expect(result.current.pageNumber).toBe(5); // 変わらない
    });

    it('intercept が false を返すと通常のページ戻しが実行される', () => {
        const onPrevIntercept = vi.fn(() => false);
        const { result } = renderHook(() => useReaderNavigation({ ...defaults, onPrevIntercept }));
        act(() => result.current.setPageNumber(5));
        act(() => result.current.handlePrev());
        expect(onPrevIntercept).toHaveBeenCalledTimes(1);
        expect(result.current.pageNumber).toBe(4);
    });
});
