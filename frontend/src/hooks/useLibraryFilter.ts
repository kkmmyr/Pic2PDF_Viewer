import { useMemo } from 'react';
import type { PdfFile, BookMetaMap } from '../types';

interface UseLibraryFilterParams {
    pdfs: PdfFile[];
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
    /** 未読フィルター。`true` のとき view_count === 0（または未記録）の書籍のみを表示する。 */
    showUnreadOnly?: boolean;
    /** ジャンルフィルター（空文字なら無効） */
    genreFilter?: string;
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

function getViewCountFromMeta(meta: BookMetaMap, path: string, name: string): number {
    return getEntryFromMeta(meta, path, name)?.view_count ?? 0;
}

export function useLibraryFilter({
    pdfs,
    searchText,
    authorFilter,
    tagFilter = '',
    seriesFilter = '',
    showHidden = false,
    showUnreadOnly = false,
    genreFilter = '',
    currentPath,
    meta,
}: UseLibraryFilterParams) {
    const filteredPdfs = useMemo(() => {
        // ゴミ箱方式: showHidden=false なら hidden を全除外、true なら hidden のみ表示
        let result = pdfs.filter((p) => {
            const hidden = isHiddenInMeta(meta, currentPath, p.name);
            return showHidden ? hidden : !hidden;
        });

        const trimmed = searchText.trim();
        if (trimmed) {
            const lower = trimmed.toLowerCase();
            result = result.filter((p) => {
                if (p.name.toLowerCase().includes(lower)) return true;
                const authors = getAuthorsFromMeta(meta, currentPath, p.name);
                if (authors.some((a) => a.toLowerCase().includes(lower))) return true;
                const tags = getTagsFromMeta(meta, currentPath, p.name);
                return tags.some((t) => t.toLowerCase().includes(lower));
            });
        }

        if (authorFilter) {
            result = result.filter((p) =>
                getAuthorsFromMeta(meta, currentPath, p.name).includes(authorFilter),
            );
        }

        if (tagFilter) {
            result = result.filter((p) =>
                getTagsFromMeta(meta, currentPath, p.name).includes(tagFilter),
            );
        }

        if (seriesFilter) {
            result = result.filter(
                (p) => getSeriesIdFromMeta(meta, currentPath, p.name) === seriesFilter,
            );
        }

        if (showUnreadOnly) {
            result = result.filter((p) => getViewCountFromMeta(meta, currentPath, p.name) === 0);
        }

        if (genreFilter) {
            result = result.filter(
                (p) => (getEntryFromMeta(meta, currentPath, p.name)?.genre ?? '') === genreFilter,
            );
        }

        return result;
    }, [
        pdfs,
        searchText,
        authorFilter,
        tagFilter,
        seriesFilter,
        showHidden,
        showUnreadOnly,
        genreFilter,
        currentPath,
        meta,
    ]);

    return { filteredPdfs };
}
