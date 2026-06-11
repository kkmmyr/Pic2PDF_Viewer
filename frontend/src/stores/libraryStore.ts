import { create } from 'zustand';
import type { LibrarySource } from '@/types';
import apiClient from '@/config/api_client';
import { API_ENDPOINTS } from '@/config/api';

interface LibraryState {
    currentPath: string;
    currentSource: LibrarySource;
    isSelectionMode: boolean;
    selectedItems: Set<string>;
    renameTarget: { name: string; isFolder: boolean } | null;
}

interface LibraryActions {
    setContext: (path: string, source: LibrarySource) => void;
    toggleSelectionMode: () => void;
    clearSelection: () => void;
    toggleSelectItem: (name: string) => void;
    bulkSelectItems: (names: string[], select: boolean) => void;
    openRenameDialog: (name: string, isFolder?: boolean) => void;
    closeRenameDialog: () => void;
    handleRename: (newName: string) => Promise<void>;
}

export const useLibraryStore = create<LibraryState & LibraryActions>((set, get) => ({
    currentPath: '',
    currentSource: 'doujin',
    isSelectionMode: false,
    selectedItems: new Set(),
    renameTarget: null,

    setContext: (path, source) => set({ currentPath: path, currentSource: source }),

    toggleSelectionMode: () =>
        set((s) => ({
            isSelectionMode: !s.isSelectionMode,
            selectedItems: s.isSelectionMode ? new Set() : s.selectedItems,
        })),

    clearSelection: () => set({ isSelectionMode: false, selectedItems: new Set() }),

    toggleSelectItem: (name) =>
        set((s) => {
            const next = new Set(s.selectedItems);
            if (next.has(name)) next.delete(name);
            else next.add(name);
            return { selectedItems: next };
        }),

    bulkSelectItems: (names, select) =>
        set((s) => {
            const next = new Set(s.selectedItems);
            names.forEach((n) => {
                if (select) next.add(n);
                else next.delete(n);
            });
            return { selectedItems: next };
        }),

    openRenameDialog: (name, isFolder = false) => set({ renameTarget: { name, isFolder } }),

    closeRenameDialog: () => set({ renameTarget: null }),

    handleRename: async (newName) => {
        const { renameTarget, currentPath, currentSource } = get();
        if (!renameTarget) return;
        await apiClient.patch(API_ENDPOINTS.RENAME, {
            path: currentPath,
            old_name: renameTarget.name,
            new_name: newName,
            source: currentSource,
            is_folder: renameTarget.isFolder,
        });
        set({ renameTarget: null });
        // リフレッシュは呼び出し元（useLibraryPanel）が invalidateQueries で実施する
    },
}));
