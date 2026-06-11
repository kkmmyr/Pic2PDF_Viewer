import { renderHook } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';

// 複数の API フェッチ hook をモックしてスモークテストを実現する
vi.mock('../hooks', () => ({
    useWindowSize: () => ({ height: 900 }),
    useBookImages: () => ({ imageUrls: null, numPages: 0, isImageMode: false }),
    useImagePreloader: vi.fn(),
    useReaderNavigation: () => ({
        pageNumber: 1,
        setPageNumber: vi.fn(),
        handleNext: vi.fn(),
        handlePrev: vi.fn(),
        resetPage: vi.fn(),
    }),
    useSpreadMode: () => ({
        spreadMode: 'auto' as const,
        isSpread: true,
        cycleSpreadMode: vi.fn(),
        handlePageSize: vi.fn(),
        resetAutoSpread: vi.fn(),
    }),
    useEditMode: () => ({
        isEditMode: false,
        selectedPages: new Set<number>(),
        toggleEditMode: vi.fn(),
        togglePageSelection: vi.fn(),
        selectRange: vi.fn(),
        resetEditMode: vi.fn(),
        requestDeletePages: vi.fn(),
        confirmDeletePages: vi.fn(),
        cancelDeletePages: vi.fn(),
        pendingDeleteCount: 0,
        applyReorder: vi.fn(),
    }),
    useFullscreen: () => ({ isFullscreen: false, toggleFullscreen: vi.fn() }),
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
        handleCloseSearch: vi.fn(),
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
        closeSearch: vi.fn(),
        toggleSearch: vi.fn(),
        isHelpOpen: false,
        openHelp: vi.fn(),
        closeHelp: vi.fn(),
    }),
}));
vi.mock('../hooks/reader/usePdfDocumentState', () => ({
    usePdfDocumentState: () => ({
        numPages: 0,
        setNumPages: vi.fn(),
        resetNumPages: vi.fn(),
        pdfVersion: 0,
        bumpPdfVersion: vi.fn(),
        handleDocumentLoadSuccess: vi.fn(),
    }),
}));
vi.mock('../hooks/reader/useRelatedBooksNavigation', () => ({
    useRelatedBooksNavigation: () => ({
        isOnRelatedPage: false,
        setIsOnRelatedPage: vi.fn(),
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
});
