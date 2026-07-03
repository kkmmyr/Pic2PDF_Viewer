import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import type { DragEndEvent } from '@dnd-kit/core';
import { arrayMove } from '@dnd-kit/sortable';

import type { BookSummary } from '@/features/novel_db/types';
import { reorderNovelSeries } from '@/features/novel_db/api';

/**
 * シリーズドリルダウン表示のドラッグ&ドロップ並び替え（4.x）。
 *
 * - ドラッグ完了時に楽観的に並び替え、API 呼び出し完了を待たず表示を更新する
 * - API 失敗時は元の順序へロールバックし、トースト通知する
 * - 親から渡される `books`（例: 他画面での編集後の再取得結果）が変わったら local state を
 *   再同期する。これをしないと、ドリルダウン表示中に他経路でメタが更新されても
 *   画面が古いままになってしまう（stale state バグ）。
 */
export function useSeriesDrilldownReorder(
    seriesId: string,
    books: BookSummary[],
    onReordered: () => void,
) {
    const [localBooks, setLocalBooks] = useState<BookSummary[]>(books);

    // 親から新しい books が渡されたら local state を同期する。
    useEffect(() => {
        setLocalBooks(books);
    }, [books]);

    const handleDragEnd = useCallback(
        async (event: DragEndEvent) => {
            const { active, over } = event;
            if (!over || active.id === over.id) return;

            const oldIndex = localBooks.findIndex((b) => b.name === active.id);
            const newIndex = localBooks.findIndex((b) => b.name === over.id);
            if (oldIndex === -1 || newIndex === -1) return;

            const reordered = arrayMove(localBooks, oldIndex, newIndex);
            setLocalBooks(reordered);

            try {
                await reorderNovelSeries(
                    seriesId,
                    reordered.map((b) => `${b.name}.pdf`),
                );
                onReordered();
            } catch {
                // ロールバック
                setLocalBooks(localBooks);
                toast.error('並び替えの保存に失敗しました。');
            }
        },
        [localBooks, seriesId, onReordered],
    );

    return { books: localBooks, handleDragEnd };
}
