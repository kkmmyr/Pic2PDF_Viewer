import { useMemo } from 'react';
import type { PdfFile, BookMetaMap } from '../types';

interface UseLibraryFilterParams {
    pdfs: PdfFile[];
    directories: string[];
    searchText: string;
    authorFilter: string;
    /** タグフィルター（空文字なら無効） */
    tagFilter?: string;
    /** シリーズフィルター（series_id 完全一致、空文字なら無効） */
    seriesFilter?: string;
    /**
     * 非表示モード（ゴミ箱方式）。
     * - `false`（デフォルト）: 通常モード。`hidden=true` の書籍を完全除外。
     * - `true`: 非表示書籍のみを表示する。
     */
    showHidden?: boolean;
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

function getSeriesIdFromMeta(meta: BookMetaMap, path: string, name: string): string | undefined {
    return getEntryFromMeta(meta, path, name)?.series_id;
}

function isHiddenInMeta(meta: BookMetaMap, path: string, name: string): boolean {
    return getEntryFromMeta(meta, path, name)?.hidden === true;
}

export function useLibraryFilter({
    pdfs,
    directories,
    searchText,
    authorFilter,
    tagFilter = '',
    seriesFilter = '',
    showHidden = false,
    currentPath,
    meta,
}: UseLibraryFilterParams) {
    const filteredPdfs = useMemo(() => {
        // ゴミ箱方式: showHidden=false なら hidden を全除外、true なら hidden のみ表示
        let result = pdfs.filter(p => {
            const hidden = isHiddenInMeta(meta, currentPath, p.name);
            return showHidden ? hidden : !hidden;
        });

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

        if (seriesFilter) {
            result = result.filter(p =>
                getSeriesIdFromMeta(meta, currentPath, p.name) === seriesFilter
            );
        }

        return result;
    }, [pdfs, searchText, authorFilter, tagFilter, seriesFilter, showHidden, currentPath, meta]);

    const filteredDirs = useMemo(() => {
        const trimmed = searchText.trim();
        if (!trimmed) return directories;
        const lower = trimmed.toLowerCase();
        return directories.filter(d => d.toLowerCase().includes(lower));
    }, [directories, searchText]);

    return { filteredPdfs, filteredDirs };
}
