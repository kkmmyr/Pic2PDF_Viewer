import { useMemo } from 'react';

import type { BookSummary } from '../features/novel_db/types';

export type GroupMode = 'flat' | 'author' | 'series';

export interface NovelBookGroup {
    label: string;
    series_id: string | null;
    representative: BookSummary;
    books: BookSummary[];
}

export interface NovelLibraryGroupResult {
    groups: NovelBookGroup[];
    ungrouped: BookSummary[];
}

function sortBySeriesIndex(books: BookSummary[]): BookSummary[] {
    return [...books].sort((a, b) => {
        const ai = a.series_index ?? a.volume ?? null;
        const bi = b.series_index ?? b.volume ?? null;
        if (ai === null && bi === null) return a.name.localeCompare(b.name, 'ja');
        if (ai === null) return 1;
        if (bi === null) return -1;
        return ai - bi;
    });
}

/**
 * 書籍一覧を groupMode に従って作者別 / シリーズ別にグループ化する。
 * - flat: 全書籍を ungrouped に返す（グループなし）
 * - author: 第 1 作者でグループ化。作者未設定は ungrouped
 * - series: series_id でグループ化。シリーズ内は series_index → volume 昇順（null は末尾）。シリーズ未設定は ungrouped
 */
export function useNovelLibraryGroup(
    books: BookSummary[],
    mode: GroupMode,
): NovelLibraryGroupResult {
    return useMemo(() => {
        if (mode === 'flat') {
            return { groups: [], ungrouped: books };
        }

        if (mode === 'author') {
            const grouped = new Map<string, BookSummary[]>();
            const ungrouped: BookSummary[] = [];
            for (const book of books) {
                const author = book.authors[0];
                if (!author) {
                    ungrouped.push(book);
                } else {
                    if (!grouped.has(author)) grouped.set(author, []);
                    grouped.get(author)!.push(book);
                }
            }
            const groups = [...grouped.entries()]
                .sort(([a], [b]) => a.localeCompare(b, 'ja'))
                .map(([label, grpBooks]) => {
                    const sorted = [...grpBooks].sort((a, b) => a.name.localeCompare(b.name, 'ja'));
                    return {
                        label,
                        series_id: null,
                        representative: sorted[0],
                        books: sorted,
                    };
                });
            return { groups, ungrouped };
        }

        // series mode
        const grouped = new Map<string, { label: string; books: BookSummary[] }>();
        const ungrouped: BookSummary[] = [];
        for (const book of books) {
            if (!book.series_id || !book.series_title) {
                ungrouped.push(book);
            } else {
                if (!grouped.has(book.series_id)) {
                    grouped.set(book.series_id, { label: book.series_title, books: [] });
                }
                grouped.get(book.series_id)!.books.push(book);
            }
        }
        const groups = [...grouped.entries()]
            .sort(([, a], [, b]) => a.label.localeCompare(b.label, 'ja'))
            .map(([series_id, g]) => {
                const sorted = sortBySeriesIndex(g.books);
                return {
                    label: g.label,
                    series_id,
                    representative: sorted[0],
                    books: sorted,
                };
            });
        return { groups, ungrouped };
    }, [books, mode]);
}
