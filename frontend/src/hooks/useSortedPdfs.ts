import { useMemo } from 'react';
import type { PdfFile, SortOrder } from '../types';

/**
 * PDF一覧をお気に入りと並び替え順序に基づいてソートするフック。
 */
export function useSortedPdfs(
    pdfs: PdfFile[],
    sortOrder: SortOrder,
    favorites: Set<string>
): PdfFile[] {
    return useMemo(() => {
        const sorted = [...pdfs];

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
                default:
                    return 0;
            }
        });

        return sorted;
    }, [pdfs, sortOrder, favorites]);
}
