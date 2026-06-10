import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { BookSummary, SeriesSummary } from '../../features/novel_db/types';
import { fetchBooks, fetchSeries } from '../../features/novel_db/api';

export const novelBooksQueryKey = ['novelBooks'] as const;

export interface UseNovelDbBooks {
    books: BookSummary[];
    series: SeriesSummary[];
    isLoading: boolean;
    error: string | null;
    refetch: () => Promise<void>;
}

/**
 * novel books/series データを取得するフック。
 *
 * React Query キャッシュ ['novelBooks'] を全ページで共有する。
 * 旧 novelBooksStore（Zustand）を廃止し useQuery に一本化。
 */
export function useNovelDbBooks(): UseNovelDbBooks {
    const queryClient = useQueryClient();

    const { data, isLoading, error, refetch: queryRefetch } = useQuery({
        queryKey: novelBooksQueryKey,
        queryFn: async () => {
            const [books, series] = await Promise.all([fetchBooks(), fetchSeries()]);
            return {
                books: Array.isArray(books) ? (books as BookSummary[]) : [],
                series: Array.isArray(series) ? (series as SeriesSummary[]) : [],
            };
        },
    });

    const refetch = async () => {
        await queryClient.invalidateQueries({ queryKey: novelBooksQueryKey });
    };

    return {
        books: data?.books ?? [],
        series: data?.series ?? [],
        isLoading,
        error: error instanceof Error ? error.message : error ? String(error) : null,
        refetch,
    };
}
