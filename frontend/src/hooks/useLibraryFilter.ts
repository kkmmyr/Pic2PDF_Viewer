import { useMemo } from 'react';
import type { PdfFile } from '../types';

interface UseLibraryFilterParams {
    pdfs: PdfFile[];
    directories: string[];
    searchText: string;
    authorFilter: string;
    currentPath: string;
    getAuthors: (path: string, name: string) => string[];
}

export function useLibraryFilter({
    pdfs,
    directories,
    searchText,
    authorFilter,
    currentPath,
    getAuthors,
}: UseLibraryFilterParams) {
    const filteredPdfs = useMemo(() => {
        let result = pdfs;

        if (searchText.trim()) {
            const lower = searchText.toLowerCase();
            result = result.filter(p =>
                p.name.toLowerCase().includes(lower) ||
                getAuthors(currentPath, p.name).some(a => a.toLowerCase().includes(lower))
            );
        }

        if (authorFilter) {
            result = result.filter(p =>
                getAuthors(currentPath, p.name).includes(authorFilter)
            );
        }

        return result;
    }, [pdfs, searchText, authorFilter, currentPath, getAuthors]);

    const filteredDirs = useMemo(() => {
        if (!searchText.trim()) return directories;
        const lower = searchText.toLowerCase();
        return directories.filter(d => d.toLowerCase().includes(lower));
    }, [directories, searchText]);

    return { filteredPdfs, filteredDirs };
}
