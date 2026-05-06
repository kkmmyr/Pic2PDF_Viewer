import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import type { PdfFile, LibrarySource } from '../types';
import { API_ENDPOINTS } from '../config/api';
import apiClient from '../config/api_client';
import { useUrlState } from '../hooks/useUrlState';
import { useLibraryManagement } from '../hooks';

interface LibraryContextValue {
    // 状態
    pdfs: PdfFile[];
    selectedPdf: string | null;
    currentPath: string;
    currentSource: LibrarySource;
    isSelectionMode: boolean;
    selectedItems: Set<string>;
    renameTarget: { name: string; isFolder: boolean } | null;
    // ナビゲーション
    onPdfClick: (name: string) => void;
    onUpClick: () => void;
    onSourceChange: (source: LibrarySource) => void;
    onClosePdf: () => void;
    onPdfUpdated: () => void;
    // 選択モード
    onToggleSelectionMode: () => void;
    /** 選択モードを終了して選択中アイテムも空にする（一括操作の成功時に呼ぶ） */
    onClearSelection: () => void;
    onToggleSelect: (item: string) => void;
    onBulkSelect: (names: string[], select: boolean) => void;
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
    const { currentPath, selectedPdf, currentSource, navigateUp, selectPdf, clearPdf, setSource } =
        useUrlState();

    const [pdfs, setPdfs] = useState<PdfFile[]>([]);
    const [libraryVersion, setLibraryVersion] = useState(0);

    const fetchPdfs = useCallback(async () => {
        try {
            const data = await apiClient.get<unknown, { files: PdfFile[] }>(API_ENDPOINTS.PDFS, {
                params: { path: currentPath, source: currentSource },
            });
            setPdfs(data.files);
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
        renameTarget,
        toggleSelectionMode,
        clearSelection,
        toggleSelectItem,
        bulkSelectItems,
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
        selectedPdf,
        currentPath,
        currentSource,
        isSelectionMode,
        selectedItems,
        renameTarget,
        onPdfClick: (name) => selectPdf(name, currentPath, currentSource),
        onUpClick: () => navigateUp(currentPath, currentSource),
        onSourceChange: setSource,
        onClosePdf: () => clearPdf(currentPath, currentSource),
        onPdfUpdated: () => setLibraryVersion((v) => v + 1),
        onToggleSelectionMode: toggleSelectionMode,
        onClearSelection: clearSelection,
        onToggleSelect: toggleSelectItem,
        onBulkSelect: bulkSelectItems,
        onOpenRename: openRenameDialog,
        onCloseRename: closeRenameDialog,
        onRenameItem: handleRename,
        onRefresh: fetchPdfs,
    };

    return <LibraryContext.Provider value={value}>{children}</LibraryContext.Provider>;
}
