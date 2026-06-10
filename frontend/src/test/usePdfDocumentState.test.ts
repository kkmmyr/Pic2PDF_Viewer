import { renderHook, act } from '@testing-library/react';
import { vi, describe, it, expect } from 'vitest';

// react-pdf は pdfjs を import するだけで DOMMatrix を要求する → mock で回避
vi.mock('react-pdf', () => ({
    pdfjs: { GlobalWorkerOptions: { workerSrc: '' } },
    Page: () => null,
    Document: () => null,
}));

import { usePdfDocumentState } from '../hooks/reader/usePdfDocumentState';

describe('usePdfDocumentState', () => {
    it('初期 numPages=0 / pdfVersion=0', () => {
        const { result } = renderHook(() => usePdfDocumentState());
        expect(result.current.numPages).toBe(0);
        expect(result.current.pdfVersion).toBe(0);
    });

    it('setNumPages で numPages を更新', () => {
        const { result } = renderHook(() => usePdfDocumentState());
        act(() => result.current.setNumPages(42));
        expect(result.current.numPages).toBe(42);
    });

    it('resetNumPages で numPages=0 に戻る', () => {
        const { result } = renderHook(() => usePdfDocumentState());
        act(() => result.current.setNumPages(10));
        act(() => result.current.resetNumPages());
        expect(result.current.numPages).toBe(0);
    });

    it('bumpPdfVersion で pdfVersion がインクリメント', () => {
        const { result } = renderHook(() => usePdfDocumentState());
        act(() => result.current.bumpPdfVersion());
        expect(result.current.pdfVersion).toBe(1);
        act(() => result.current.bumpPdfVersion());
        expect(result.current.pdfVersion).toBe(2);
    });

    it('handleDocumentLoadSuccess で numPages を pdf.numPages にセット + onLoaded を呼ぶ', () => {
        const { result } = renderHook(() => usePdfDocumentState());
        const onLoaded = vi.fn();
        const fakePdf = { numPages: 7 } as never;

        act(() => result.current.handleDocumentLoadSuccess(fakePdf, onLoaded));

        expect(result.current.numPages).toBe(7);
        expect(onLoaded).toHaveBeenCalledWith(fakePdf);
    });

    it('handleDocumentLoadSuccess: onLoaded 省略でも問題なし', () => {
        const { result } = renderHook(() => usePdfDocumentState());
        const fakePdf = { numPages: 3 } as never;

        expect(() => {
            act(() => result.current.handleDocumentLoadSuccess(fakePdf));
        }).not.toThrow();
        expect(result.current.numPages).toBe(3);
    });
});
