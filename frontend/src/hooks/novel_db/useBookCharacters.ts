/**
 * 書籍のキャラクター一覧（B-15）を on-demand で取得・キャッシュするフック。
 *
 * BookCard の「登場人物」トグル展開時にのみ fetch する想定。
 * `enabled=false` の間は API を叩かない。
 */
import { useCallback, useEffect, useState } from 'react';

import { fetchBookCharacters } from '@/features/novel_db/api';
import type { CharacterSummary } from '@/features/novel_db/types';

export interface UseBookCharacters {
    characters: CharacterSummary[];
    isLoading: boolean;
    error: string | null;
    refetch: () => Promise<void>;
}

export function useBookCharacters(bookName: string, enabled: boolean): UseBookCharacters {
    const [characters, setCharacters] = useState<CharacterSummary[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const refetch = useCallback(async () => {
        setIsLoading(true);
        setError(null);
        try {
            const list = await fetchBookCharacters(bookName);
            setCharacters(Array.isArray(list) ? list : []);
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        } finally {
            setIsLoading(false);
        }
    }, [bookName]);

    useEffect(() => {
        if (!enabled) return;
        void refetch();
    }, [enabled, refetch]);

    return { characters, isLoading, error, refetch };
}
