import { useState, useEffect, useCallback } from 'react';
import { Document, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/TextLayer.css';

import type { LibrarySource, ReadingDirection, SpreadMode, DeletePagesResponse } from '../../types';
import { buildStaticUrl, API_ENDPOINTS, STATIC_PATHS } from '../../config/api';
import apiClient from '../../config/api_client';
import { useWindowSize, useBookImages, useImagePreloader, useReaderNavigation, useToast } from '../../hooks';
import { usePdfSearch } from '../../hooks/usePdfSearch';
import { ReaderHeader, PageRenderer, PdfSearchBar, ToastContainer } from '../reader';

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
}

/**
 * PDF/画像リーダービュー。
 *
 * 追加機能:
 * - Viewer内検索: Ctrl+F でサーチバーを開き、PDFテキストレイヤーをハイライト
 * - ダークモード対応の背景色
 */
export function ReaderPanel({
    selectedPdf,
    currentPath,
    currentSource,
    onPdfUpdated,
    onClose,
}: ReaderPanelProps) {
    const { height: windowHeight } = useWindowSize();
    const { imageUrls, numPages: imageNumPages, isImageMode } =
        useBookImages(selectedPdf, currentPath, currentSource);

    // Reader 設定
    const [spreadMode, setSpreadMode] = useState<SpreadMode>('auto');
    // autoモード時にページサイズから計算した実効値（true=見開き、false=1ページ）
    const [autoIsSpread, setAutoIsSpread] = useState(true);
    // 実際のレンダリングに使う isSpread
    const isSpread = spreadMode === 'auto' ? autoIsSpread
        : spreadMode === 'spread';
    const [direction, setDirection] = useState<ReadingDirection>('rtl');
    const [numPages, setNumPages] = useState(0);
    const [showHeader, setShowHeader] = useState(false);
    const [pdfVersion, setPdfVersion] = useState(0);

    // ページナビゲーション
    const { pageNumber, setPageNumber, handleNext, handlePrev, resetPage } =
        useReaderNavigation({ numPages, isSpread, direction, isActive: true });

    // 編集モード
    const [isEditMode, setIsEditMode] = useState(false);
    const [selectedPages, setSelectedPages] = useState<Set<number>>(new Set());
    const { toasts, showToast, dismissToast } = useToast();

    // 検索
    const [isSearchOpen, setIsSearchOpen] = useState(false);
    const {
        searchText, setSearchText,
        matchCount, currentMatch,
        handleCloseSearch: closeSearchState,
        handlePrevMatch, handleNextMatch,
        customTextRenderer,
        onDocumentLoaded,
    } = usePdfSearch({ isSearchOpen, setPageNumber });

    // Ctrl+F でサーチバーを開く
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
                e.preventDefault();
                setIsSearchOpen(true);
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, []);

    const handleCloseSearch = useCallback(() => {
        setIsSearchOpen(false);
        closeSearchState();
    }, [closeSearchState]);

    // プリロード (3ページ先読み)
    useImagePreloader(imageUrls, pageNumber - 1, 3);

    useEffect(() => {
        if (isImageMode) setNumPages(imageNumPages);
    }, [isImageMode, imageNumPages]);

    useEffect(() => {
        setIsEditMode(false);
        setSelectedPages(new Set());
        setNumPages(0);
        setAutoIsSpread(true); // PDF切り替え時に自動判定をリセット
        handleCloseSearch();
        resetPage();
    }, [selectedPdf, resetPage, handleCloseSearch]);

    const handleClose = useCallback(() => {
        resetPage();
        setIsEditMode(false);
        setSelectedPages(new Set());
        handleCloseSearch();
        onClose();
    }, [resetPage, onClose, handleCloseSearch]);

    const toggleDirection = useCallback(() => {
        setDirection(prev => (prev === 'rtl' ? 'ltr' : 'rtl'));
        resetPage();
    }, [resetPage]);

    // Auto → Spread → Single → Auto の順に循環
    const cycleSpreadMode = useCallback(() => {
        setSpreadMode(prev =>
            prev === 'auto' ? 'spread' : prev === 'spread' ? 'single' : 'auto'
        );
    }, []);

    // autoモード時: ページサイズから見開きかどうかを判定する
    const handlePageSize = useCallback((width: number, height: number) => {
        if (spreadMode !== 'auto') return;
        // 横長（width > height）→ 1ページ、縦長 → 見開き
        setAutoIsSpread(width <= height);
    }, [spreadMode]);

    const handleToggleEditMode = useCallback(() => {
        setIsEditMode(prev => !prev);
        setSelectedPages(new Set());
    }, []);

    const togglePageSelection = useCallback((pNum: number, e: React.MouseEvent) => {
        e.stopPropagation();
        setSelectedPages(prev => {
            const next = new Set(prev);
            if (next.has(pNum)) next.delete(pNum);
            else next.add(pNum);
            return next;
        });
    }, []);

    const handleDeletePages = useCallback(async () => {
        if (selectedPages.size === 0) return;
        if (!confirm(`${selectedPages.size} ページを削除しますか？この操作は元に戻せません。`)) return;

        try {
            const pageIndices = Array.from(selectedPages).map(p => p - 1);
            const data = await apiClient.post<unknown, DeletePagesResponse>(
                API_ENDPOINTS.DELETE_PAGES(selectedPdf, currentPath, currentSource),
                { page_indices: pageIndices }
            );
            setIsEditMode(false);
            setSelectedPages(new Set());
            setPdfVersion(v => v + 1);
            onPdfUpdated();

            if (pageNumber > data.total_pages) {
                setPageNumber(Math.max(1, data.total_pages));
            }
        } catch (e: unknown) {
            showToast(e instanceof Error ? e.message : '削除に失敗しました。', 'error');
        }
    }, [selectedPages, selectedPdf, currentPath, currentSource, pageNumber, onPdfUpdated, setPageNumber, showToast]);

    const onDocumentLoadSuccess = useCallback((pdf: pdfjs.PDFDocumentProxy) => {
        setNumPages(pdf.numPages);
        onDocumentLoaded(pdf);
    }, [onDocumentLoaded]);

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
            // RTL: page 1 is the cover, shown alone to avoid page 2 appearing in both spreads
            if (pageNumber === 1) return <>{renderPageItem(p1, 'single')}</>;
            return <>{renderPageItem(p2, 'left')}{renderPageItem(p1, 'right')}</>;
        }
        return <>{renderPageItem(p1, 'left')}{renderPageItem(p2, 'right')}</>;
    };

    const pdfUrl = buildStaticUrl(
        STATIC_PATHS.PDF(currentPath, selectedPdf, currentSource, pdfVersion)
    );

    // 検索バーが開いている分だけコンテンツを下げるオフセット
    const contentTopOffset = isSearchOpen ? 'pt-10' : '';

    return (
        <>
            {/* ヘッダー表示トリガーゾーン */}
            <div
                className="fixed top-0 left-0 right-0 h-16 z-40"
                onMouseEnter={() => setShowHeader(true)}
            />

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
                onClose={handleClose}
                onToggleDirection={toggleDirection}
                onCycleSpreadMode={cycleSpreadMode}
                onToggleEditMode={handleToggleEditMode}
                onDeletePages={handleDeletePages}
                onMouseLeave={() => setShowHeader(false)}
                onToggleSearch={() => setIsSearchOpen(s => !s)}
                onPageJump={setPageNumber}
            />

            {/* 検索バー (isSearchOpen 中は常に表示) */}
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

            <div className={`flex-1 bg-gray-100 dark:bg-gray-950 overflow-auto relative ${contentTopOffset}`}>
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
                                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500" />
                                </div>
                            }
                        >
                            <div className="flex shadow-2xl">
                                {isSpread ? renderSpreadPages() : renderPageItem(pageNumber, 'single')}
                            </div>
                        </Document>
                    )}
                </div>
            </div>
            <ToastContainer toasts={toasts} onDismiss={dismissToast} />
        </>
    );
}
