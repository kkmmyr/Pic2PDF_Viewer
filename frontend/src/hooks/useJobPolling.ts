import { useState, useCallback, useRef, useEffect } from 'react';
import type { LibrarySource } from '../types';
import apiClient from '../config/api_client';
import { API_CONFIG } from '../constants';

interface UseJobPollingOptions<TStatus> {
    source: LibrarySource;
    statusUrl: string;
    startUrl: string;
    idleStatus: TStatus;
    onComplete?: () => void;
}

/** source 単位で非同期ジョブを起動し進捗をポーリングする汎用フック */
export function useJobPolling<TStatus extends { status: string }>({
    source,
    statusUrl,
    startUrl,
    idleStatus,
    onComplete,
}: UseJobPollingOptions<TStatus>) {
    const [jobStatus, setJobStatus] = useState<TStatus>(idleStatus);
    const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

    const clearPolling = useCallback(() => {
        if (intervalRef.current) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
        }
    }, []);

    const fetchStatus = useCallback(async () => {
        try {
            const data = await apiClient.get<unknown, TStatus>(statusUrl, { params: { source } });
            setJobStatus(data);
            if (data.status !== 'running') {
                clearPolling();
                if (data.status === 'done') onComplete?.();
            }
        } catch {
            clearPolling();
        }
    }, [source, statusUrl, clearPolling, onComplete]);

    // ソース変更時に現在のジョブ状態を取得（別ソースで実行中の場合もある）
    useEffect(() => {
        setJobStatus(idleStatus);
        clearPolling();
        (async () => {
            try {
                const data = await apiClient.get<unknown, TStatus>(statusUrl, {
                    params: { source },
                });
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

    const startJob = useCallback(
        async (extraParams?: Record<string, unknown>) => {
            await apiClient.post(startUrl, null, { params: { source, ...extraParams } });
            clearPolling();
            intervalRef.current = setInterval(fetchStatus, API_CONFIG.JOB_POLL_INTERVAL_MS);
            fetchStatus();
        },
        [source, startUrl, clearPolling, fetchStatus],
    );

    useEffect(() => () => clearPolling(), [clearPolling]);

    return { jobStatus, startJob };
}
