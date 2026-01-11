import { useState, useCallback } from 'react';
import { LibrarySource } from '../types';
import { buildApiUrl, API_ENDPOINTS } from '../config/api';

interface UseLibraryManagementProps {
    currentPath: string;
    currentSource: LibrarySource;
    onRefresh: () => void;
}

export function useLibraryManagement({ currentPath, currentSource, onRefresh }: UseLibraryManagementProps) {
    const [isSelectionMode, setIsSelectionMode] = useState(false);
    const [selectedItems, setSelectedItems] = useState<Set<string>>(new Set());
    const [isMoveDialogOpen, setIsMoveDialogOpen] = useState(false);

    const toggleSelectionMode = useCallback(() => {
        setIsSelectionMode(prev => {
            if (prev) {
                setSelectedItems(new Set());
            }
            return !prev;
        });
    }, []);

    const toggleSelectItem = useCallback((name: string) => {
        setSelectedItems(prev => {
            const next = new Set(prev);
            if (next.has(name)) {
                next.delete(name);
            } else {
                next.add(name);
            }
            return next;
        });
    }, []);

    const createFolder = useCallback(async () => {
        const name = prompt("フォルダ名を入力してください");
        if (!name) return;

        try {
            const res = await fetch(buildApiUrl(API_ENDPOINTS.DIRECTORIES), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    path: currentPath,
                    name,
                    source: currentSource
                })
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Failed to create directory');
            }

            onRefresh();
        } catch (e: any) {
            alert(e.message);
        }
    }, [currentPath, currentSource, onRefresh]);

    const openMoveDialog = useCallback(() => {
        if (selectedItems.size === 0) return;
        setIsMoveDialogOpen(true);
    }, [selectedItems]);

    const closeMoveDialog = useCallback(() => {
        setIsMoveDialogOpen(false);
    }, []);

    const handleMoveItems = useCallback(async (destination: string) => {
        if (selectedItems.size === 0) return;

        try {
            const res = await fetch(buildApiUrl(API_ENDPOINTS.MOVE), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    items: Array.from(selectedItems),
                    source_path: currentPath,
                    destination_path: destination,
                    source: currentSource
                })
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Failed to move items');
            }

            // Success
            setIsMoveDialogOpen(false);
            setIsSelectionMode(false);
            setSelectedItems(new Set());
            onRefresh();
        } catch (e: any) {
            alert(e.message);
        }
    }, [selectedItems, currentPath, currentSource, onRefresh]);

    return {
        isSelectionMode,
        selectedItems,
        isMoveDialogOpen,
        toggleSelectionMode,
        toggleSelectItem,
        createFolder,
        openMoveDialog,
        closeMoveDialog,
        handleMoveItems,
    };
}
