import { useMemo } from 'react';
import type { BookMetaMap } from '../types';

type SeriesRef = { id: string; title: string; index: number } | null;
type VolumeRef = { name: string; index: number; title: string } | null;

function findAdjacentVolume(
    meta: BookMetaMap,
    getSeries: (path: string, name: string) => SeriesRef,
    currentPath: string,
    selectedPdf: string,
    direction: 'next' | 'prev',
): VolumeRef {
    const cur = getSeries(currentPath, selectedPdf);
    if (!cur) return null;
    const prefix = currentPath ? `${currentPath}/` : '';
    let best: VolumeRef = null;
    for (const [key, e] of Object.entries(meta)) {
        if (e.series_id !== cur.id) continue;
        const idx = e.series_index ?? 0;
        if (direction === 'next' ? idx <= cur.index : idx >= cur.index) continue;
        // 同フォルダ判定: prefix が一致し、残部分にスラッシュがない
        const rest = currentPath
            ? key.startsWith(prefix)
                ? key.slice(prefix.length)
                : null
            : key.includes('/')
              ? null
              : key;
        if (rest === null || rest.includes('/')) continue;
        // next: 最小の idx / prev: 最大の idx を選ぶ
        if (!best || (direction === 'next' ? idx < best.index : idx > best.index)) {
            best = { name: rest, index: idx, title: e.series_title ?? '' };
        }
    }
    return best;
}

/**
 * 現在の書籍の次巻を返す。
 * 同フォルダ・同シリーズ内で series_index が現在より大きい中で最小のものを選ぶ。
 */
export function useNextSeriesVolume(
    meta: BookMetaMap,
    getSeries: (path: string, name: string) => SeriesRef,
    currentPath: string,
    selectedPdf: string,
): VolumeRef {
    return useMemo(
        () => findAdjacentVolume(meta, getSeries, currentPath, selectedPdf, 'next'),
        [meta, getSeries, currentPath, selectedPdf],
    );
}

/**
 * 現在の書籍の前巻を返す。
 * 同フォルダ・同シリーズ内で series_index が現在より小さい中で最大のものを選ぶ。
 */
export function usePrevSeriesVolume(
    meta: BookMetaMap,
    getSeries: (path: string, name: string) => SeriesRef,
    currentPath: string,
    selectedPdf: string,
): VolumeRef {
    return useMemo(
        () => findAdjacentVolume(meta, getSeries, currentPath, selectedPdf, 'prev'),
        [meta, getSeries, currentPath, selectedPdf],
    );
}
