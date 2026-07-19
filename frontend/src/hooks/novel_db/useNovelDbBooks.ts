import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { BookSummary, SeriesSummary } from '@/features/novel_db/types';
import {
    novelBooksQueryOptions,
    novelDbKeys,
    novelSeriesQueryOptions,
} from '@/features/novel_db/queries';

export const novelBooksQueryKey = novelDbKeys.books();

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
 * books / series のReact Queryキャッシュを全ページで共有する。
 * 旧 novelBooksStore（Zustand）を廃止し useQuery に一本化。
 */
export function useNovelDbBooks(): UseNovelDbBooks {
    const queryClient = useQueryClient();

    const booksQuery = useQuery(novelBooksQueryOptions());
    const seriesQuery = useQuery(novelSeriesQueryOptions());
    const error = booksQuery.error ?? seriesQuery.error;

    const refetch = async () => {
        await queryClient.invalidateQueries({ queryKey: novelDbKeys.library() });
    };

    return {
        books: Array.isArray(booksQuery.data) ? (booksQuery.data as BookSummary[]) : [],
        series: Array.isArray(seriesQuery.data) ? (seriesQuery.data as SeriesSummary[]) : [],
        isLoading: booksQuery.isLoading || seriesQuery.isLoading,
        error: error instanceof Error ? error.message : error ? String(error) : null,
        refetch,
    };
}
