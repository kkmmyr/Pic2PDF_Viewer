import type { LibrarySource } from '../../types';
import { useReaderState } from '../../hooks/useReaderState';
import { useTouchSwipe } from '../../hooks/useTouchSwipe';
import { ReaderHeader, PdfSearchBar, ToastContainer, PageSlider } from '../reader';
import { EdgeHoverZones } from '../reader/EdgeHoverZones';
import { PageGridOverlay } from '../reader/PageGridOverlay';
import { RelatedBooksPage } from '../reader/RelatedBooksPage';
import { ShortcutsHelpDialog } from '../reader/ShortcutsHelpDialog';
import { ConfirmDialog } from '../ui/ConfirmDialog';
import { ReaderPageView } from './ReaderPageView';

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
 * state / handler はすべて useReaderState が管理し、本コンポーネントは JSX のオーケストレーターに集中する。
 */
export function ReaderPanel(props: ReaderPanelProps) {
    const { selectedPdf, currentPath, currentSource } = props;

    const {
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
        showHeaderOn,
        showHeaderOff,
        showHeaderOnTouch,
        showSlider,
        showSliderOn,
        showSliderOff,
        showSliderOnTouch,
        pauseSliderTimer,
        resumeSliderTimer,
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
        toasts,
        dismissToast,
        pageNumber,
        setPageNumber,
        handleNext,
        handlePrev,
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
    } = useReaderState(props);

    const { onTouchStart, onTouchEnd } = useTouchSwipe({
        onSwipeLeft: handleNext,
        onSwipeRight: handlePrev,
    });

    return (
        <>
            <EdgeHoverZones
                onEnterTop={showHeaderOn}
                onEnterBottom={showSliderOn}
                onTouchTop={showHeaderOnTouch}
                onTouchBottom={showSliderOnTouch}
            />

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
                onDragStart={pauseSliderTimer}
                onDragEnd={resumeSliderTimer}
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
                        onTouchStart={onTouchStart}
                        onTouchEnd={onTouchEnd}
                    >
                        <ReaderPageView
                            pageNumber={pageNumber}
                            numPages={numPages}
                            windowHeight={windowHeight}
                            isSpread={isSpread}
                            direction={direction}
                            onNext={handleNext}
                            onPrev={handlePrev}
                            isImageMode={isImageMode}
                            imageUrls={imageUrls}
                            searchText={searchText}
                            customTextRenderer={customTextRenderer}
                            handlePageSize={handlePageSize}
                            pdfUrl={pdfUrl}
                            onDocumentLoadSuccess={onDocumentLoadSuccess}
                        />
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
