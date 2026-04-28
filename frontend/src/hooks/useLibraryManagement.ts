import { useState, useCallback } from 'react';
import type { LibrarySource } from '../types';
import { API_ENDPOINTS } from '../config/api';
import apiClient from '../config/api_client';

interface UseLibraryManagementProps {
    currentPath: string;
    currentSource: LibrarySource;
    onRefresh: () => void;
}

export function useLibraryManagement({ currentPath, currentSource, onRefresh }: UseLibraryManagementProps) {
    const [isSelectionMode, setIsSelectionMode] = useState(false);
    const [selectedItems, setSelectedItems] = useState<Set<string>>(new Set());
    const [isMoveDialogOpen, setIsMoveDialogOpen] = useState(false);
    const [isCreateFolderOpen, setIsCreateFolderOpen] = useState(false);
    const [renameTarget, setRenameTarget] = useState<{ name: string; isFolder: boolean } | null>(null);

    const toggleSelectionMode = useCallback(() => {
        setIsSelectionMode(prev => {
            if (prev) setSelectedItems(new Set());
            return !prev;
        });
    }, []);

    /**
     * 選択モードを終了して選択中アイテムも空にする。一括操作の成功時に
     * カードからチェックボックスが消えて通常表示に戻すため呼ぶ。
     */
    const clearSelection = useCallback(() => {
        setIsSelectionMode(false);
        setSelectedItems(new Set());
    }, []);

    const toggleSelectItem = useCallback((name: string) => {
        setSelectedItems(prev => {
            const next = new Set(prev);
            if (next.has(name)) next.delete(name);
            else next.add(name);
            return next;
        });
    }, []);

    // フォルダ作成ダイアログの開閉
    const openCreateFolderDialog = useCallback(() => setIsCreateFolderOpen(true), []);
    const closeCreateFolderDialog = useCallback(() => setIsCreateFolderOpen(false), []);

    // 実際のフォルダ作成 API 呼び出し（CreateFolderDialog から名前を受け取る）
    const handleCreateFolder = useCallback(async (name: string) => {
        await apiClient.post(API_ENDPOINTS.DIRECTORIES, {
            path: currentPath,
            name,
            source: currentSource,
        });
        onRefresh();
    }, [currentPath, currentSource, onRefresh]);

    const openMoveDialog = useCallback(() => {
        if (selectedItems.size === 0) return;
        setIsMoveDialogOpen(true);
    }, [selectedItems]);

    const closeMoveDialog = useCallback(() => setIsMoveDialogOpen(false), []);

    const handleMoveItems = useCallback(async (destination: string) => {
        if (selectedItems.size === 0) return;

        await apiClient.post(API_ENDPOINTS.MOVE, {
            items: Array.from(selectedItems),
            source_path: currentPath,
            destination_path: destination,
            source: currentSource,
        });

        setIsMoveDialogOpen(false);
        setIsSelectionMode(false);
        setSelectedItems(new Set());
        onRefresh();
    }, [selectedItems, currentPath, currentSource, onRefresh]);

    const openRenameDialog = useCallback((name: string, isFolder = false) => setRenameTarget({ name, isFolder }), []);
    const closeRenameDialog = useCallback(() => setRenameTarget(null), []);

    const handleRename = useCallback(async (newName: string) => {
        if (!renameTarget) return;
        await apiClient.patch(API_ENDPOINTS.RENAME, {
            path: currentPath,
            old_name: renameTarget.name,
            new_name: newName,
            source: currentSource,
            is_folder: renameTarget.isFolder,
        });
        setRenameTarget(null);
        onRefresh();
    }, [renameTarget, currentPath, currentSource, onRefresh]);

    return {
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
    };
}
