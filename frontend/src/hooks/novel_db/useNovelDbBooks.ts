import { useEffect } from 'react';
import { useNovelBooksStore } from '../../stores/novelBooksStore';
import type { BookSummary, SeriesSummary } from '../../features/novel_db/types';

export interface UseNovelDbBooks {
    books: BookSummary[];
    series: SeriesSummary[];
    isLoading: boolean;
    error: string | null;
    refetch: () => Promise<void>;
}

export function useNovelDbBooks(): UseNovelDbBooks {
    const { books, series, isLoading, error, fetch } = useNovelBooksStore();

    useEffect(() => {
        // データ未取得かつ取得中でなければ初回フェッチ。
        // 他コンポーネントが先にフェッチ中の場合は store の isLoading が true になっているためスキップ。
        if (books.length === 0 && !isLoading) {
            void fetch();
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    return { books, series, isLoading, error, refetch: fetch };
}
