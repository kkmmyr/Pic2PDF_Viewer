import { useState, useCallback } from 'react';
import { useReaderLifecycle } from '@/features/reader/useReaderLifecycle';
import { pdfjs } from 'react-pdf';
import type { LibrarySource, ReadingDirection } from '@/types';
import { buildStaticUrl, STATIC_PATHS } from '@/config/api';
import { toast } from 'sonner';
import { useWindowSize } from '@/hooks/useWindowSize';
import { useBookMeta } from '@/hooks/library/useBookMeta';
import { useBookImages } from '@/hooks/reader/useBookImages';
import { useImagePreloader } from '@/hooks/reader/useImagePreloader';
import { useReaderNavigation } from '@/hooks/reader/useReaderNavigation';
import { useSpreadMode } from '@/hooks/reader/useSpreadMode';
import { useEditMode } from '@/hooks/reader/useEditMode';
import { useFullscreen } from '@/hooks/reader/useFullscreen';
import { useNextSeriesVolume, usePrevSeriesVolume } from '@/hooks/reader/useNextSeriesVolume';
import { useRelatedBooks } from '@/hooks/reader/useRelatedBooks';
import { usePdfSearch } from '@/hooks/reader/usePdfSearch';
import { useReaderUIState } from '@/hooks/reader/useReaderUIState';
import { usePdfDocumentState } from '@/hooks/reader/usePdfDocumentState';
import { useRelatedBooksNavigation } from '@/hooks/reader/useRelatedBooksNavigation';
import { useReadProgressTracker } from '@/hooks/reader/useReadProgressTracker';
import { useVolumeNavigation } from '@/hooks/reader/useVolumeNavigation';
import { useReaderInput } from '@/hooks/reader/useReaderInput';

interface UseReaderStateProps {
    selectedPdf: string;
    currentPath: string;
    currentSource: LibrarySource;
    initialPage?: number;
    onPdfUpdated: () => void;
    onClose: () => void;
    onSelectPdf?: (name: string) => void;
}

/**
 * ReaderPanel が必要とする全 state / handler を集約するフック。
 * 専門hookを組み立て、初期化順はuseReaderLifecycleへ委譲する。
 * ReaderPanel 本体は JSX のオーケストレーターに集中できる。
 */
export function useReaderState({
    selectedPdf,
    currentPath,
    currentSource,
    initialPage,
    onPdfUpdated,
    onClose,
    onSelectPdf,
}: UseReaderStateProps) {
    const { height: windowHeight } = useWindowSize();
    const [direction, setDirection] = useState<ReadingDirection>('rtl');

    const {
        numPages,
        setNumPages,
        resetNumPages,
        pdfVersion,
        bumpPdfVersion,
        handleDocumentLoadSuccess,
    } = usePdfDocumentState();

    const {
        imageUrls,
        numPages: imageNumPages,
        isImageMode,
    } = useBookImages(selectedPdf, currentPath, currentSource, pdfVersion);

    const {
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
    } = useReaderUIState();

    const { spreadMode, isSpread, cycleSpreadMode, handlePageSize, resetAutoSpread } =
        useSpreadMode();
    const { isFullscreen, toggleFullscreen } = useFullscreen();

    const { meta, getSeries, recordView, getReadState, setReadState } = useBookMeta(currentSource);
    const nextVolume = useNextSeriesVolume(meta, getSeries, currentPath, selectedPdf);
    const prevVolume = usePrevSeriesVolume(meta, getSeries, currentPath, selectedPdf);
    const relatedBooks = useRelatedBooks(meta, currentPath, selectedPdf);

    const {
        isOnRelatedPage,
        setIsOnRelatedPage,
        handleNextAtEnd,
        handlePrevIntercept,
        handleSelectRelated,
    } = useRelatedBooksNavigation({ relatedBooks, onSelectPdf, recordView, currentPath });

    const { pageNumber, setPageNumber, handleNext, handlePrev, resetPage } = useReaderNavigation({
        numPages,
        isSpread,
        direction,
        isActive: true,
        onNextAtEnd: handleNextAtEnd,
        onPrevIntercept: handlePrevIntercept,
    });

    const { handleNavigateNextVolume, handleNavigatePrevVolume } = useVolumeNavigation({
        nextVolume,
        prevVolume,
        onSelectPdf,
        recordView,
        currentPath,
    });

    const isAtLastSpread =
        numPages > 0 && (isSpread ? pageNumber + 1 >= numPages : pageNumber >= numPages);

    useReadProgressTracker({
        selectedPdf,
        currentPath,
        isAtLastSpread,
        getReadState,
        setReadState,
    });

    const {
        isEditMode,
        selectedPages,
        toggleEditMode,
        togglePageSelection,
        selectRange,
        resetEditMode,
        requestDeletePages,
        confirmDeletePages,
        cancelDeletePages,
        pendingDeleteCount,
        applyReorder,
    } = useEditMode({
        selectedPdf,
        currentPath,
        currentSource,
        pageNumber,
        setPageNumber,
        onPdfUpdated,
        bumpPdfVersion,
        showError: (msg) => toast.error(msg),
    });

    const {
        searchText,
        setSearchText,
        matchCount,
        currentMatch,
        handleCloseSearch: closeSearchState,
        handlePrevMatch,
        handleNextMatch,
        customTextRenderer,
        onDocumentLoaded,
    } = usePdfSearch({ isSearchOpen, setPageNumber });

    const handleCloseSearch = useCallback(() => {
        closeSearch();
        closeSearchState();
    }, [closeSearch, closeSearchState]);

    useReaderInput({
        toggleFullscreen,
        toggleEditMode,
        openHelp,
        openSearch,
        hasNextVolume: Boolean(nextVolume),
        hasPrevVolume: Boolean(prevVolume),
        onSelectPdf,
        onNavigateNextVolume: handleNavigateNextVolume,
        onNavigatePrevVolume: handleNavigatePrevVolume,
    });

    useImagePreloader(imageUrls, pageNumber - 1, 3);

    useReaderLifecycle({
        selectedPdf,
        initialPage,
        isImageMode,
        imageNumPages,
        numPages,
        pageNumber,
        resetEditMode,
        resetNumPages,
        resetAutoSpread,
        handleCloseSearch,
        resetPage,
        setIsOnRelatedPage,
        setNumPages,
        setPageNumber,
    });

    const handleClose = useCallback(() => {
        resetPage();
        resetEditMode();
        handleCloseSearch();
        onClose();
    }, [resetPage, onClose, handleCloseSearch, resetEditMode]);

    const toggleDirection = useCallback(() => {
        setDirection((prev) => (prev === 'rtl' ? 'ltr' : 'rtl'));
        resetPage();
    }, [resetPage]);

    const onDocumentLoadSuccess = useCallback(
        (pdf: pdfjs.PDFDocumentProxy) => {
            handleDocumentLoadSuccess(pdf, onDocumentLoaded);
        },
        [handleDocumentLoadSuccess, onDocumentLoaded],
    );

    const pdfUrl = buildStaticUrl(
        STATIC_PATHS.PDF(currentPath, selectedPdf, currentSource, pdfVersion),
    );

    const contentTopOffset = isSearchOpen ? 'pt-10' : '';

    return {
        windowHeight,
        direction,
        toggleDirection,
        numPages,
        pdfVersion,
        onDocumentLoadSuccess,
        pdfUrl,
        imageUrls,
        isImageMode,
        showHeader,
        showHeaderOff,
        showSlider,
        showSliderOff,
        pauseSliderTimer,
        resumeSliderTimer,
        toggleBothUI,
        isSearchOpen,
        toggleSearch,
        isHelpOpen,
        openHelp,
        closeHelp,
        spreadMode,
        isSpread,
        cycleSpreadMode,
        handlePageSize,
        isFullscreen,
        toggleFullscreen,
        pageNumber,
        setPageNumber,
        handleNext,
        handlePrev,
        nextVolume,
        prevVolume,
        handleNavigateNextVolume,
        handleNavigatePrevVolume,
        relatedBooks,
        isOnRelatedPage,
        handleSelectRelated,
        isEditMode,
        selectedPages,
        toggleEditMode,
        togglePageSelection,
        selectRange,
        requestDeletePages,
        confirmDeletePages,
        cancelDeletePages,
        pendingDeleteCount,
        applyReorder,
        searchText,
        setSearchText,
        matchCount,
        currentMatch,
        handleCloseSearch,
        handlePrevMatch,
        handleNextMatch,
        customTextRenderer,
        contentTopOffset,
        handleClose,
    };
}
