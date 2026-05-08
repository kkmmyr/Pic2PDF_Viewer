import { useMemo } from 'react';
import type { BookMetaMap } from '../types';
import { cmpJa } from '../utils/sort';

interface UseMetaDerivedResult {
    /** 全作者名（重複排除・ソート済み）
     * authors 不在エントリからの undefined 混入を ?? [] でガード */
    allAuthors: string[];
    /** 全ジャンル（重複排除・ソート済み） */
    allGenres: string[];
    /** 全シリーズ一覧（id, title、タイトル順） */
    allSeries: { id: string; title: string }[];
    /** 全シリーズ統計付き一覧（id, title, maxIndex, count、タイトル順）
     * maxIndex: そのシリーズの最大 series_index（一括追加の採番開始用）*/
    allSeriesWithStats: { id: string; title: string; maxIndex: number; count: number }[];
}

export function useMetaDerived(meta: BookMetaMap): UseMetaDerivedResult {
    const allAuthors = useMemo(
        () => [...new Set(Object.values(meta).flatMap((e) => e.authors ?? []))].sort(cmpJa),
        [meta],
    );

    const allGenres = useMemo(
        () =>
            [
                ...new Set(
                    Object.values(meta)
                        .map((e) => e.genre)
                        .filter((g): g is string => !!g),
                ),
            ].sort(cmpJa),
        [meta],
    );

    const allSeries = useMemo(() => {
        const map = new Map<string, string>();
        for (const e of Object.values(meta)) {
            if (e.series_id && !map.has(e.series_id)) {
                map.set(e.series_id, e.series_title ?? '');
            }
        }
        return Array.from(map.entries())
            .map(([id, title]) => ({ id, title }))
            .sort((a, b) => cmpJa(a.title, b.title));
    }, [meta]);

    const allSeriesWithStats = useMemo(() => {
        const map = new Map<string, { title: string; maxIndex: number; count: number }>();
        for (const e of Object.values(meta)) {
            if (!e.series_id) continue;
            const idx = e.series_index ?? 0;
            const existing = map.get(e.series_id);
            if (existing) {
                existing.count++;
                if (idx > existing.maxIndex) existing.maxIndex = idx;
            } else {
                map.set(e.series_id, { title: e.series_title ?? '', maxIndex: idx, count: 1 });
            }
        }
        return Array.from(map.entries())
            .map(([id, { title, maxIndex, count }]) => ({ id, title, maxIndex, count }))
            .sort((a, b) => cmpJa(a.title, b.title));
    }, [meta]);

    return { allAuthors, allGenres, allSeries, allSeriesWithStats };
}
