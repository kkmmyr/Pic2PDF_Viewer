import { act, renderHook } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';

const readerStateMocks = vi.hoisted(() => ({
    bookImages: {
        imageUrls: null as string[] | null,
        numPages: 0,
        isImageMode: false,
    },
    setNumPages: vi.fn(),
    resetNumPages: vi.fn(),
    setPageNumber: vi.fn(),
    documentNumPages: 0,
    resetPage: vi.fn(),
    resetEditMode: vi.fn(),
    resetAutoSpread: vi.fn(),
    closeSearch: vi.fn(),
    closeSearchState: vi.fn(),
    setIsOnRelatedPage: vi.fn(),
}));

// 複数の API フェッチ hook をモックしてスモークテストを実現する
vi.mock('../hooks/useWindowSize', () => ({
    useWindowSize: () => ({ height: 900 }),
}));
vi.mock('../hooks/reader/useBookImages', () => ({
    useBookImages: () => readerStateMocks.bookImages,
}));
vi.mock('../hooks/reader/useImagePreloader', () => ({
    useImagePreloader: vi.fn(),
}));
vi.mock('../hooks/reader/useReaderNavigation', () => ({
    useReaderNavigation: () => ({
        pageNumber: 1,
        setPageNumber: readerStateMocks.setPageNumber,
        handleNext: vi.fn(),
        handlePrev: vi.fn(),
        resetPage: readerStateMocks.resetPage,
    }),
}));
vi.mock('../hooks/reader/useSpreadMode', () => ({
    useSpreadMode: () => ({
        spreadMode: 'auto' as const,
        isSpread: true,
        cycleSpreadMode: vi.fn(),
        handlePageSize: vi.fn(),
        resetAutoSpread: readerStateMocks.resetAutoSpread,
    }),
}));
vi.mock('../hooks/reader/useEditMode', () => ({
    useEditMode: () => ({
        isEditMode: false,
        selectedPages: new Set<number>(),
        toggleEditMode: vi.fn(),
        togglePageSelection: vi.fn(),
        selectRange: vi.fn(),
        resetEditMode: readerStateMocks.resetEditMode,
        requestDeletePages: vi.fn(),
        confirmDeletePages: vi.fn(),
        cancelDeletePages: vi.fn(),
        pendingDeleteCount: 0,
        applyReorder: vi.fn(),
    }),
}));
vi.mock('../hooks/reader/useFullscreen', () => ({
    useFullscreen: () => ({ isFullscreen: false, toggleFullscreen: vi.fn() }),
}));
vi.mock('../hooks/library/useBookMeta', () => ({
    useBookMeta: () => ({
        meta: {},
        getSeries: vi.fn(),
        recordView: vi.fn(),
        getReadState: vi.fn(),
        setReadState: vi.fn(),
    }),
}));

vi.mock('../hooks/reader/useNextSeriesVolume', () => ({
    useNextSeriesVolume: () => null,
    usePrevSeriesVolume: () => null,
}));
vi.mock('../hooks/reader/useRelatedBooks', () => ({
    useRelatedBooks: () => ({ series: [], authors: [] }),
}));
vi.mock('../hooks/reader/usePdfSearch', () => ({
    usePdfSearch: () => ({
        searchText: '',
        setSearchText: vi.fn(),
        matchCount: 0,
        currentMatch: 0,
        handleCloseSearch: readerStateMocks.closeSearchState,
        handlePrevMatch: vi.fn(),
        handleNextMatch: vi.fn(),
        customTextRenderer: undefined,
        onDocumentLoaded: vi.fn(),
    }),
}));
vi.mock('../hooks/reader/useReaderUIState', () => ({
    useReaderUIState: () => ({
        showHeader: false,
        showHeaderOn: vi.fn(),
        showHeaderOff: vi.fn(),
        showSlider: false,
        showSliderOn: vi.fn(),
        showSliderOff: vi.fn(),
        isSearchOpen: false,
        openSearch: vi.fn(),
        closeSearch: readerStateMocks.closeSearch,
        toggleSearch: vi.fn(),
        isHelpOpen: false,
        openHelp: vi.fn(),
        closeHelp: vi.fn(),
    }),
}));
vi.mock('../hooks/reader/usePdfDocumentState', () => ({
    usePdfDocumentState: () => ({
        numPages: readerStateMocks.documentNumPages,
        setNumPages: readerStateMocks.setNumPages,
        resetNumPages: readerStateMocks.resetNumPages,
        pdfVersion: 0,
        bumpPdfVersion: vi.fn(),
        handleDocumentLoadSuccess: vi.fn(),
    }),
}));
vi.mock('../hooks/reader/useRelatedBooksNavigation', () => ({
    useRelatedBooksNavigation: () => ({
        isOnRelatedPage: false,
        setIsOnRelatedPage: readerStateMocks.setIsOnRelatedPage,
        handleNextAtEnd: vi.fn(),
        handlePrevIntercept: vi.fn(),
        handleSelectRelated: vi.fn(),
    }),
}));
vi.mock('../hooks/reader/useReadProgressTracker', () => ({ useReadProgressTracker: vi.fn() }));
vi.mock('../hooks/reader/useVolumeNavigation', () => ({
    useVolumeNavigation: () => ({
        handleNavigateNextVolume: vi.fn(),
        handleNavigatePrevVolume: vi.fn(),
    }),
}));
vi.mock('../hooks/reader/useReaderInput', () => ({ useReaderInput: vi.fn() }));
vi.mock('../config/api', () => ({
    buildStaticUrl: (p: string) => p,
    STATIC_PATHS: { PDF: () => '/test.pdf' },
}));

import { useReaderState } from '@/hooks/reader/useReaderState';

const defaultProps = {
    selectedPdf: 'test.pdf',
    currentPath: '',
    currentSource: 'doujin' as const,
    onPdfUpdated: vi.fn(),
    onClose: vi.fn(),
};

describe('useReaderState', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        readerStateMocks.bookImages.imageUrls = null;
        readerStateMocks.bookImages.numPages = 0;
        readerStateMocks.bookImages.isImageMode = false;
        readerStateMocks.documentNumPages = 0;
    });

    it('初期状態: direction="rtl", numPages=0, isImageMode=false', () => {
        const { result } = renderHook(() => useReaderState(defaultProps));
        expect(result.current.direction).toBe('rtl');
        expect(result.current.numPages).toBe(0);
        expect(result.current.isImageMode).toBe(false);
    });

    it('初期状態: isEditMode=false, isSearchOpen=false', () => {
        const { result } = renderHook(() => useReaderState(defaultProps));
        expect(result.current.isEditMode).toBe(false);
        expect(result.current.isSearchOpen).toBe(false);
    });

    it('contentTopOffset: isSearchOpen=false のとき空文字', () => {
        const { result } = renderHook(() => useReaderState(defaultProps));
        expect(result.current.contentTopOffset).toBe('');
    });

    it('pdfUrl を返す', () => {
        const { result } = renderHook(() => useReaderState(defaultProps));
        expect(typeof result.current.pdfUrl).toBe('string');
    });

    it('キャッシュ済み画像書籍の再オープンではリセット後にページ数を同期する', () => {
        readerStateMocks.bookImages.imageUrls = ['/page-1.webp', '/page-2.webp'];
        readerStateMocks.bookImages.numPages = 2;
        readerStateMocks.bookImages.isImageMode = true;

        renderHook(() => useReaderState(defaultProps));

        expect(readerStateMocks.resetNumPages).toHaveBeenCalled();
        expect(readerStateMocks.setNumPages).toHaveBeenLastCalledWith(2);
        const resetOrder = readerStateMocks.resetNumPages.mock.invocationCallOrder.at(-1);
        const syncOrder = readerStateMocks.setNumPages.mock.invocationCallOrder.at(-1);
        expect(resetOrder).toBeDefined();
        expect(syncOrder).toBeDefined();
        expect(syncOrder!).toBeGreaterThan(resetOrder!);
    });

    it('URLの初期ページをページ数確定後に一度だけ範囲内へ適用する', () => {
        readerStateMocks.documentNumPages = 5;

        const { rerender } = renderHook(() => useReaderState({ ...defaultProps, initialPage: 8 }));

        expect(readerStateMocks.setPageNumber).toHaveBeenCalledTimes(1);
        expect(readerStateMocks.setPageNumber).toHaveBeenCalledWith(5);

        rerender();
        expect(readerStateMocks.setPageNumber).toHaveBeenCalledTimes(1);
    });
    it('書籍切替では編集・文書・見開き・検索・ページ・関連表示の順にリセットする', () => {
        readerStateMocks.bookImages.isImageMode = true;
        readerStateMocks.bookImages.numPages = 6;
        const { rerender } = renderHook(
            ({ name }) => useReaderState({ ...defaultProps, selectedPdf: name }),
            {
                initialProps: { name: 'first.pdf' },
            },
        );
        vi.clearAllMocks();
        rerender({ name: 'second.pdf' });
        const calls = [
            readerStateMocks.resetEditMode,
            readerStateMocks.resetNumPages,
            readerStateMocks.resetAutoSpread,
            readerStateMocks.closeSearch,
            readerStateMocks.closeSearchState,
            readerStateMocks.resetPage,
            readerStateMocks.setIsOnRelatedPage,
            readerStateMocks.setNumPages,
        ];
        const order = calls.map((fn) => fn.mock.invocationCallOrder[0]);
        expect(order.every((n) => n !== undefined)).toBe(true);
        expect(order).toEqual([...order].sort((a, b) => a - b));
    });

    it('ページ数待ち・初期ページ変更・別書籍の初期ページを従来の順に適用する', () => {
        const { rerender } = renderHook(
            ({ name, initialPage }) =>
                useReaderState({ ...defaultProps, selectedPdf: name, initialPage }),
            {
                initialProps: { name: 'first.pdf', initialPage: 4 },
            },
        );
        expect(readerStateMocks.setPageNumber).not.toHaveBeenCalled();
        readerStateMocks.documentNumPages = 8;
        rerender({ name: 'first.pdf', initialPage: 4 });
        expect(readerStateMocks.setPageNumber).toHaveBeenLastCalledWith(4);
        rerender({ name: 'first.pdf', initialPage: 7 });
        expect(readerStateMocks.setPageNumber).toHaveBeenLastCalledWith(7);
        rerender({ name: 'second.pdf', initialPage: 4 });
        expect(readerStateMocks.setPageNumber).toHaveBeenLastCalledWith(4);
        expect(readerStateMocks.setPageNumber).toHaveBeenCalledTimes(3);
    });

    it('閉じる時はページ・編集・検索を戻してから外へ通知する', () => {
        const onClose = vi.fn();
        const { result } = renderHook(() => useReaderState({ ...defaultProps, onClose }));
        vi.clearAllMocks();
        act(() => result.current.handleClose());
        const order = [
            readerStateMocks.resetPage,
            readerStateMocks.resetEditMode,
            readerStateMocks.closeSearch,
            readerStateMocks.closeSearchState,
            onClose,
        ].map((fn) => fn.mock.invocationCallOrder[0]);
        expect(order.every((n) => n !== undefined)).toBe(true);
        expect(order).toEqual([...order].sort((a, b) => a - b));
    });
});
