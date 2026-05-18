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
            setSearchParams((prev) => {
                const next = new URLSearchParams(prev);
                next.set('file', pdfName);
                if (currentPath) next.set('path', currentPath);
                else next.delete('path');
                return next;
            });
        },
        [setSearchParams],
    );

    const clearPdf = useCallback(() => {
        setSearchParams((prev) => {
            const next = new URLSearchParams(prev);
            next.delete('file');
            return next;
        });
    }, [setSearchParams]);

    return {
        currentPath,
        selectedPdf,
        navigateIntoFolder,
        navigateUp,
        selectPdf,
        clearPdf,
    };
}
