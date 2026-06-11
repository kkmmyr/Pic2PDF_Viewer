import { useCallback, useEffect, useState } from 'react';

import { fetchBookDetail } from '@/features/novel_db/api';
import type { BookDetail } from '@/features/novel_db/types';

interface UseBookDetail {
    detail: BookDetail | null;
    isLoading: boolean;
    error: string | null;
    refetch: () => Promise<void>;
}

export function useBookDetail(bookName: string): UseBookDetail {
    const [detail, setDetail] = useState<BookDetail | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const load = useCallback(async () => {
        if (!bookName) return;
        setIsLoading(true);
        setError(null);
        try {
            const d = await fetchBookDetail(bookName);
            setDetail(d);
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : '取得失敗');
            setDetail(null);
        } finally {
            setIsLoading(false);
        }
    }, [bookName]);

    useEffect(() => {
        void load();
    }, [load]);

    return { detail, isLoading, error, refetch: load };
}
