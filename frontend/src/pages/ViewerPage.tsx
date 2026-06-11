import { useEffect, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { LibraryPanel } from '@/components/library';
import { ReaderPanel } from '@/components/reader';
import { useUrlState } from '@/hooks/library/useUrlState';
import { useCurrentSource } from '@/hooks/useCurrentSource';
import { useLibraryStore } from '@/stores/libraryStore';
import { pdfQueryKey } from '@/hooks/library/useLibraryPdfs';

function LibraryView() {
    const { currentPath, selectedPdf, navigateUp, selectPdf, clearPdf } = useUrlState();
    const currentSource = useCurrentSource();
    const { setContext } = useLibraryStore();
    const queryClient = useQueryClient();

    // URL 由来のコンテキストをストアに同期する。
    // PDF 一覧の取得は useLibraryPanel 内の useLibraryPdfs が担う。
    useEffect(() => {
        setContext(currentPath, currentSource);
    }, [currentPath, currentSource, setContext]);

    const handlePdfClick = useCallback(
        (name: string) => selectPdf(name, currentPath),
        [selectPdf, currentPath],
    );

    const handleUpClick = useCallback(() => navigateUp(currentPath), [navigateUp, currentPath]);

    const handlePdfUpdated = useCallback(() => {
        void queryClient.invalidateQueries({ queryKey: pdfQueryKey(currentPath, currentSource) });
    }, [queryClient, currentPath, currentSource]);

    return (
        <div className="h-full flex flex-col relative">
            {/* 常にマウントして display:none で隠すことでスクロール位置を保持する */}
            <div className={selectedPdf ? 'hidden' : 'contents'}>
                <LibraryPanel onPdfClick={handlePdfClick} onUpClick={handleUpClick} />
            </div>
            {selectedPdf && (
                <ReaderPanel
                    selectedPdf={selectedPdf}
                    currentPath={currentPath}
                    currentSource={currentSource}
                    onPdfUpdated={handlePdfUpdated}
                    onClose={clearPdf}
                    onSelectPdf={handlePdfClick}
                />
            )}
        </div>
    );
}

export default function ViewerPage() {
    return <LibraryView />;
}
