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
import { usePdfSearch } from '../../hooks/usePdfSearch';
import { useReaderShortcuts } from '../../hooks/useReaderShortcuts';
import { useReaderUIState } from '../../hooks/useReaderUIState';
import { usePdfDocumentState } from '../../hooks/usePdfDocumentState';
import { ReaderHeader, PageRenderer, PdfSearchBar, ToastContainer, PageSlider } from '../reader';
import { EdgeHoverZones } from '../reader/EdgeHoverZones';
import { NextVolumeBanner } from '../reader/NextVolumeBanner';
import { ShortcutsHelpDialog } from '../reader/ShortcutsHelpDialog';
import { ConfirmDialog } from '../ui/ConfirmDialog';

// <Document> を使うモジュールと同じファイルで workerSrc を設定する必要がある（react-pdf の要件）
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
    'pdfjs-dist/build/pdf.worker.min.mjs',
    import.meta.url,
).toString();

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
    const {
        imageUrls,
        numPages: imageNumPages,
        isImageMode,
    } = useBookImages(selectedPdf, currentPath, currentSource);

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

    const { pageNumber, setPageNumber, handleNext, handlePrev, resetPage } = useReaderNavigation({
        numPages,
        isSpread,
        direction,
        isActive: true,
    });

    const { toasts, showToast, dismissToast } = useToast();

    // 「次の巻へ」用に書籍メタデータを参照する。
    // 同 series_id で series_index が現在より大きい中で最小のものを次巻とする。
    // 判定範囲は同フォルダ内のみ（meta のキー prefix で path 一致をチェック）。
    const { meta, getSeries, recordView } = useBookMeta(currentSource);
    const nextVolume = useNextSeriesVolume(meta, getSeries, currentPath, selectedPdf);
    const prevVolume = usePrevSeriesVolume(meta, getSeries, currentPath, selectedPdf);

    // 最終ページ/最終スプレッド到達判定。numPages が未確定（0）なら表示しない。
    const isAtLastSpread =
        numPages > 0 && (isSpread ? pageNumber + 1 >= numPages : pageNumber >= numPages);

    const handleNavigateNextVolume = useCallback(() => {
        if (!nextVolume || !onSelectPdf) return;
        recordView(currentPath, nextVolume.name);
        onSelectPdf(nextVolume.name);
    }, [nextVolume, onSelectPdf, recordView, currentPath]);

    const handleNavigatePrevVolume = useCallback(() => {
        if (!prevVolume || !onSelectPdf) return;
        recordView(currentPath, prevVolume.name);
        onSelectPdf(prevVolume.name);
    }, [prevVolume, onSelectPdf, recordView, currentPath]);

    const {
        isEditMode,
        selectedPages,
        toggleEditMode,
        togglePageSelection,
        resetEditMode,
        requestDeletePages,
        confirmDeletePages,
        cancelDeletePages,
        pendingDeleteCount,
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

    // PDF 内テキスト検索
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

    // キーボードショートカット（Ctrl+F / f / e / ?）を集約
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

    // プリロード (3ページ先読み)
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
    }, [selectedPdf, resetPage, handleCloseSearch, resetEditMode, resetAutoSpread, resetNumPages]);

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
            isEditMode={isEditMode}
            isSelected={selectedPages.has(pNum)}
            side={side}
            direction={direction}
            onToggleSelection={togglePageSelection}
            onNext={handleNext}
            onPrev={handlePrev}
            isImageMode={isImageMode}
            imageUrl={imageUrls ? imageUrls[pNum - 1] : null}
            searchText={searchText}
            customTextRenderer={!isImageMode && searchText ? customTextRenderer : undefined}
            onPageSize={side === 'right' || side === 'single' ? handlePageSize : undefined}
        />
    );

    const renderSpreadPages = () => {
        const p1 = pageNumber;
        const p2 = pageNumber + 1;
        if (direction === 'rtl') {
            // RTL: 1ページ目（表紙）は単独表示。2ページ目を両スプレッドに出さないため
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

    // 検索バーが開いている分だけコンテンツを下げるオフセット
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
                selectedPagesCount={selectedPages.size}
                showHeader={showHeader || isSearchOpen}
                isSearchOpen={isSearchOpen}
                isFullscreen={isFullscreen}
                onClose={handleClose}
                onToggleDirection={toggleDirection}
                onCycleSpreadMode={cycleSpreadMode}
                onToggleEditMode={toggleEditMode}
                onDeletePages={requestDeletePages}
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
                show={showSlider}
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

            <div
                className={`flex-1 bg-gray-100 dark:bg-gray-950 overflow-auto relative ${contentTopOffset}`}
            >
                <div
                    className="min-h-full flex items-center justify-center p-4 w-fit mx-auto"
                    onClick={handleNext}
                >
                    {isImageMode ? (
                        <div className="flex gap-0 shadow-2xl justify-center bg-gray-900">
                            {isSpread ? renderSpreadPages() : renderPageItem(pageNumber, 'single')}
                        </div>
                    ) : (
                        <Document
                            file={pdfUrl}
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
            {nextVolume && isAtLastSpread && onSelectPdf && (
                <NextVolumeBanner
                    title={`次の巻: #${nextVolume.index} ${nextVolume.title}`}
                    onClick={handleNavigateNextVolume}
                />
            )}

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
