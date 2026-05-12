import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';

export function useUrlState() {
    const [searchParams, setSearchParams] = useSearchParams();

    const currentPath = searchParams.get('path') || '';
    const selectedPdf = searchParams.get('file') || null;

    const navigateIntoFolder = useCallback(
        (dirName: string, basePath: string) => {
            const newPath = basePath ? `${basePath}/${dirName}` : dirName;
            setSearchParams({ path: newPath });
        },
        [setSearchParams],
    );

    const navigateUp = useCallback(
        (currentPath: string) => {
            if (!currentPath) return;
            const parts = currentPath.split('/');
            parts.pop();
            const newPath = parts.join('/');
            const newParams = new URLSearchParams();
            if (newPath) newParams.set('path', newPath);
            setSearchParams(newParams);
        },
        [setSearchParams],
    );

    const selectPdf = useCallback(
        (pdfName: string, currentPath: string) => {
            const params: Record<string, string> = { file: pdfName };
            if (currentPath) params.path = currentPath;
            setSearchParams(params);
        },
        [setSearchParams],
    );

    const clearPdf = useCallback(
        (currentPath: string) => {
            const newParams = new URLSearchParams();
            if (currentPath) newParams.set('path', currentPath);
            setSearchParams(newParams);
        },
        [setSearchParams],
    );

    return {
        currentPath,
        selectedPdf,
        navigateIntoFolder,
        navigateUp,
        selectPdf,
        clearPdf,
    };
}
