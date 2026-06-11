import { useCallback, useState } from 'react';
import type { LibrarySource, SuggestedSeries } from '@/types';
import { API_ENDPOINTS } from '@/config/api';
import apiClient from '@/config/api_client';
import { errorMessage } from '@/utils/error';

/**
 * 既存シリーズへの紐付け候補を取得するフック（A-1）。
 *
 * `BulkSeriesAssignDialog` の「AI が提案するシリーズに追加」モードから利用。
 * 書き込み副作用なし。バックエンドの `POST /api/series/suggest` を呼び出す。
 */
export function useSeriesSuggestion(source: LibrarySource, path: string) {
    const [candidates, setCandidates] = useState<SuggestedSeries[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const fetchSuggestions = useCallback(
        async (names: string[]) => {
            if (names.length === 0) {
                setCandidates([]);
                setError(null);
                return;
            }
            setLoading(true);
            setError(null);
            try {
                const response = await apiClient.post<unknown, { candidates: SuggestedSeries[] }>(
                    API_ENDPOINTS.SERIES_SUGGEST,
                    { path, names, source },
                );
                setCandidates(response.candidates ?? []);
            } catch (e: unknown) {
                setCandidates([]);
                setError(errorMessage(e, '提案の取得に失敗しました'));
            } finally {
                setLoading(false);
            }
        },
        [source, path],
    );

    const reset = useCallback(() => {
        setCandidates([]);
        setError(null);
    }, []);

    return { candidates, loading, error, fetchSuggestions, reset };
}
