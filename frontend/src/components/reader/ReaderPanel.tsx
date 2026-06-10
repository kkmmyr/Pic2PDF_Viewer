import { useCallback } from 'react';
import type { LibrarySource } from '../../types';
import { ReaderProvider, useReaderContext } from '../../contexts/ReaderContext';
import { useTouchSwipe } from '../../hooks/useTouchSwipe';
import { PdfSearchBar } from './PdfSearchBar';
import { PageSlider } from './PageSlider';
import { PageGridOverlay } from './PageGridOverlay';
import { RelatedBooksPage } from './RelatedBooksPage';
import { ShortcutsHelpDialog } from './ShortcutsHelpDialog';
import { ReaderHeader } from './ReaderHeader';
import { ReaderPageView } from './ReaderPageView';
import { ConfirmDialog } from '../ui/ConfirmDialog';

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
 * state / handler はすべて ReaderProvider (useReaderState) が管理し、
 * 本コンポーネントは JSX のオーケストレーターに集中する。
 */
export function ReaderPanel(props: ReaderPanelProps) {
    return (
        <ReaderProvider {...props}>
            <ReaderPanelContent />
        </ReaderProvider>
    );
}

function ReaderPanelContent() {
    const {
        direction,
        handleNext,
        handlePrev,
        showHeader,
        showSlider,
        toggleBothUI,
        isSearchOpen,
        isOnRelatedPage,
        contentTopOffset,
        // PageSlider
        pageNumber,
        numPages,
        isSpread,
        selectedPdf,
        currentPath,
        currentSource,
        setPageNumber,
        showSliderOff,
        pauseSliderTimer,
        resumeSliderTimer,
        // PdfSearchBar
        searchText,
        matchCount,
        currentMatch,
        setSearchText,
        handlePrevMatch,
        handleNextMatch,
        handleCloseSearch,
        // RelatedBooksPage
        relatedBooks,
        handleSelectRelated,
        // PageGridOverlay
        isEditMode,
        pdfVersion,
        selectedPages,
        toggleEditMode,
        togglePageSelection,
        selectRange,
        requestDeletePages,
        applyReorder,
        // ConfirmDialog
        pendingDeleteCount,
        confirmDeletePages,
        cancelDeletePages,
    } = useReaderContext();

    const { onTouchStart, onTouchEnd, onTouchCancel } = useTouchSwipe({
        onSwipeLeft: direction === 'rtl' ? handlePrev : handleNext,
        onSwipeRight: direction === 'rtl' ? handleNext : handlePrev,
    });

    const noop = useCallback(() => {}, []);
    const {
        onTouchStart: onRelatedTouchStart,
        onTouchEnd: onRelatedTouchEnd,
        onTouchCancel: onRelatedTouchCancel,
    } = useTouchSwipe({
        onSwipeLeft: direction === 'rtl' ? handlePrev : noop,
        onSwipeRight: direction === 'rtl' ? noop : handlePrev,
    });

    const handleContentClick = useCallback(
        (e: React.MouseEvent) => {
            const zone = e.clientX / window.innerWidth;
            if (zone < 1 / 3) {
                if (direction === 'rtl') handleNext();
                else handlePrev();
            } else if (zone > 2 / 3) {
                if (direction === 'rtl') handlePrev();
                else handleNext();
            } else {
                toggleBothUI(showHeader, showSlider);
            }
        },
        [direction, handleNext, handlePrev, toggleBothUI, showHeader, showSlider],
    );

    return (
        <>
            <ReaderHeader />

            <PageSlider
                pageNumber={pageNumber}
                numPages={numPages}
                isSpread={isSpread}
                direction={direction}
                show={showSlider || isOnRelatedPage}
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
                    onTouchStart={onRelatedTouchStart}
                    onTouchEnd={onRelatedTouchEnd}
                    onTouchCancel={onRelatedTouchCancel}
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
                        className="min-h-full flex items-center justify-center p-4 w-full"
                        style={{ touchAction: 'pan-y' }}
                        onClick={handleContentClick}
                        onTouchStart={onTouchStart}
                        onTouchEnd={onTouchEnd}
                        onTouchCancel={onTouchCancel}
                    >
                        <ReaderPageView />
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

            <ShortcutsHelpDialog />
        </>
    );
}
