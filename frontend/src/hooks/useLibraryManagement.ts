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
    const [renameTarget, setRenameTarget] = useState<{ name: string; isFolder: boolean } | null>(null);

    const toggleSelectionMode = useCallback(() => {
        setIsSelectionMode(prev => {
            if (prev) setSelectedItems(new Set());
            return !prev;
        });
    }, []);

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

    const bulkSelectItems = useCallback((names: string[], select: boolean) => {
        setSelectedItems(prev => {
            const next = new Set(prev);
            names.forEach(n => {
                if (select) next.add(n);
                else next.delete(n);
            });
            return next;
        });
    }, []);

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
        renameTarget,
        toggleSelectionMode,
        clearSelection,
        toggleSelectItem,
        bulkSelectItems,
        openRenameDialog,
        closeRenameDialog,
        handleRename,
    };
}
