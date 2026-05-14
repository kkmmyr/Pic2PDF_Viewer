import { useState, useEffect, useCallback } from 'react';
import { Document, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/TextLayer.css';

import type { LibrarySource, ReadingDirection } from '../../types';
import { buildStaticUrl, STATIC_PATHS } from '../../config/api';
import {
    useWindowSize,
    useBookImages,
    useImagePreloader,
    useReaderNavigation,
    useToast,
    useSpreadMode,
    useEditMode,
    useFullscreen,
    useBookMeta,
} from '../../hooks';
import { useNextSeriesVolume, usePrevSeriesVolume } from '../../hooks/useNextSeriesVolume';
import { useRelatedBooks } from '../../hooks/useRelatedBooks';
import { usePdfSearch } from '../../hooks/usePdfSearch';
import { useReaderShortcuts } from '../../hooks/useReaderShortcuts';
import { useReaderUIState } from '../../hooks/useReaderUIState';
import { usePdfDocumentState } from '../../hooks/usePdfDocumentState';
import { useRelatedBooksNavigation } from '../../hooks/useRelatedBooksNavigation';
import { useReadProgressTracker } from '../../hooks/useReadProgressTracker';
import { useVolumeNavigation } from '../../hooks/useVolumeNavigation';
import { ReaderHeader, PageRenderer, PdfSearchBar, ToastContainer, PageSlider } from '../reader';
import { EdgeHoverZones } from '../reader/EdgeHoverZones';
import { PageGridOverlay } from '../reader/PageGridOverlay';
import { RelatedBooksPage } from '../reader/RelatedBooksPage';
import { ShortcutsHelpDialog } from '../reader/ShortcutsHelpDialog';
import { ConfirmDialog } from '../ui/ConfirmDialog';

// <Document> を使うモジュールと同じファイルで workerSrc を設定する必要がある（react-pdf の要件）
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
    'pdfjs-dist/build/pdf.worker.min.mjs',
    import.meta.url,
).toString();

// Searchable PDF（ReportLab 生成）に含まれる ASCII85 ストリーム中の `<` を pdf.js の lenient parser が
// hex string 開始と誤読し getHexString warning を大量に出すため、verbosity を ERRORS に下げる。
// Document の options は識別性が変わると再読込を誘発するためモジュールスコープで固定する。
const PDF_DOCUMENT_OPTIONS = {
    verbosity: pdfjs.VerbosityLevel.ERRORS,
};

interface ReaderPanelProps {
    selectedPdf: string;
    currentPath: string;
    currentSource: LibrarySource;
    onPdfUpdated: () => void;
    onClose: () => void;
    /** 同フォルダ内の別書籍に切り替える（「次の巻へ」遷移用） */
    onSelectPdf?: (name: string) => void;
}

/**
 * PDF/画像リーダービュー。
 *
 * - Ctrl+F で PDF テキストレイヤーをハイライト検索
 * - 編集モードでページを選択して削除（`useEditMode`）
 * - 見開き Auto/Spread/Single モード切り替え（`useSpreadMode`）
 */
export function ReaderPanel({
    selectedPdf,
    currentPath,
    currentSource,
    onPdfUpdated,
    onClose,
    onSelectPdf,
}: ReaderPanelProps) {
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
        showHeaderOn,
        showHeaderOff,
        showSlider,
        showSliderOn,
        showSliderOff,
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
    const { toasts, showToast, dismissToast } = useToast();

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

    // 最終ページ/最終スプレッド到達判定。numPages が未確定（0）なら表示しない。
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
        showError: (msg) => showToast(msg, 'error'),
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

    useReaderShortcuts({
        isActive: true,
        onToggleFullscreen: toggleFullscreen,
        onToggleEditMode: toggleEditMode,
        onOpenHelp: openHelp,
        onToggleSearch: openSearch,
        onNavigateNextVolume: nextVolume && onSelectPdf ? handleNavigateNextVolume : null,
        onNavigatePrevVolume: prevVolume && onSelectPdf ? handleNavigatePrevVolume : null,
    });

    const handleCloseSearch = useCallback(() => {
        closeSearch();
        closeSearchState();
    }, [closeSearch, closeSearchState]);

    useImagePreloader(imageUrls, pageNumber - 1, 3);

    useEffect(() => {
        if (isImageMode) setNumPages(imageNumPages);
    }, [isImageMode, imageNumPages, setNumPages]);

    useEffect(() => {
        resetEditMode();
        resetNumPages();
        resetAutoSpread();
        handleCloseSearch();
        resetPage();
        setIsOnRelatedPage(false);
    }, [selectedPdf, resetPage, handleCloseSearch, resetEditMode, resetAutoSpread, resetNumPages, setIsOnRelatedPage]);

    // ページペア切替時に Auto 見開き判定をリセット。直後に PageRenderer の onRenderSuccess
    // で左右両ページの寸法が通知され、片方でも横長なら 1 ページ表示に確定する。
    useEffect(() => {
        resetAutoSpread();
    }, [pageNumber, resetAutoSpread]);

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

    const renderPageItem = (pNum: number, side: 'left' | 'right' | 'single') => (
        <PageRenderer
            key={`page-${pNum}`}
            pageNumber={pNum}
            numPages={numPages}
            windowHeight={windowHeight}
            side={side}
            direction={direction}
            onNext={handleNext}
            onPrev={handlePrev}
            isImageMode={isImageMode}
            imageUrl={imageUrls ? imageUrls[pNum - 1] : null}
            searchText={searchText}
            customTextRenderer={!isImageMode && searchText ? customTextRenderer : undefined}
            isSpread={isSpread}
            onPageSize={handlePageSize}
        />
    );

    const renderSpreadPages = () => {
        const p1 = pageNumber;
        const p2 = pageNumber + 1;
        if (direction === 'rtl') {
            if (pageNumber === 1) return <>{renderPageItem(p1, 'single')}</>;
            return (
                <>
                    {renderPageItem(p2, 'left')}
                    {renderPageItem(p1, 'right')}
                </>
            );
        }
        return (
            <>
                {renderPageItem(p1, 'left')}
                {renderPageItem(p2, 'right')}
            </>
        );
    };

    const pdfUrl = buildStaticUrl(
        STATIC_PATHS.PDF(currentPath, selectedPdf, currentSource, pdfVersion),
    );

    const contentTopOffset = isSearchOpen ? 'pt-10' : '';

    return (
        <>
            <EdgeHoverZones onEnterTop={showHeaderOn} onEnterBottom={showSliderOn} />

            <ReaderHeader
                selectedPdf={selectedPdf}
                direction={direction}
                spreadMode={spreadMode}
                pageNumber={pageNumber}
                numPages={numPages}
                isEditMode={isEditMode}
                showHeader={showHeader || isSearchOpen}
                isSearchOpen={isSearchOpen}
                isFullscreen={isFullscreen}
                hidePageIndicator={isOnRelatedPage}
                onClose={handleClose}
                onToggleDirection={toggleDirection}
                onCycleSpreadMode={cycleSpreadMode}
                onToggleEditMode={toggleEditMode}
                onMouseLeave={showHeaderOff}
                onToggleSearch={toggleSearch}
                onToggleFullscreen={toggleFullscreen}
                onOpenHelp={openHelp}
            />

            <PageSlider
                pageNumber={pageNumber}
                numPages={numPages}
                isSpread={isSpread}
                direction={direction}
                show={showSlider && !isOnRelatedPage}
                selectedPdf={selectedPdf}
                currentPath={currentPath}
                currentSource={currentSource}
                onPageJump={setPageNumber}
                onMouseLeave={showSliderOff}
            />

            {isSearchOpen && (
                <PdfSearchBar
                    searchText={searchText}
                    matchCount={matchCount}
                    currentMatch={currentMatch}
                    onSearchChange={setSearchText}
                    onPrevMatch={handlePrevMatch}
                    onNextMatch={handleNextMatch}
                    onClose={handleCloseSearch}
                />
            )}

            {isOnRelatedPage ? (
                <div
                    className={`flex-1 bg-gray-100 dark:bg-gray-950 overflow-auto relative ${contentTopOffset}`}
                >
                    <RelatedBooksPage
                        related={relatedBooks}
                        currentPath={currentPath}
                        currentSource={currentSource}
                        onSelect={handleSelectRelated}
                    />
                </div>
            ) : (
                <div
                    className={`flex-1 bg-gray-100 dark:bg-gray-950 overflow-auto relative ${contentTopOffset}`}
                >
                    <div
                        className="min-h-full flex items-center justify-center p-4 w-fit mx-auto"
                        onClick={handleNext}
                    >
                        {isImageMode ? (
                            <div className="flex gap-0 shadow-2xl justify-center bg-gray-900">
                                {isSpread
                                    ? renderSpreadPages()
                                    : renderPageItem(pageNumber, 'single')}
                            </div>
                        ) : (
                            <Document
                                file={pdfUrl}
                                options={PDF_DOCUMENT_OPTIONS}
                                onLoadSuccess={onDocumentLoadSuccess}
                                className="flex justify-center"
                                loading={
                                    <div className="flex items-center justify-center h-96">
                                        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-500" />
                                    </div>
                                }
                            >
                                <div className="flex shadow-2xl">
                                    {isSpread
                                        ? renderSpreadPages()
                                        : renderPageItem(pageNumber, 'single')}
                                </div>
                            </Document>
                        )}
                    </div>
                </div>
            )}

            <PageGridOverlay
                open={isEditMode && numPages > 0}
                selectedPdf={selectedPdf}
                currentPath={currentPath}
                currentSource={currentSource}
                numPages={numPages}
                pdfVersion={pdfVersion}
                selectedPages={selectedPages}
                onClose={toggleEditMode}
                onTogglePage={togglePageSelection}
                onSelectRange={selectRange}
                onRequestDelete={requestDeletePages}
                onApplyReorder={applyReorder}
            />

            <ConfirmDialog
                open={pendingDeleteCount > 0}
                title="ページを削除"
                message={`${pendingDeleteCount} ページを削除しますか？\nこの操作は元に戻せません。`}
                confirmLabel="削除"
                danger
                onConfirm={confirmDeletePages}
                onCancel={cancelDeletePages}
            />

            <ShortcutsHelpDialog open={isHelpOpen} onClose={closeHelp} />

            <ToastContainer toasts={toasts} onDismiss={dismissToast} />
        </>
    );
}
