import { useCallback, useEffect, useState } from 'react';

import { fetchBookDetail } from '../../features/novel_db/api';
import type { BookDetail } from '../../features/novel_db/types';

interface UseBookDetail {
    detail: BookDetail | null;
    isLoading: boolean;
    error: string | null;
    refetch: () => void;
}

export function useBookDetail(bookName: string): UseBookDetail {
    const [detail, setDetail] = useState<BookDetail | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const load = useCallback(() => {
        if (!bookName) return;
        setIsLoading(true);
        setError(null);
        fetchBookDetail(bookName)
            .then(setDetail)
            .catch((e: unknown) => {
                setError(e instanceof Error ? e.message : '取得失敗');
            })
            .finally(() => setIsLoading(false));
    }, [bookName]);

    useEffect(() => {
        load();
    }, [load]);

    return { detail, isLoading, error, refetch: load };
}
