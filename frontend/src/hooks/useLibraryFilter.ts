import { useMemo } from 'react';
import type { PdfFile, BookMetaMap } from '../types';

interface UseLibraryFilterParams {
    pdfs: PdfFile[];
    directories: string[];
    searchText: string;
    authorFilter: string;
    currentPath: string;
    meta: BookMetaMap;
}

function getAuthorsFromMeta(meta: BookMetaMap, path: string, name: string): string[] {
    const key = path ? `${path}/${name}` : name;
    return meta[key]?.authors ?? [];
}

export function useLibraryFilter({
    pdfs,
    directories,
    searchText,
    authorFilter,
    currentPath,
    meta,
}: UseLibraryFilterParams) {
    const filteredPdfs = useMemo(() => {
        let result = pdfs;

        const trimmed = searchText.trim();
        if (trimmed) {
            const lower = trimmed.toLowerCase();
            result = result.filter(p =>
                p.name.toLowerCase().includes(lower) ||
                getAuthorsFromMeta(meta, currentPath, p.name).some(a => a.toLowerCase().includes(lower))
            );
        }

        if (authorFilter) {
            result = result.filter(p =>
                getAuthorsFromMeta(meta, currentPath, p.name).includes(authorFilter)
            );
        }

        return result;
    }, [pdfs, searchText, authorFilter, currentPath, meta]);

    const filteredDirs = useMemo(() => {
        const trimmed = searchText.trim();
        if (!trimmed) return directories;
        const lower = trimmed.toLowerCase();
        return directories.filter(d => d.toLowerCase().includes(lower));
    }, [directories, searchText]);

    return { filteredPdfs, filteredDirs };
}
