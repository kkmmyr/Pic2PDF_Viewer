import { useCallback, useMemo, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { toast } from 'sonner';

import { fetchNovelAuthors, fetchSeries, patchNovelBookMeta } from '@/features/novel_db/api';
import type { BookSummary } from '@/features/novel_db/types';
import type { ExistingSeriesOption } from '@/types';

interface UseNovelLibraryBulkActionsOptions {
    books: BookSummary[];
    selectedNames: Set<string>;
    onMetaRefetch: () => void;
    onClearSelection: () => void;
}

interface BulkSeriesAssignment {
    mode: 'existing' | 'new' | 'remove';
    seriesId?: string;
    indexes?: number[];
}

/**
 * 小説ライブラリの一括メタデータ更新を扱う。
 *
 * 選択対象は表示順で逐次更新し、全件成功したときだけ一覧を再取得して選択を解除する。
 * 更新に失敗した場合は呼び出し元のダイアログへ reject を返し、残りの更新を行わない。
 */
export function useNovelLibraryBulkActions({
    books,
    selectedNames,
    onMetaRefetch,
    onClearSelection,
}: UseNovelLibraryBulkActionsOptions) {
    const [showAuthorDialog, setShowAuthorDialog] = useState(false);
    const [showSeriesDialog, setShowSeriesDialog] = useState(false);
    const [allAuthors, setAllAuthors] = useState<string[]>([]);
    const [allSeriesForDialog, setAllSeriesForDialog] = useState<ExistingSeriesOption[]>([]);

    const selectedBooks = useMemo(
        () => books.filter((book) => selectedNames.has(book.name)),
        [books, selectedNames],
    );
    const authorCandidatesMutation = useMutation({ mutationFn: fetchNovelAuthors, retry: false });
    const seriesCandidatesMutation = useMutation({ mutationFn: fetchSeries, retry: false });

    const applyAuthorsMutation = useMutation({
        retry: false,
        mutationFn: async (authors: string[]) => {
            for (const book of selectedBooks) {
                await patchNovelBookMeta(`${book.name}.pdf`, { authors });
            }
        },
    });
    const assignSeriesMutation = useMutation({
        retry: false,
        mutationFn: async (params: BulkSeriesAssignment) => {
            for (const [index, book] of selectedBooks.entries()) {
                if (params.mode === 'remove') {
                    await patchNovelBookMeta(`${book.name}.pdf`, { series_id: '' });
                } else {
                    await patchNovelBookMeta(`${book.name}.pdf`, {
                        series_id: params.seriesId,
                        volume: params.indexes?.[index] ?? null,
                    });
                }
            }
        },
    });

    const openAuthorDialog = useCallback(async () => {
        try {
            setAllAuthors(await authorCandidatesMutation.mutateAsync());
        } catch {
            toast.error('作者一覧の取得に失敗しました');
            setAllAuthors([]);
        }
        setShowAuthorDialog(true);
    }, [authorCandidatesMutation]);

    const openSeriesDialog = useCallback(async () => {
        try {
            const series = await seriesCandidatesMutation.mutateAsync();
            setAllSeriesForDialog(
                series.map((item) => {
                    let max = 0;
                    for (const book of books) {
                        if (
                            book.series_id === item.id &&
                            book.volume !== null &&
                            book.volume > max
                        ) {
                            max = book.volume;
                        }
                    }
                    return { id: item.id, title: item.name, maxIndex: max };
                }),
            );
        } catch {
            toast.error('シリーズ一覧の取得に失敗しました');
            setAllSeriesForDialog([]);
        }
        setShowSeriesDialog(true);
    }, [books, seriesCandidatesMutation]);

    const applyAuthors = useCallback(
        async (authors: string[]) => {
            await applyAuthorsMutation.mutateAsync(authors);
            onMetaRefetch();
            onClearSelection();
        },
        [applyAuthorsMutation, onClearSelection, onMetaRefetch],
    );

    const assignSeries = useCallback(
        async (params: BulkSeriesAssignment) => {
            await assignSeriesMutation.mutateAsync(params);
            onMetaRefetch();
            onClearSelection();
        },
        [assignSeriesMutation, onClearSelection, onMetaRefetch],
    );

    return {
        showAuthorDialog,
        setShowAuthorDialog,
        showSeriesDialog,
        setShowSeriesDialog,
        allAuthors,
        allSeriesForDialog,
        openAuthorDialog,
        openSeriesDialog,
        applyAuthors,
        assignSeries,
    };
}
