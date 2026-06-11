import { useMemo } from 'react';
import type { PdfFile, BookMetaMap, ReadState } from '@/types';

interface UseLibraryFilterParams {
    pdfs: PdfFile[];
    searchText: string;
    authorFilter: string;
    /** シリーズフィルター（series_id 完全一致、空文字なら無効） */
    seriesFilter?: string;
    /**
     * 非表示モード（ゴミ箱方式）。
     * - `false`（デフォルト）: 通常モード。`hidden=true` の書籍を完全除外。
     * - `true`: 非表示書籍のみを表示する。
     */
    showHidden?: boolean;
    /**
     * 読書状態フィルター（空文字なら無効）。
     * `meta[key].read_state` が無いエントリは `view_count` から派生して扱う。
     */
    readStateFilter?: '' | ReadState;
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

function getSeriesIdFromMeta(meta: BookMetaMap, path: string, name: string): string | undefined {
    return getEntryFromMeta(meta, path, name)?.series_id;
}

function isHiddenInMeta(meta: BookMetaMap, path: string, name: string): boolean {
    return getEntryFromMeta(meta, path, name)?.hidden === true;
}

function getReadStateFromMeta(meta: BookMetaMap, path: string, name: string): ReadState {
    const entry = getEntryFromMeta(meta, path, name);
    if (entry?.read_state) return entry.read_state;
    return (entry?.view_count ?? 0) > 0 ? 'reading' : 'unread';
}

export function useLibraryFilter({
    pdfs,
    searchText,
    authorFilter,
    seriesFilter = '',
    showHidden = false,
    readStateFilter = '',
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
                return authors.some((a) => a.toLowerCase().includes(lower));
            });
        }

        if (authorFilter) {
            result = result.filter((p) =>
                getAuthorsFromMeta(meta, currentPath, p.name).includes(authorFilter),
            );
        }

        if (seriesFilter) {
            result = result.filter(
                (p) => getSeriesIdFromMeta(meta, currentPath, p.name) === seriesFilter,
            );
        }

        if (readStateFilter) {
            result = result.filter(
                (p) => getReadStateFromMeta(meta, currentPath, p.name) === readStateFilter,
            );
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
        seriesFilter,
        showHidden,
        readStateFilter,
        genreFilter,
        currentPath,
        meta,
    ]);

    return { filteredPdfs };
}
