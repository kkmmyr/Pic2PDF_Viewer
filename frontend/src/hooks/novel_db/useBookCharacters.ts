/**
 * 書籍のキャラクター一覧（B-15）を on-demand で取得・キャッシュするフック。
 *
 * BookCard の「登場人物」トグル展開時にのみ fetch する想定。
 * `enabled=false` の間は API を叩かない。
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { fetchBookCharacters } from '@/features/novel_db/api';
import type { CharacterSummary } from '@/features/novel_db/types';

export interface UseBookCharacters {
    characters: CharacterSummary[];
    isLoading: boolean;
    error: string | null;
    refetch: () => Promise<void>;
}

export function useBookCharacters(bookName: string, enabled: boolean): UseBookCharacters {
    // refetch の失敗を追跡する補助 state（TanStack Query v5 はデータありの場合 error を更新しない）
    const [refetchError, setRefetchError] = useState<string | null>(null);

    const query = useQuery({
        queryKey: ['bookCharacters', bookName],
        queryFn: () => fetchBookCharacters(bookName),
        enabled,
        staleTime: Infinity,
    });

    const refetch = async () => {
        setRefetchError(null);
        const result = await query.refetch();
        if (result.error) {
            const msg = result.error instanceof Error ? result.error.message : String(result.error);
            setRefetchError(msg);
        }
    };

    const error = refetchError ?? (query.error instanceof Error ? query.error.message : null);

    return {
        characters: Array.isArray(query.data) ? query.data : [],
        isLoading: query.isLoading,
        error,
        refetch,
    };
}
