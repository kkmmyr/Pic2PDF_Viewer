import { useEffect, useCallback } from 'react';
import { LibraryPanel, ReaderPanel } from '../components/viewer';
import { useUrlState } from '../hooks/useUrlState';
import { useCurrentSource } from '../hooks/useCurrentSource';
import { useLibraryStore } from '../stores/libraryStore';

function LibraryView() {
    const { currentPath, selectedPdf, navigateUp, selectPdf, clearPdf } = useUrlState();
    const currentSource = useCurrentSource();
    const { setContext, fetchPdfs, bumpVersion, version } = useLibraryStore();

    // Sync URL-derived context to store, then fetch pdfs.
    // setContext is synchronous so fetchPdfs reads the updated path/source immediately.
    useEffect(() => {
        setContext(currentPath, currentSource);
        void fetchPdfs();
    }, [currentPath, currentSource, setContext, fetchPdfs]);

    // Re-fetch when an operation (rename, thumbnail regen, etc.) bumps the version.
    // Skip version === 0 to avoid double-fetch on first mount.
    useEffect(() => {
        if (version > 0) void fetchPdfs();
    }, [version, fetchPdfs]);

    const handlePdfClick = useCallback(
        (name: string) => selectPdf(name, currentPath),
        [selectPdf, currentPath],
    );

    const handleUpClick = useCallback(
        () => navigateUp(currentPath),
        [navigateUp, currentPath],
    );

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
                    onPdfUpdated={bumpVersion}
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
