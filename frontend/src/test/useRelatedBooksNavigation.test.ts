import { renderHook, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { useRelatedBooksNavigation } from '../hooks/useRelatedBooksNavigation';

describe('useRelatedBooksNavigation', () => {
    const mockRecordView = vi.fn();
    const mockOnSelectPdf = vi.fn();

    const defaultProps = {
        relatedBooks: { series: [{ name: 'vol2.pdf' }], authors: [] },
        onSelectPdf: mockOnSelectPdf,
        recordView: mockRecordView,
        currentPath: '/path/to/book.pdf',
    };

    beforeEach(() => { vi.clearAllMocks(); });

    it('初期状態で isOnRelatedPage は false', () => {
        const { result } = renderHook(() => useRelatedBooksNavigation(defaultProps));
        expect(result.current.isOnRelatedPage).toBe(false);
    });

    it('handleNextAtEnd: 関連書籍あり + onSelectPdf あり → isOnRelatedPage=true', () => {
        const { result } = renderHook(() => useRelatedBooksNavigation(defaultProps));
        act(() => { result.current.handleNextAtEnd(); });
        expect(result.current.isOnRelatedPage).toBe(true);
    });

    it('handleNextAtEnd: series/authors 両方空 → isOnRelatedPage は変わらない', () => {
        const { result } = renderHook(() =>
            useRelatedBooksNavigation({ ...defaultProps, relatedBooks: { series: [], authors: [] } }),
        );
        act(() => { result.current.handleNextAtEnd(); });
        expect(result.current.isOnRelatedPage).toBe(false);
    });

    it('handleNextAtEnd: onSelectPdf=undefined → isOnRelatedPage は変わらない', () => {
        const { result } = renderHook(() =>
            useRelatedBooksNavigation({ ...defaultProps, onSelectPdf: undefined }),
        );
        act(() => { result.current.handleNextAtEnd(); });
        expect(result.current.isOnRelatedPage).toBe(false);
    });

    it('handlePrevIntercept: 関連ページ中 → false に戻して true を返す', () => {
        const { result } = renderHook(() => useRelatedBooksNavigation(defaultProps));
        act(() => { result.current.handleNextAtEnd(); });
        expect(result.current.isOnRelatedPage).toBe(true);

        let intercepted = false;
        act(() => { intercepted = result.current.handlePrevIntercept(); });
        expect(intercepted).toBe(true);
        expect(result.current.isOnRelatedPage).toBe(false);
    });

    it('handlePrevIntercept: 通常ページ中 → false を返し状態も変わらない', () => {
        const { result } = renderHook(() => useRelatedBooksNavigation(defaultProps));
        let intercepted = true;
        act(() => { intercepted = result.current.handlePrevIntercept(); });
        expect(intercepted).toBe(false);
        expect(result.current.isOnRelatedPage).toBe(false);
    });

    it('handleSelectRelated: recordView と onSelectPdf が正しい引数で呼ばれる', () => {
        const { result } = renderHook(() => useRelatedBooksNavigation(defaultProps));
        act(() => { result.current.handleSelectRelated('next.pdf'); });
        expect(mockRecordView).toHaveBeenCalledWith('/path/to/book.pdf', 'next.pdf');
        expect(mockOnSelectPdf).toHaveBeenCalledWith('next.pdf');
    });

    it('handleSelectRelated: onSelectPdf=undefined → 何も起きない', () => {
        const { result } = renderHook(() =>
            useRelatedBooksNavigation({ ...defaultProps, onSelectPdf: undefined }),
        );
        act(() => { result.current.handleSelectRelated('next.pdf'); });
        expect(mockRecordView).not.toHaveBeenCalled();
        expect(mockOnSelectPdf).not.toHaveBeenCalled();
    });
});
