import { useMemo } from 'react';

import type { BookSummary } from '../features/novel_db/types';

export type GroupMode = 'flat' | 'author' | 'series';

export interface BookGroup {
    label: string;
    books: BookSummary[];
}

export interface NovelLibraryGroupResult {
    groups: BookGroup[];
    /** グループに属さない書籍（作者未設定 / シリーズ未設定） */
    ungrouped: BookSummary[];
}

/**
 * 書籍一覧を groupMode に従って作者別 / シリーズ別にグループ化する。
 * - flat: 全書籍を ungrouped に返す（グループなし）
 * - author: 第 1 作者でグループ化。作者未設定は ungrouped
 * - series: series_id でグループ化。series 内は volume 昇順（null は末尾）。シリーズ未設定は ungrouped
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
                .map(([label, grpBooks]) => ({
                    label,
                    books: [...grpBooks].sort((a, b) => a.name.localeCompare(b.name, 'ja')),
                }));
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
        const groups = [...grouped.values()]
            .sort((a, b) => a.label.localeCompare(b.label, 'ja'))
            .map((g) => ({
                label: g.label,
                books: [...g.books].sort((a, b) => {
                    if (a.volume === null && b.volume === null)
                        return a.name.localeCompare(b.name, 'ja');
                    if (a.volume === null) return 1;
                    if (b.volume === null) return -1;
                    return a.volume - b.volume;
                }),
            }));
        return { groups, ungrouped };
    }, [books, mode]);
}
