import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import type { PdfFile, LibrarySource } from '../types';
import { API_ENDPOINTS } from '../config/api';
import apiClient from '../config/api_client';
import { useUrlState } from '../hooks/useUrlState';
import { useLibraryManagement } from '../hooks';

interface LibraryContextValue {
    // 状態
    pdfs: PdfFile[];
    directories: string[];
    selectedPdf: string | null;
    currentPath: string;
    currentSource: LibrarySource;
    isSelectionMode: boolean;
    selectedItems: Set<string>;
    isMoveDialogOpen: boolean;
    isCreateFolderOpen: boolean;
    renameTarget: { name: string; isFolder: boolean } | null;
    // ナビゲーション
    onPdfClick: (name: string) => void;
    onFolderClick: (name: string) => void;
    onUpClick: () => void;
    onSourceChange: (source: LibrarySource) => void;
    onClosePdf: () => void;
    onPdfUpdated: () => void;
    // 選択モード
    onToggleSelectionMode: () => void;
    /** 選択モードを終了して選択中アイテムも空にする（一括操作の成功時に呼ぶ） */
    onClearSelection: () => void;
    onToggleSelect: (item: string) => void;
    // フォルダ作成
    onOpenCreateFolder: () => void;
    onCloseCreateFolder: () => void;
    onCreateFolder: (name: string) => Promise<void>;
    // 移動
    onMoveSelected: () => void;
    onCloseMoveDialog: () => void;
    onMoveItems: (destination: string) => Promise<void>;
    // リネーム
    onOpenRename: (name: string, isFolder?: boolean) => void;
    onCloseRename: () => void;
    onRenameItem: (newName: string) => Promise<void>;
    // 更新
    onRefresh: () => void;
}

const LibraryContext = createContext<LibraryContextValue | null>(null);

export function useLibraryContext(): LibraryContextValue {
    const ctx = useContext(LibraryContext);
    if (!ctx) throw new Error('useLibraryContext must be used within LibraryProvider');
    return ctx;
}

export function LibraryProvider({ children }: { children: ReactNode }) {
    const {
        currentPath,
        selectedPdf,
        currentSource,
        navigateIntoFolder,
        navigateUp,
        selectPdf,
        clearPdf,
        setSource,
    } = useUrlState();

    const [pdfs, setPdfs] = useState<PdfFile[]>([]);
    const [directories, setDirectories] = useState<string[]>([]);
    const [libraryVersion, setLibraryVersion] = useState(0);

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

    const {
        isSelectionMode,
        selectedItems,
        isMoveDialogOpen,
        isCreateFolderOpen,
        renameTarget,
        toggleSelectionMode,
        clearSelection,
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

    const value: LibraryContextValue = {
        pdfs,
        directories,
        selectedPdf,
        currentPath,
        currentSource,
        isSelectionMode,
        selectedItems,
        isMoveDialogOpen,
        isCreateFolderOpen,
        renameTarget,
        onPdfClick: (name) => selectPdf(name, currentPath, currentSource),
        onFolderClick: (dir) => navigateIntoFolder(dir, currentPath, currentSource),
        onUpClick: () => navigateUp(currentPath, currentSource),
        onSourceChange: setSource,
        onClosePdf: () => clearPdf(currentPath, currentSource),
        onPdfUpdated: () => setLibraryVersion(v => v + 1),
        onToggleSelectionMode: toggleSelectionMode,
        onClearSelection: clearSelection,
        onToggleSelect: toggleSelectItem,
        onOpenCreateFolder: openCreateFolderDialog,
        onCloseCreateFolder: closeCreateFolderDialog,
        onCreateFolder: handleCreateFolder,
        onMoveSelected: openMoveDialog,
        onCloseMoveDialog: closeMoveDialog,
        onMoveItems: handleMoveItems,
        onOpenRename: openRenameDialog,
        onCloseRename: closeRenameDialog,
        onRenameItem: handleRename,
        onRefresh: fetchPdfs,
    };

    return (
        <LibraryContext.Provider value={value}>
            {children}
        </LibraryContext.Provider>
    );
}
