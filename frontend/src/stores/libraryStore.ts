import { create } from 'zustand';
import type { LibrarySource } from '@/types';

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
}

export const useLibraryStore = create<LibraryState & LibraryActions>((set) => ({
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
}));
