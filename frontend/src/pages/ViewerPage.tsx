import { useState, useEffect, useCallback } from 'react';
import { pdfjs } from 'react-pdf';

import type { PdfFile, LibrarySource } from '../types';
import { API_ENDPOINTS } from '../config/api';
import apiClient from '../config/api_client';
import { useUrlState } from '../hooks/useUrlState';
import { useLibraryManagement } from '../hooks';
import { LibraryPanel, ReaderPanel } from '../components/viewer';

pdfjs.GlobalWorkerOptions.workerSrc =
    `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

/**
 * ViewerPage — ライブラリ閲覧 & PDF リーダーのルートコンポーネント。
 *
 * 責務:
 * - URL パラメータとの同期 (useUrlState)
 * - PDF 一覧のフェッチ
 * - ライブラリ管理 (useLibraryManagement)
 * - LibraryPanel / ReaderPanel の切り替え表示
 *
 * Reader 内の状態 (ページ番号・編集モード等) は ReaderPanel が管理する。
 */
export default function ViewerPage() {
    const {
        currentPath,
        selectedPdf,
        navigateIntoFolder,
        navigateUp,
        selectPdf,
        clearPdf,
        resetAll,
    } = useUrlState();

    const [pdfs, setPdfs] = useState<PdfFile[]>([]);
    const [directories, setDirectories] = useState<string[]>([]);
    const [currentSource, setCurrentSource] = useState<LibrarySource>('generated');
    // PDF 一覧の再取得トリガー（ページ削除後などに使用）
    const [libraryVersion, setLibraryVersion] = useState(0);

    // PDF 一覧を取得
    const fetchPdfs = useCallback(async () => {
        try {
            const data = await apiClient.get<unknown, { files: PdfFile[]; directories: string[] }>(
                API_ENDPOINTS.PDFS,
                { params: { path: currentPath, source: currentSource } }
            );
            setPdfs(data.files);
            setDirectories(data.directories ?? []);
        } catch (e) {
            console.error(e);
        }
    }, [currentPath, currentSource]);

    useEffect(() => {
        fetchPdfs();
    }, [fetchPdfs, libraryVersion]);

    // ライブラリ管理（フォルダ作成・移動・リネーム）
    const {
        isSelectionMode,
        selectedItems,
        isMoveDialogOpen,
        isCreateFolderOpen,
        renameTarget,
        toggleSelectionMode,
        toggleSelectItem,
        openCreateFolderDialog,
        closeCreateFolderDialog,
        handleCreateFolder,
        openMoveDialog,
        closeMoveDialog,
        handleMoveItems,
        openRenameDialog,
        closeRenameDialog,
        handleRename,
    } = useLibraryManagement({
        currentPath,
        currentSource,
        onRefresh: fetchPdfs,
    });

    // ソース切り替え
    const handleSourceChange = useCallback((source: LibrarySource) => {
        setCurrentSource(source);
        resetAll();
    }, [resetAll]);

    return (
        <div className="h-full flex flex-col relative">
            {selectedPdf ? (
                <ReaderPanel
                    selectedPdf={selectedPdf}
                    currentPath={currentPath}
                    currentSource={currentSource}
                    onPdfUpdated={() => setLibraryVersion(v => v + 1)}
                    onClose={() => clearPdf(currentPath)}
                />
            ) : (
                <LibraryPanel
                    pdfs={pdfs}
                    directories={directories}
                    currentPath={currentPath}
                    currentSource={currentSource}
                    isSelectionMode={isSelectionMode}
                    selectedItems={selectedItems}
                    isMoveDialogOpen={isMoveDialogOpen}
                    isCreateFolderOpen={isCreateFolderOpen}
                    renameTarget={renameTarget}
                    onPdfClick={(name) => selectPdf(name, currentPath)}
                    onFolderClick={(dir) => navigateIntoFolder(dir, currentPath)}
                    onUpClick={() => navigateUp(currentPath)}
                    onSourceChange={handleSourceChange}
                    onToggleSelectionMode={toggleSelectionMode}
                    onToggleSelect={toggleSelectItem}
                    onOpenCreateFolder={openCreateFolderDialog}
                    onCloseCreateFolder={closeCreateFolderDialog}
                    onCreateFolder={handleCreateFolder}
                    onMoveSelected={openMoveDialog}
                    onCloseMoveDialog={closeMoveDialog}
                    onMoveItems={handleMoveItems}
                    onOpenRename={openRenameDialog}
                    onCloseRename={closeRenameDialog}
                    onRenameItem={handleRename}
                />
            )}
        </div>
    );
}
