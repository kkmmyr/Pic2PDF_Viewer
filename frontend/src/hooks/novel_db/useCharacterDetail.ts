/**
 * キャラクター詳細（サマリ + 主要シーン top 5）を取得するフック（B-15）。
 *
 * 詳細ダイアログを開いたタイミング（bookName / charName が両方 set）で fetch。
 * どちらかが null の間は API を叩かず idle 状態に戻す。
 */
import { useCallback, useEffect, useState } from 'react';

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
    const [detail, setDetail] = useState<CharacterDetail | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const load = useCallback(async () => {
        if (!bookName || !charName) return;
        setIsLoading(true);
        setError(null);
        try {
            const d = await fetchCharacterDetail(bookName, charName);
            setDetail(d);
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
            setDetail(null);
        } finally {
            setIsLoading(false);
        }
    }, [bookName, charName]);

    useEffect(() => {
        if (!bookName || !charName) {
            setDetail(null);
            setError(null);
            return;
        }
        void load();
    }, [bookName, charName, load]);

    return { detail, isLoading, error, refetch: load };
}
