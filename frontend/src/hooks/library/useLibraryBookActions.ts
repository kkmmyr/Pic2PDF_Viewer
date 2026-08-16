import { useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { API_ENDPOINTS } from '@/config/api';
import apiClient from '@/config/api_client';
import type { LibrarySource } from '@/types';

import { pdfQueryKey } from './useLibraryPdfs';

interface RenameTarget {
    name: string;
    isFolder: boolean;
}

interface LibraryBookActionsOptions {
    currentPath: string;
    currentSource: LibrarySource;
    renameTarget: RenameTarget | null;
    closeRenameDialog: () => void;
}

export function useLibraryBookActions({
    currentPath,
    currentSource,
    renameTarget,
    closeRenameDialog,
}: LibraryBookActionsOptions) {
    const queryClient = useQueryClient();
    const invalidatePdfs = useCallback(() => {
        void queryClient.invalidateQueries({ queryKey: pdfQueryKey(currentPath, currentSource) });
    }, [queryClient, currentPath, currentSource]);

    const handleRename = useCallback(
        async (newName: string) => {
            if (!renameTarget) return;
            await apiClient.patch(API_ENDPOINTS.RENAME, {
                path: currentPath,
                old_name: renameTarget.name,
                new_name: newName,
                source: currentSource,
                is_folder: renameTarget.isFolder,
            });
            closeRenameDialog();
            invalidatePdfs();
        },
        [renameTarget, currentPath, currentSource, closeRenameDialog, invalidatePdfs],
    );

    const handleRegenThumb = useCallback(
        async (name: string) => {
            await apiClient.post(API_ENDPOINTS.REGENERATE_THUMBNAIL, {
                path: currentPath,
                name,
                source: currentSource,
            });
            invalidatePdfs();
        },
        [currentPath, currentSource, invalidatePdfs],
    );

    return { handleRename, handleRegenThumb, invalidatePdfs };
}
