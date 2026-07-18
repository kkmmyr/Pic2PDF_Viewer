import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { fetchBookDetail } from '@/features/novel_db/api';
import type { BookDetail } from '@/features/novel_db/types';

interface UseBookDetail {
    detail: BookDetail | null;
    isLoading: boolean;
    error: string | null;
    refetch: () => Promise<void>;
}

export function useBookDetail(bookName: string): UseBookDetail {
    const [refetchError, setRefetchError] = useState<string | null>(null);
    const query = useQuery({
        queryKey: ['novelBookDetail', bookName],
        queryFn: () => fetchBookDetail(bookName),
        enabled: bookName.length > 0,
    });

    useEffect(() => setRefetchError(null), [bookName]);

    return {
        detail: refetchError ? null : (query.data ?? null),
        isLoading: query.isLoading,
        error: refetchError ?? (query.error instanceof Error ? query.error.message : null),
        refetch: async () => {
            if (!bookName) return;
            setRefetchError(null);
            const result = await query.refetch();
            if (result.error) {
                setRefetchError(
                    result.error instanceof Error ? result.error.message : String(result.error),
                );
            }
        },
    };
}
