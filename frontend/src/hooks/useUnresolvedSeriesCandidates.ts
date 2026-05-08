import { useCallback, useState } from 'react';
import type { LibrarySource } from '../types';
import { API_ENDPOINTS } from '../config/api';
import apiClient from '../config/api_client';

export type UnresolvedReason = 'short_prefix' | 'volume_parse_failed';

export interface UnresolvedSeriesBook {
    path: string;
    name: string;
    title: string;
}

export interface UnresolvedSeriesCandidate {
    reason: UnresolvedReason;
    score: number;
    common_prefix: string;
    books: UnresolvedSeriesBook[];
}

interface UnresolvedSeriesResponse {
    candidates: UnresolvedSeriesCandidate[];
}

/**
 * シリーズ自動判定で漏れた候補を取得する hook（A-6）。
 *
 * `refresh()` を呼ばないと取得しない lazy fetch（ダイアログ open 時のみ起動する想定）。
 * 取得失敗時は `error` に文字列が入り、`candidates` は前回値を保持する。
 */
export function useUnresolvedSeriesCandidates(source: LibrarySource) {
    const [candidates, setCandidates] = useState<UnresolvedSeriesCandidate[] | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const refresh = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await apiClient.get<unknown, UnresolvedSeriesResponse>(
                API_ENDPOINTS.SERIES_UNRESOLVED_CANDIDATES,
                { params: { source } },
            );
            setCandidates(data.candidates);
        } catch (e) {
            setError(e instanceof Error ? e.message : '候補の取得に失敗しました。');
        } finally {
            setLoading(false);
        }
    }, [source]);

    const reset = useCallback(() => {
        setCandidates(null);
        setError(null);
    }, []);

    return { candidates, loading, error, refresh, reset };
}
