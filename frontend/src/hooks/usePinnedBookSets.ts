import { useMemo } from 'react';
import type { BookMetaMap } from '../types';
import type { PinsMap } from './useLibraryPins';
import { authorsKey } from '../utils/authors';

interface UsePinnedBookSetsParams {
    meta: BookMetaMap;
    currentPath: string;
    seriesPins: PinsMap;
    authorPins: PinsMap;
    authorFilter: string;
    seriesFilter: string;
}

interface UsePinnedBookSetsResult {
    /** favorites_first ソート用: シリーズ・作者ピン両方を含む */
    pinnedBooks: Set<string>;
    /** 文脈別お気に入りSet（PdfGrid の isFav 表示用）
     *  seriesFilter 中はシリーズピンのみ、authorFilter 中は作者ピンのみ返す */
    contextualFavorites: Set<string>;
}

function isDirectChild(key: string, currentPath: string): boolean {
    return currentPath
        ? key.startsWith(currentPath + '/') && !key.slice(currentPath.length + 1).includes('/')
        : !key.includes('/');
}

function nameFromKey(key: string, currentPath: string): string {
    return currentPath ? key.slice(currentPath.length + 1) : key;
}

export function usePinnedBookSets({
    meta,
    currentPath,
    seriesPins,
    authorPins,
    authorFilter,
    seriesFilter,
}: UsePinnedBookSetsParams): UsePinnedBookSetsResult {
    const pinnedBooks = useMemo(() => {
        const set = new Set<string>();
        for (const [key, entry] of Object.entries(meta)) {
            if (!isDirectChild(key, currentPath)) continue;
            const name = nameFromKey(key, currentPath);
            if (entry.series_id && seriesPins[entry.series_id] === name) {
                set.add(name);
                continue;
            }
            if (entry.authors?.length) {
                const ak = authorsKey(entry.authors);
                if (authorPins[ak] === name) set.add(name);
            }
        }
        return set;
    }, [meta, currentPath, seriesPins, authorPins]);

    const contextualFavorites = useMemo(() => {
        if (!seriesFilter && !authorFilter) return new Set<string>();
        const set = new Set<string>();
        for (const [key, entry] of Object.entries(meta)) {
            if (!isDirectChild(key, currentPath)) continue;
            const name = nameFromKey(key, currentPath);
            if (seriesFilter) {
                if (entry.series_id && seriesPins[entry.series_id] === name) set.add(name);
            } else {
                if (entry.authors?.length) {
                    const ak = authorsKey(entry.authors);
                    if (authorPins[ak] === name) set.add(name);
                }
            }
        }
        return set;
    }, [seriesFilter, authorFilter, meta, currentPath, seriesPins, authorPins]);

    return { pinnedBooks, contextualFavorites };
}
