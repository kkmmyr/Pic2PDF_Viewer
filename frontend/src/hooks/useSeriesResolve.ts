import { useState, useCallback, useRef, useEffect } from 'react';
import type { LibrarySource } from '../types';
import { API_ENDPOINTS } from '../config/api';
import apiClient from '../config/api_client';
import { API_CONFIG } from '../constants';

export interface SeriesResolveStatus {
    status: 'idle' | 'running' | 'done' | 'error';
    total: number;
    done: number;
    created: number;
    current: string;
    error: string;
}

const IDLE_STATUS: SeriesResolveStatus = {
    status: 'idle',
    total: 0,
    done: 0,
    created: 0,
    current: '',
    error: '',
};

/**
 * シリーズ判定ジョブの実行制御 + 進捗ポーリング。
 * `useAutoFillAuthors` と同じ非同期ジョブパターン。
 */
export function useSeriesResolve(source: LibrarySource, onComplete?: () => void) {
    const [jobStatus, setJobStatus] = useState<SeriesResolveStatus>(IDLE_STATUS);
    const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

    const clearPolling = useCallback(() => {
        if (intervalRef.current) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
        }
    }, []);

    const fetchStatus = useCallback(async () => {
        try {
            const data = await apiClient.get<unknown, SeriesResolveStatus>(
                API_ENDPOINTS.SERIES_RESOLVE_STATUS,
                { params: { source } }
            );
            setJobStatus(data);
            if (data.status !== 'running') {
                clearPolling();
                if (data.status === 'done') onComplete?.();
            }
        } catch {
            clearPolling();
        }
    }, [source, clearPolling, onComplete]);

    // ソース変更時に現在のジョブ状態を取得（別ソースで実行中の場合もある）
    useEffect(() => {
        setJobStatus(IDLE_STATUS);
        clearPolling();
        (async () => {
            try {
                const data = await apiClient.get<unknown, SeriesResolveStatus>(
                    API_ENDPOINTS.SERIES_RESOLVE_STATUS,
                    { params: { source } }
                );
                setJobStatus(data);
                if (data.status === 'running') {
                    intervalRef.current = setInterval(fetchStatus, API_CONFIG.JOB_POLL_INTERVAL_MS);
                }
            } catch {
                // ignore
            }
        })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [source]);

    const startResolve = useCallback(async (useGemma = false) => {
        await apiClient.post(
            API_ENDPOINTS.SERIES_RESOLVE,
            null,
            { params: { source, use_gemma: useGemma } }
        );
        clearPolling();
        intervalRef.current = setInterval(fetchStatus, API_CONFIG.JOB_POLL_INTERVAL_MS);
        fetchStatus();
    }, [source, clearPolling, fetchStatus]);

    useEffect(() => () => clearPolling(), [clearPolling]);

    return { jobStatus, startResolve };
}
