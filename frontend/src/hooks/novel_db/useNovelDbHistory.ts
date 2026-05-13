/**
 * 質問履歴の一覧取得 + 削除フック。
 *
 * 表示は時系列降順。当面は全件まとめて取得（履歴上限なし要件 / 件数増加が懸念に
 * なれば paged 化へ後続改修）。
 */
import { useCallback, useEffect, useState } from 'react';

import { deleteQaHistory, fetchQaHistory } from '../../features/novel_db/api';
import type { QaHistoryEntry } from '../../features/novel_db/types';

const FETCH_LIMIT = 100;

export interface UseNovelDbHistory {
    items: QaHistoryEntry[];
    total: number;
    isLoading: boolean;
    error: string | null;
    deleteItem: (id: number) => Promise<void>;
    refetch: () => Promise<void>;
}

export function useNovelDbHistory(book?: string): UseNovelDbHistory {
    const [items, setItems] = useState<QaHistoryEntry[]>([]);
    const [total, setTotal] = useState(0);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const refetch = useCallback(async () => {
        setIsLoading(true);
        setError(null);
        try {
            const res = await fetchQaHistory(0, FETCH_LIMIT, book);
            setItems(Array.isArray(res?.items) ? res.items : []);
            setTotal(typeof res?.total === 'number' ? res.total : 0);
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        } finally {
            setIsLoading(false);
        }
    }, [book]);

    useEffect(() => {
        void refetch();
    }, [refetch]);

    const deleteItem = useCallback(async (id: number) => {
        await deleteQaHistory(id);
        setItems((prev) => prev.filter((i) => i.id !== id));
        setTotal((prev) => Math.max(0, prev - 1));
    }, []);

    return { items, total, isLoading, error, deleteItem, refetch };
}
