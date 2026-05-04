import { LibraryProvider, useLibraryContext } from '../contexts/LibraryContext';
import { LibraryPanel, ReaderPanel } from '../components/viewer';

function LibraryView() {
    const {
        selectedPdf, currentPath, currentSource,
        onClosePdf, onPdfUpdated, onPdfClick,
    } = useLibraryContext();

    return (
        <div className="h-full flex flex-col relative">
            {/* 常にマウントして display:none で隠すことでスクロール位置を保持する */}
            <div className={selectedPdf ? 'hidden' : 'contents'}>
                <LibraryPanel />
            </div>
            {selectedPdf && (
                <ReaderPanel
                    selectedPdf={selectedPdf}
                    currentPath={currentPath}
                    currentSource={currentSource}
                    onPdfUpdated={onPdfUpdated}
                    onClose={onClosePdf}
                    onSelectPdf={onPdfClick}
                />
            )}
        </div>
    );
}

export default function ViewerPage() {
    return (
        <LibraryProvider>
            <LibraryView />
        </LibraryProvider>
    );
}
