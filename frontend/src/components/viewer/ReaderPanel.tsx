import { useState, useEffect, useCallback } from 'react';
import { Document, pdfjs } from 'react-pdf';

import type { LibrarySource, ReadingDirection, DeletePagesResponse } from '../../types';
import { buildStaticUrl, API_ENDPOINTS, STATIC_PATHS } from '../../config/api';
import apiClient from '../../config/api_client';
import { useWindowSize, useBookImages, useImagePreloader, useReaderNavigation } from '../../hooks';
import { ReaderHeader, PageRenderer } from '../reader';

// Worker は呼び出し元で設定済みの場合もあるが、念のためここでも保証する
if (!pdfjs.GlobalWorkerOptions.workerSrc) {
    pdfjs.GlobalWorkerOptions.workerSrc =
        `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;
}

interface ReaderPanelProps {
    selectedPdf: string;
    currentPath: string;
    currentSource: LibrarySource;
    /** PDF が更新された時にバージョンをインクリメントして親に通知する */
    onPdfUpdated: () => void;
    /** リーダーを閉じてライブラリに戻る */
    onClose: () => void;
}

/**
 * PDF/画像リーダービュー。
 *
 * Reader の表示状態・編集状態を内部で一元管理し、
 * ViewerPage からの props は最小限（選択中PDF・パス・ソース・コールバック）のみ受け取る。
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

    // プリロード (3ページ先読み)
    useImagePreloader(imageUrls, pageNumber - 1, 3);

    // 画像モード切り替え時に numPages を更新
    useEffect(() => {
        if (isImageMode) setNumPages(imageNumPages);
    }, [isImageMode, imageNumPages]);

    // PDF が変わったらリセット
    useEffect(() => {
        setIsEditMode(false);
        setSelectedPages(new Set());
        setNumPages(0);
        resetPage();
    }, [selectedPdf, resetPage]);

    const handleClose = useCallback(() => {
        resetPage();
        setIsEditMode(false);
        setSelectedPages(new Set());
        onClose();
    }, [resetPage, onClose]);

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

    const onDocumentLoadSuccess = useCallback(({ numPages }: { numPages: number }) => {
        setNumPages(numPages);
    }, []);

    // ページレンダリングヘルパー
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
                onClose={handleClose}
                onToggleDirection={toggleDirection}
                onToggleSpread={() => setIsSpread(s => !s)}
                onToggleEditMode={handleToggleEditMode}
                onDeletePages={handleDeletePages}
                onMouseLeave={() => setShowHeader(false)}
            />

            <div className="flex-1 bg-gray-100 overflow-auto relative">
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
