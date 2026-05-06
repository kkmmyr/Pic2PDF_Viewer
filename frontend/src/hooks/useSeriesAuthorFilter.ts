import { useCallback, useMemo } from 'react';
import type { BookMetaMap } from '../types';

interface UseSeriesAuthorFilterParams {
    meta: BookMetaMap;
    selectedItems: Set<string>;
    getAuthors: (path: string, name: string) => string[];
    currentPath: string;
    allSeries: { id: string; title: string }[];
    allSeriesWithStats: { id: string; title: string; maxIndex: number; count: number }[];
    seriesEditTarget: string | null;
}

interface UseSeriesAuthorFilterResult {
    /** 選択書籍に複数の異なる作者セットが混在しているか */
    isMixedAuthors: boolean;
    /** 指定した作者キーに属するシリーズ ID の Set を返す */
    validSeriesIdsByAuthorKey: (authorKey: string) => Set<string>;
    /** SeriesEditDialog 用: 対象書籍の作者に絞ったシリーズ一覧 */
    seriesEditFilteredSeries: { id: string; title: string }[];
    /** BulkSeriesAssignDialog 用: 選択書籍の共通作者に絞ったシリーズ一覧 */
    bulkSeriesFiltered: { id: string; title: string; maxIndex: number; count: number }[];
}

export function useSeriesAuthorFilter({
    meta,
    selectedItems,
    getAuthors,
    currentPath,
    allSeries,
    allSeriesWithStats,
    seriesEditTarget,
}: UseSeriesAuthorFilterParams): UseSeriesAuthorFilterResult {
    const validSeriesIdsByAuthorKey = useCallback(
        (authorKey: string): Set<string> => {
            const ids = new Set<string>();
            for (const entry of Object.values(meta)) {
                if (!entry.series_id) continue;
                const key = [...(entry.authors ?? [])].sort().join('\n');
                if (key === authorKey) ids.add(entry.series_id);
            }
            return ids;
        },
        [meta],
    );

    const isMixedAuthors = useMemo(() => {
        const keys = new Set<string>();
        for (const name of Array.from(selectedItems)) {
            if (!name.toLowerCase().endsWith('.pdf')) continue;
            keys.add([...getAuthors(currentPath, name)].sort().join('\n'));
        }
        return keys.size > 1;
    }, [selectedItems, getAuthors, currentPath]);

    const seriesEditFilteredSeries = useMemo(() => {
        if (!seriesEditTarget) return allSeries;
        const authors = getAuthors(currentPath, seriesEditTarget);
        if (authors.length === 0) return allSeries;
        const authorKey = [...authors].sort().join('\n');
        const validIds = validSeriesIdsByAuthorKey(authorKey);
        return allSeries.filter((s) => validIds.has(s.id));
    }, [seriesEditTarget, getAuthors, currentPath, allSeries, validSeriesIdsByAuthorKey]);

    const bulkSeriesFiltered = useMemo(() => {
        if (isMixedAuthors) return allSeriesWithStats;
        const keys = new Set<string>();
        for (const name of Array.from(selectedItems)) {
            if (!name.toLowerCase().endsWith('.pdf')) continue;
            keys.add([...getAuthors(currentPath, name)].sort().join('\n'));
        }
        if (keys.size === 0) return allSeriesWithStats;
        const authorKey = Array.from(keys)[0];
        if (!authorKey) return allSeriesWithStats;
        const validIds = validSeriesIdsByAuthorKey(authorKey);
        return allSeriesWithStats.filter((s) => validIds.has(s.id));
    }, [
        isMixedAuthors,
        selectedItems,
        getAuthors,
        currentPath,
        allSeriesWithStats,
        validSeriesIdsByAuthorKey,
    ]);

    return {
        isMixedAuthors,
        validSeriesIdsByAuthorKey,
        seriesEditFilteredSeries,
        bulkSeriesFiltered,
    };
}
