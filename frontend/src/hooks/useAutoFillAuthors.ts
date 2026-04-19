import { useState, useCallback, useRef, useEffect } from 'react';
import type { LibrarySource } from '../types';
import { API_ENDPOINTS } from '../config/api';
import apiClient from '../config/api_client';

export interface AutoFillStatus {
    status: 'idle' | 'running' | 'done' | 'error';
    total: number;
    done: number;
    skipped: number;
    current: string;
    results: Array<{ title: string; author: string }>;
    error: string;
}

const IDLE_STATUS: AutoFillStatus = {
    status: 'idle',
    total: 0,
    done: 0,
    skipped: 0,
    current: '',
    results: [],
    error: '',
};

export function useAutoFillAuthors(source: LibrarySource, onComplete?: () => void) {
    const [jobStatus, setJobStatus] = useState<AutoFillStatus>(IDLE_STATUS);
    const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

    const clearPolling = useCallback(() => {
        if (intervalRef.current) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
        }
    }, []);

    const fetchStatus = useCallback(async () => {
        try {
            const data = await apiClient.get<unknown, AutoFillStatus>(
                API_ENDPOINTS.META_AUTO_FILL_STATUS,
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

    // ソース変更時に現在のジョブ状態を取得（別ソースのジョブが動いている場合もある）
    useEffect(() => {
        setJobStatus(IDLE_STATUS);
        clearPolling();
        (async () => {
            try {
                const data = await apiClient.get<unknown, AutoFillStatus>(
                    API_ENDPOINTS.META_AUTO_FILL_STATUS,
                    { params: { source } }
                );
                setJobStatus(data);
                // 既に実行中なら即ポーリング開始
                if (data.status === 'running') {
                    intervalRef.current = setInterval(fetchStatus, 1500);
                }
            } catch {
                // ignore
            }
        })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [source]);

    const startAutoFill = useCallback(async (overwrite = false) => {
        try {
            await apiClient.post(API_ENDPOINTS.META_AUTO_FILL, null, { params: { source, overwrite } });
            clearPolling();
            intervalRef.current = setInterval(fetchStatus, 1500);
            fetchStatus();
        } catch (e: unknown) {
            alert(e instanceof Error ? e.message : '自動登録の開始に失敗しました。Ollama と SearXNG が起動しているか確認してください。');
        }
    }, [source, clearPolling, fetchStatus]);

    useEffect(() => () => clearPolling(), [clearPolling]);

    return { jobStatus, startAutoFill };
}
