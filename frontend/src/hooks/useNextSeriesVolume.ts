import { useMemo } from 'react';
import type { BookMetaMap } from '../types';

type SeriesRef = { id: string; title: string; index: number } | null;

/**
 * 現在の書籍の次巻を返す。
 * 同フォルダ・同シリーズ内で series_index が現在より大きい中で最小のものを選ぶ。
 * 対象外（シリーズ未割当・次巻なし）の場合は null。
 */
export function useNextSeriesVolume(
    meta: BookMetaMap,
    getSeries: (path: string, name: string) => SeriesRef,
    currentPath: string,
    selectedPdf: string,
): { name: string; index: number; title: string } | null {
    return useMemo(() => {
        const cur = getSeries(currentPath, selectedPdf);
        if (!cur) return null;
        const prefix = currentPath ? `${currentPath}/` : '';
        let best: { name: string; index: number; title: string } | null = null;
        for (const [key, e] of Object.entries(meta)) {
            if (e.series_id !== cur.id) continue;
            const idx = e.series_index ?? 0;
            if (idx <= cur.index) continue;
            // 同フォルダ判定: prefix が一致し、残部分にスラッシュがない
            const rest = currentPath
                ? (key.startsWith(prefix) ? key.slice(prefix.length) : null)
                : (key.includes('/') ? null : key);
            if (rest === null || rest.includes('/')) continue;
            if (!best || idx < best.index) {
                best = { name: rest, index: idx, title: e.series_title ?? '' };
            }
        }
        return best;
    }, [meta, getSeries, currentPath, selectedPdf]);
}
