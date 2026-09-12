import { LibraryPanel } from '@/components/library';
import { ReaderPanel } from '@/features/reader';
import { useLibrarySession } from '@/features/library/useLibrarySession';

/** 一覧の状態を保持したまま読書画面を開閉する。 */
export function LibraryWorkspace() {
    const {
        currentPath,
        currentSource,
        selectedPdf,
        initialPage,
        clearPdf,
        handlePdfClick,
        handleUpClick,
        handlePdfUpdated,
    } = useLibrarySession();
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
                    initialPage={initialPage}
                    onPdfUpdated={handlePdfUpdated}
                    onClose={clearPdf}
                    onSelectPdf={handlePdfClick}
                />
            )}
        </div>
    );
}
