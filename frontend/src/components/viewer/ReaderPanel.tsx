import { useState, useEffect, useCallback, useRef } from 'react';
import { Document, pdfjs } from 'react-pdf';

import type { LibrarySource, ReadingDirection, DeletePagesResponse } from '../../types';
import { buildStaticUrl, API_ENDPOINTS, STATIC_PATHS } from '../../config/api';
import apiClient from '../../config/api_client';
import { useWindowSize, useBookImages, useImagePreloader, useReaderNavigation } from '../../hooks';
import { ReaderHeader, PageRenderer, PdfSearchBar } from '../reader';

if (!pdfjs.GlobalWorkerOptions.workerSrc) {
    pdfjs.GlobalWorkerOptions.workerSrc =
        `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;
}

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
    const [isSpread, setIsSpread] = useState(true);
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

    // 検索
    const [isSearchOpen, setIsSearchOpen] = useState(false);
    const [searchText, setSearchText] = useState('');
    const [matchCount, setMatchCount] = useState(0);
    const [currentMatch, setCurrentMatch] = useState(0);
    // PDFページのテキストコンテンツ: { pageNum -> TextItem[] }
    const pdfRef = useRef<pdfjs.PDFDocumentProxy | null>(null);

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

    // 検索クローズ時にリセット
    const handleCloseSearch = useCallback(() => {
        setIsSearchOpen(false);
        setSearchText('');
        setMatchCount(0);
        setCurrentMatch(0);
    }, []);

    // テキスト検索: 全ページを走査してマッチ数を算出し、最初のマッチページに移動
    const searchAllPages = useCallback(async (text: string) => {
        if (!pdfRef.current || !text) {
            setMatchCount(0);
            setCurrentMatch(0);
            return;
        }

        let totalMatches = 0;
        let firstMatchPage = -1;
        const lowerText = text.toLowerCase();

        for (let i = 1; i <= pdfRef.current.numPages; i++) {
            const page = await pdfRef.current.getPage(i);
            const content = await page.getTextContent();
            const pageText = content.items
                .map((item) => ('str' in item ? item.str : ''))
                .join('');
            const count = (pageText.toLowerCase().match(new RegExp(
                lowerText.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'
            )) || []).length;

            if (count > 0 && firstMatchPage === -1) firstMatchPage = i;
            totalMatches += count;
        }

        setMatchCount(totalMatches);
        setCurrentMatch(totalMatches > 0 ? 1 : 0);
        if (firstMatchPage > 0 && firstMatchPage !== pageNumber) {
            setPageNumber(firstMatchPage);
        }
    }, [pageNumber, setPageNumber]);

    useEffect(() => {
        if (!isSearchOpen) return;
        searchAllPages(searchText);
    }, [searchText, isSearchOpen, searchAllPages]);

    const handlePrevMatch = useCallback(() => {
        setCurrentMatch(prev => (prev > 1 ? prev - 1 : matchCount));
    }, [matchCount]);

    const handleNextMatch = useCallback(() => {
        setCurrentMatch(prev => (prev < matchCount ? prev + 1 : 1));
    }, [matchCount]);

    // プリロード (3ページ先読み)
    useImagePreloader(imageUrls, pageNumber - 1, 3);

    useEffect(() => {
        if (isImageMode) setNumPages(imageNumPages);
    }, [isImageMode, imageNumPages]);

    useEffect(() => {
        setIsEditMode(false);
        setSelectedPages(new Set());
        setNumPages(0);
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
            alert(e instanceof Error ? e.message : '削除に失敗しました。');
        }
    }, [selectedPages, selectedPdf, currentPath, currentSource, pageNumber, onPdfUpdated, setPageNumber]);

    const onDocumentLoadSuccess = useCallback((pdf: pdfjs.PDFDocumentProxy) => {
        setNumPages(pdf.numPages);
        pdfRef.current = pdf;
    }, []);

    // テキストレイヤーのハイライトレンダラー
    const customTextRenderer = useCallback(
        ({ str }: { str: string }) => {
            if (!searchText || !str) return str;
            const escaped = searchText.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
            const regex = new RegExp(`(${escaped})`, 'gi');
            return str.replace(regex, `<mark style="background:rgba(255,200,0,0.5);border-radius:2px;">$1</mark>`);
        },
        [searchText]
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
        />
    );

    const renderSpreadPages = () => {
        const p1 = pageNumber;
        const p2 = pageNumber + 1;
        if (direction === 'rtl') {
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
                isSpread={isSpread}
                pageNumber={pageNumber}
                numPages={numPages}
                isEditMode={isEditMode}
                selectedPagesCount={selectedPages.size}
                showHeader={showHeader}
                isSearchOpen={isSearchOpen}
                onClose={handleClose}
                onToggleDirection={toggleDirection}
                onToggleSpread={() => setIsSpread(s => !s)}
                onToggleEditMode={handleToggleEditMode}
                onDeletePages={handleDeletePages}
                onMouseLeave={() => setShowHeader(false)}
                onToggleSearch={() => setIsSearchOpen(s => !s)}
                onPageJump={setPageNumber}
            />

            {/* 検索バー (ヘッダーが表示中のみ表示) */}
            {isSearchOpen && showHeader && (
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
        </>
    );
}
