import { useMemo } from 'react';
import type { PdfFile, SortOrder } from '../types';

/**
 * PDF一覧をお気に入りと並び替え順序に基づいてソートするフック。
 *
 * @param getViewCount - 閲覧回数取得関数。'view_desc' ソート時に使用。未指定なら 0 として扱う。
 * @param getLastViewedAt - 最終閲覧時刻取得関数 (UNIX 秒)。'recent_view' ソート時に使用。未閲覧は undefined。
 */
export function useSortedPdfs(
    pdfs: PdfFile[],
    sortOrder: SortOrder,
    favorites: Set<string>,
    getViewCount?: (name: string) => number,
    getLastViewedAt?: (name: string) => number | undefined,
): PdfFile[] {
    return useMemo(() => {
        const sorted = [...pdfs];
        const views = getViewCount ?? (() => 0);
        const lastViewed = getLastViewedAt ?? (() => undefined);

        sorted.sort((a, b) => {
            const aFav = favorites.has(a.name) ? 0 : 1;
            const bFav = favorites.has(b.name) ? 0 : 1;

            if (sortOrder === 'favorites_first') {
                if (aFav !== bFav) return aFav - bFav;
                // 同じグループ内は名前昇順
                return a.name.localeCompare(b.name, 'ja');
            }

            switch (sortOrder) {
                case 'name_asc':
                    return a.name.localeCompare(b.name, 'ja');
                case 'name_desc':
                    return b.name.localeCompare(a.name, 'ja');
                case 'date_asc':
                    return (a.created_at ?? 0) - (b.created_at ?? 0);
                case 'date_desc':
                    return (b.created_at ?? 0) - (a.created_at ?? 0);
                case 'view_desc': {
                    const diff = views(b.name) - views(a.name);
                    if (diff !== 0) return diff;
                    return a.name.localeCompare(b.name, 'ja');
                }
                case 'recent_view': {
                    // 未閲覧は末尾。同時刻は名前昇順。
                    const aT = lastViewed(a.name);
                    const bT = lastViewed(b.name);
                    if (aT === undefined && bT === undefined) {
                        return a.name.localeCompare(b.name, 'ja');
                    }
                    if (aT === undefined) return 1;
                    if (bT === undefined) return -1;
                    if (aT !== bT) return bT - aT;
                    return a.name.localeCompare(b.name, 'ja');
                }
                default:
                    return 0;
            }
        });

        return sorted;
    }, [pdfs, sortOrder, favorites, getViewCount, getLastViewedAt]);
}
