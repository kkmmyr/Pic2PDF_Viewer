import { create } from 'zustand';
import type { PdfFile, LibrarySource } from '../types';
import apiClient from '../config/api_client';
import { API_ENDPOINTS } from '../config/api';

interface LibraryState {
    pdfs: PdfFile[];
    currentPath: string;
    currentSource: LibrarySource;
    version: number;
    isSelectionMode: boolean;
    selectedItems: Set<string>;
    renameTarget: { name: string; isFolder: boolean } | null;
}

interface LibraryActions {
    fetchPdfs: () => Promise<void>;
    setContext: (path: string, source: LibrarySource) => void;
    bumpVersion: () => void;
    toggleSelectionMode: () => void;
    clearSelection: () => void;
    toggleSelectItem: (name: string) => void;
    bulkSelectItems: (names: string[], select: boolean) => void;
    openRenameDialog: (name: string, isFolder?: boolean) => void;
    closeRenameDialog: () => void;
    handleRename: (newName: string) => Promise<void>;
}

export const useLibraryStore = create<LibraryState & LibraryActions>((set, get) => ({
    pdfs: [],
    currentPath: '',
    currentSource: 'doujin',
    version: 0,
    isSelectionMode: false,
    selectedItems: new Set(),
    renameTarget: null,

    fetchPdfs: async () => {
        const { currentPath, currentSource } = get();
        try {
            const data = await apiClient.get<unknown, { files: PdfFile[] }>(API_ENDPOINTS.PDFS, {
                params: { path: currentPath, source: currentSource },
            });
            set({ pdfs: data.files });
        } catch {
            // ignore fetch errors silently
        }
    },

    setContext: (path, source) => set({ currentPath: path, currentSource: source }),

    bumpVersion: () => set((s) => ({ version: s.version + 1 })),

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
        get().bumpVersion();
    },
}));
