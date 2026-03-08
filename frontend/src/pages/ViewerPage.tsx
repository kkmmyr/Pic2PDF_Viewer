import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Document, pdfjs } from 'react-pdf';

// Types
import type { PdfFile, ReadingDirection, LibrarySource } from '../types';

// Config
import { buildStaticUrl, API_ENDPOINTS, STATIC_PATHS } from '../config/api';
import apiClient from '../config/api_client';

// Hooks
import { useWindowSize, useBookImages, useImagePreloader, useLibraryManagement, useReaderNavigation } from '../hooks';

// Components
import {
    ReaderHeader,
    LibraryHeader,
    FolderGrid,
    PdfGrid,
    MoveDialog,
    PageRenderer,
} from '../components/reader';

// Set worker source
pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

export default function ViewerPage() {
    const [searchParams, setSearchParams] = useSearchParams();

    // Derived state from URL
    const currentPath = searchParams.get('path') || "";
    const selectedPdf = searchParams.get('file');
    const [currentPathState, setCurrentPath] = useState(currentPath);
    const [selectedPdfState, setSelectedPdf] = useState<string | null>(selectedPdf);

    const [pdfs, setPdfs] = useState<PdfFile[]>([]);
    const [directories, setDirectories] = useState<string[]>([]);

    // Source State
    const [currentSource, setCurrentSource] = useState<LibrarySource>('generated');

    // Custom Hooks
    const { height: windowHeight } = useWindowSize();
    const { imageUrls, numPages: imageNumPages, isImageMode } = useBookImages(selectedPdfState, currentPathState, currentSource);



    // Window Size State
    const [showHeader, setShowHeader] = useState(false);

    // Reader State
    const [isSpread, setIsSpread] = useState(true);
    const [direction, setDirection] = useState<ReadingDirection>('rtl');
    const [numPages, setNumPages] = useState<number>(0);

    // Page Navigation Hook
    const {
        pageNumber,
        setPageNumber,
        handleNext,
        handlePrev,
        resetPage
    } = useReaderNavigation({
        numPages,
        isSpread,
        direction,
        isActive: !!selectedPdfState
    });

    // Edit Mode State
    const [isEditMode, setIsEditMode] = useState(false);
    const [selectedPages, setSelectedPages] = useState<Set<number>>(new Set());

    // PDF Version for cache busting
    const [pdfVersion, setPdfVersion] = useState(0);

    // Image Preloading
    useImagePreloader(imageUrls, pageNumber - 1, 3); // Preload 3 pages ahead/behind

    // Update numPages when in image mode
    useEffect(() => {
        if (isImageMode) {
            setNumPages(imageNumPages);
        }
    }, [isImageMode, imageNumPages]);

    // Reset state when changing PDF
    useEffect(() => {
        setIsEditMode(false);
        setSelectedPages(new Set());
        setNumPages(0);
        resetPage();
    }, [selectedPdfState, resetPage]);

    // Fetch PDF list
    const fetchPdfs = useCallback(async () => {
        try {
            const data = await apiClient.get<any, any>(API_ENDPOINTS.PDFS, {
                params: {
                    path: currentPathState,
                    source: currentSource
                }
            });
            setPdfs(data.files);
            setDirectories(data.directories || []);
        } catch (e) {
            console.error(e);
        }
    }, [currentPathState, currentSource]);

    useEffect(() => {
        fetchPdfs();
    }, [fetchPdfs]);

    // Library Management
    const {
        isSelectionMode,
        selectedItems,
        isMoveDialogOpen,
        toggleSelectionMode,
        toggleSelectItem,
        createFolder,
        openMoveDialog,
        closeMoveDialog,
        handleMoveItems,
    } = useLibraryManagement({
        currentPath: currentPathState,
        currentSource: currentSource,
        onRefresh: fetchPdfs
    });

    // Sync URL params with state
    useEffect(() => {
        const path = searchParams.get('path') || "";
        const file = searchParams.get('file');

        if (path !== currentPathState) setCurrentPath(path);
        if (file !== selectedPdfState) setSelectedPdf(file);
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [searchParams]);

    // Navigation handlers
    const handleFolderClick = useCallback((dirName: string) => {
        const newPath = currentPathState ? `${currentPathState}/${dirName}` : dirName;
        setSearchParams({ path: newPath });
    }, [currentPathState, setSearchParams]);

    const handleUpClick = useCallback(() => {
        if (!currentPathState) return;
        const parts = currentPathState.split('/');
        parts.pop();
        const newPath = parts.join('/');

        const newParams = new URLSearchParams(searchParams);
        if (newPath) {
            newParams.set('path', newPath);
        } else {
            newParams.delete('path');
        }
        newParams.delete('file');
        setSearchParams(newParams);
    }, [currentPathState, searchParams, setSearchParams]);

    const handlePdfClick = useCallback((pdfName: string) => {
        const newParams = new URLSearchParams(searchParams);
        newParams.set('file', pdfName);
        setSearchParams(newParams);
    }, [searchParams, setSearchParams]);

    const handleSourceChange = useCallback((source: LibrarySource) => {
        setCurrentSource(source);
        setCurrentPath(""); // Reset path to root when switching sources
        setSearchParams({}); // Clear URL params
    }, [setSearchParams]);

    const onDocumentLoadSuccess = useCallback(({ numPages }: { numPages: number }) => {
        setNumPages(numPages);
    }, []);

    const closeReader = useCallback(() => {
        const newParams = new URLSearchParams(searchParams);
        newParams.delete('file');
        setSearchParams(newParams);
        resetPage();
        setIsEditMode(false);
        setSelectedPages(new Set());
    }, [searchParams, setSearchParams, resetPage]);

    const toggleDirection = useCallback(() => {
        setDirection(prev => prev === 'rtl' ? 'ltr' : 'rtl');
        resetPage();
    }, [resetPage]);

    // Edit Mode Logic
    const togglePageSelection = useCallback((pNum: number, e: React.MouseEvent) => {
        e.stopPropagation();
        setSelectedPages(prev => {
            const newSelected = new Set(prev);
            if (newSelected.has(pNum)) {
                newSelected.delete(pNum);
            } else {
                newSelected.add(pNum);
            }
            return newSelected;
        });
    }, []);

    const handleDeletePages = useCallback(async () => {
        if (selectedPages.size === 0 || !selectedPdfState) return;

        if (!confirm(`Are you sure you want to delete ${selectedPages.size} pages? This action cannot be undone.`)) {
            return;
        }

        try {
            const pageIndices = Array.from(selectedPages).map(p => p - 1);
            const data = await apiClient.post<any, any>(
                API_ENDPOINTS.DELETE_PAGES(selectedPdfState, currentPathState, currentSource),
                { page_indices: pageIndices }
            );

            setIsEditMode(false);
            setSelectedPages(new Set());
            setPdfVersion(v => v + 1);

            if (pageNumber > data.total_pages) {
                setPageNumber(Math.max(1, data.total_pages));
            }
        } catch (e: any) {
            alert(e.message);
        }
    }, [selectedPages, selectedPdfState, currentPathState, pageNumber, currentSource]);

    const handleToggleEditMode = useCallback(() => {
        setIsEditMode(prev => !prev);
        setSelectedPages(new Set());
    }, []);

    // Helper to render page via PageRenderer component
    const renderPageItem = (pNum: number, side: 'left' | 'right' | 'single') => {
        return (
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
    };

    // Render spread pages
    const renderSpreadPages = () => {
        const p1 = pageNumber;
        const p2 = pageNumber + 1;

        if (direction === 'rtl') {
            return (
                <>
                    {renderPageItem(p2, 'left')}
                    {renderPageItem(p1, 'right')}
                </>
            );
        } else {
            return (
                <>
                    {renderPageItem(p1, 'left')}
                    {renderPageItem(p2, 'right')}
                </>
            );
        }
    };

    return (
        <div className="h-full flex flex-col relative">
            {/* Header Trigger Zone */}
            {selectedPdfState && (
                <div
                    className="fixed top-0 left-0 right-0 h-16 z-40"
                    onMouseEnter={() => setShowHeader(true)}
                />
            )}

            {/* Header */}
            {selectedPdfState ? (
                <ReaderHeader
                    selectedPdf={selectedPdfState}
                    direction={direction}
                    isSpread={isSpread}
                    pageNumber={pageNumber}
                    numPages={numPages}
                    isEditMode={isEditMode}
                    selectedPagesCount={selectedPages.size}
                    showHeader={showHeader}
                    onClose={closeReader}
                    onToggleDirection={toggleDirection}
                    onToggleSpread={() => setIsSpread(!isSpread)}
                    onToggleEditMode={handleToggleEditMode}
                    onDeletePages={handleDeletePages}
                    onMouseLeave={() => setShowHeader(false)}
                />
            ) : (
                <LibraryHeader
                    currentPath={currentPathState}
                    currentSource={currentSource}
                    isSelectionMode={isSelectionMode}
                    selectedCount={selectedItems.size}
                    onUpClick={handleUpClick}
                    onSourceChange={handleSourceChange}
                    onToggleSelectionMode={toggleSelectionMode}
                    onCreateFolder={createFolder}
                    onMoveSelected={openMoveDialog}
                />
            )}

            {/* Move Dialog */}
            <MoveDialog
                open={isMoveDialogOpen}
                onClose={closeMoveDialog}
                onMove={handleMoveItems}
                currentSource={currentSource}
                sourcePath={currentPathState}
            />

            {/* Content */}
            <div className="flex-1 bg-gray-100 overflow-auto relative">
                {!selectedPdfState ? (
                    <div className="w-full h-full p-6 overflow-y-auto">
                        <FolderGrid
                            directories={directories}
                            onFolderClick={handleFolderClick}
                            isSelectionMode={isSelectionMode}
                            selectedItems={selectedItems}
                            onToggleSelect={toggleSelectItem}
                        />
                        <PdfGrid
                            pdfs={pdfs}
                            onPdfClick={handlePdfClick}
                            isSelectionMode={isSelectionMode}
                            selectedItems={selectedItems}
                            onToggleSelect={toggleSelectItem}
                        />
                    </div>
                ) : (
                    // Reader View
                    <div
                        className="min-h-full flex items-center justify-center p-4 w-fit mx-auto"
                        onClick={handleNext}
                    >
                        {isImageMode ? (
                            // Image Mode Render
                            <div className="flex gap-0 shadow-2xl justify-center bg-gray-900">
                                {isSpread ? renderSpreadPages() : renderPageItem(pageNumber, 'single')}
                            </div>
                        ) : (
                            // PDF Mode Render
                            <Document
                                file={buildStaticUrl(STATIC_PATHS.PDF(currentPathState, selectedPdfState, currentSource, pdfVersion))}
                                onLoadSuccess={onDocumentLoadSuccess}
                                className="flex justify-center"
                                loading={
                                    <div className="flex items-center justify-center h-96">
                                        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
                                    </div>
                                }
                            >
                                <div className="flex shadow-2xl">
                                    {isSpread ? renderSpreadPages() : renderPageItem(pageNumber, 'single')}
                                </div>
                            </Document>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}
