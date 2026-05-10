/**
 * 書籍一覧 + シリーズ一覧を取得・キャッシュするフック。
 */
import { useCallback, useEffect, useState } from 'react';

import { fetchBooks, fetchSeries } from '../../features/novel_db/api';
import type { BookSummary, SeriesSummary } from '../../features/novel_db/types';

export interface UseNovelDbBooks {
    books: BookSummary[];
    series: SeriesSummary[];
    isLoading: boolean;
    error: string | null;
    refetch: () => Promise<void>;
}

export function useNovelDbBooks(): UseNovelDbBooks {
    const [books, setBooks] = useState<BookSummary[]>([]);
    const [series, setSeries] = useState<SeriesSummary[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const refetch = useCallback(async () => {
        setIsLoading(true);
        setError(null);
        try {
            const [b, s] = await Promise.all([fetchBooks(), fetchSeries()]);
            setBooks(Array.isArray(b) ? b : []);
            setSeries(Array.isArray(s) ? s : []);
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        } finally {
            setIsLoading(false);
        }
    }, []);

    useEffect(() => {
        void refetch();
    }, [refetch]);

    return { books, series, isLoading, error, refetch };
}
