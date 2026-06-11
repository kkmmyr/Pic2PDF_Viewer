/**
 * 質問履歴の一覧取得 + 削除フック。
 *
 * 表示は時系列降順。当面は全件まとめて取得（履歴上限なし要件 / 件数増加が懸念に
 * なれば paged 化へ後続改修）。
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import { deleteQaHistory, fetchQaHistory } from '@/features/novel_db/api';
import type { QaHistoryEntry, QaHistoryListResponse } from '@/features/novel_db/types';

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
    const queryClient = useQueryClient();
    const queryKey = ['qaHistory', book ?? null] as const;

    const query = useQuery({
        queryKey,
        queryFn: () => fetchQaHistory(0, FETCH_LIMIT, book),
        staleTime: Infinity,
    });

    const deleteMutation = useMutation({
        mutationFn: (id: number) => deleteQaHistory(id),
        onMutate: (id) => {
            const prev = queryClient.getQueryData<QaHistoryListResponse>(queryKey);
            queryClient.setQueryData(queryKey, (old: QaHistoryListResponse | undefined) => {
                if (!old) return old;
                return {
                    items: old.items.filter((i) => i.id !== id),
                    total: Math.max(0, old.total - 1),
                };
            });
            return { prev };
        },
        onError: (_err, _id, context) => {
            if (context?.prev !== undefined) {
                queryClient.setQueryData(queryKey, context.prev);
            }
        },
    });

    return {
        items: query.data?.items ?? [],
        total: query.data?.total ?? 0,
        isLoading: query.isLoading,
        error: query.error instanceof Error ? query.error.message : null,
        deleteItem: (id: number) => deleteMutation.mutateAsync(id),
        refetch: async () => {
            await queryClient.refetchQueries({
                queryKey: queryKey as unknown as readonly unknown[],
            });
        },
    };
}
