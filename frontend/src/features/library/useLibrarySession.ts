import { useEffect, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useUrlState } from '@/hooks/library/useUrlState';
import { useCurrentSource } from '@/hooks/useCurrentSource';
import { useLibraryStore } from '@/stores/libraryStore';
import { pdfQueryKey } from '@/hooks/library/useLibraryPdfs';

/** URLを正本とする一覧と読書sessionの接続。 */
export function useLibrarySession() {
    const { currentPath, selectedPdf, initialPage, navigateUp, selectPdf, clearPdf } =
        useUrlState();
    const currentSource = useCurrentSource();
    const { setContext } = useLibraryStore();
    const queryClient = useQueryClient();

    // URL 由来のコンテキストをストアに同期する。
    // PDF 一覧の取得は useLibraryPanel 内の useLibraryPdfs が担う。
    useEffect(() => {
        setContext(currentPath, currentSource);
    }, [currentPath, currentSource, setContext]);

    const handlePdfClick = useCallback(
        (name: string) => selectPdf(name, currentPath),
        [selectPdf, currentPath],
    );

    const handleUpClick = useCallback(() => navigateUp(currentPath), [navigateUp, currentPath]);

    const handlePdfUpdated = useCallback(() => {
        void queryClient.invalidateQueries({ queryKey: pdfQueryKey(currentPath, currentSource) });
    }, [queryClient, currentPath, currentSource]);

    return {
        currentPath,
        currentSource,
        selectedPdf,
        initialPage,
        clearPdf,
        handlePdfClick,
        handleUpClick,
        handlePdfUpdated,
    };
}
