import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { fetchCharacterDetail } from '@/features/novel_db/api';
import type { CharacterDetail } from '@/features/novel_db/types';

export interface UseCharacterDetail {
    detail: CharacterDetail | null;
    isLoading: boolean;
    error: string | null;
    refetch: () => Promise<void>;
}

export function useCharacterDetail(
    bookName: string | null,
    charName: string | null,
): UseCharacterDetail {
    const [refetchError, setRefetchError] = useState<string | null>(null);
    const query = useQuery({
        queryKey: ['novelCharacterDetail', bookName, charName],
        queryFn: () => fetchCharacterDetail(bookName!, charName!),
        enabled: Boolean(bookName && charName),
    });

    useEffect(() => setRefetchError(null), [bookName, charName]);

    return {
        detail: refetchError ? null : (query.data ?? null),
        isLoading: query.isLoading,
        error: refetchError ?? (query.error instanceof Error ? query.error.message : null),
        refetch: async () => {
            if (!bookName || !charName) return;
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
