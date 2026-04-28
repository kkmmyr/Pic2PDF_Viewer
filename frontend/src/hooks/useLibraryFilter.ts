import { useMemo } from 'react';
import type { PdfFile, BookMetaMap } from '../types';

interface UseLibraryFilterParams {
    pdfs: PdfFile[];
    directories: string[];
    searchText: string;
    authorFilter: string;
    /** タグフィルター（空文字なら無効） */
    tagFilter?: string;
    currentPath: string;
    meta: BookMetaMap;
}

function getEntryFromMeta(meta: BookMetaMap, path: string, name: string) {
    const key = path ? `${path}/${name}` : name;
    return meta[key];
}

function getAuthorsFromMeta(meta: BookMetaMap, path: string, name: string): string[] {
    return getEntryFromMeta(meta, path, name)?.authors ?? [];
}

function getTagsFromMeta(meta: BookMetaMap, path: string, name: string): string[] {
    return getEntryFromMeta(meta, path, name)?.tags ?? [];
}

export function useLibraryFilter({
    pdfs,
    directories,
    searchText,
    authorFilter,
    tagFilter = '',
    currentPath,
    meta,
}: UseLibraryFilterParams) {
    const filteredPdfs = useMemo(() => {
        let result = pdfs;

        const trimmed = searchText.trim();
        if (trimmed) {
            const lower = trimmed.toLowerCase();
            result = result.filter(p => {
                if (p.name.toLowerCase().includes(lower)) return true;
                const authors = getAuthorsFromMeta(meta, currentPath, p.name);
                if (authors.some(a => a.toLowerCase().includes(lower))) return true;
                const tags = getTagsFromMeta(meta, currentPath, p.name);
                return tags.some(t => t.toLowerCase().includes(lower));
            });
        }

        if (authorFilter) {
            result = result.filter(p =>
                getAuthorsFromMeta(meta, currentPath, p.name).includes(authorFilter)
            );
        }

        if (tagFilter) {
            result = result.filter(p =>
                getTagsFromMeta(meta, currentPath, p.name).includes(tagFilter)
            );
        }

        return result;
    }, [pdfs, searchText, authorFilter, tagFilter, currentPath, meta]);

    const filteredDirs = useMemo(() => {
        const trimmed = searchText.trim();
        if (!trimmed) return directories;
        const lower = trimmed.toLowerCase();
        return directories.filter(d => d.toLowerCase().includes(lower));
    }, [directories, searchText]);

    return { filteredPdfs, filteredDirs };
}
