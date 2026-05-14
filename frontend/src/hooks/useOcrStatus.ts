import { useState, useCallback } from 'react';
import apiClient from '../config/api_client';
import { API_ENDPOINTS } from '../config/api';
import { usePolling } from './usePolling';
import type { OcrStatusResponse } from '../types';

/**
 * OCR ステータスをポーリングで取得するフック。
 *
 * - 常時ポーリングが必要なため enabled は固定で true
 * - ポーリング間隔は 2000ms（usePolling のデフォルト）
 */
export function useOcrStatus(enabled = true) {
    const [status, setStatus] = useState<OcrStatusResponse['status']>('idle');
    const [logs, setLogs] = useState<string[]>([]);

    const fetchStatus = useCallback(async () => {
        try {
            const data = await apiClient.get<unknown, OcrStatusResponse>(API_ENDPOINTS.OCR_STATUS);
            setStatus(data.status);
            setLogs(data.logs);
        } catch (err) {
            console.error('Failed to fetch OCR status', err);
        }
    }, []);

    const { refetch } = usePolling(fetchStatus, { enabled });

    const startOcr = useCallback(async (targetDir?: string) => {
        return apiClient.post(API_ENDPOINTS.OCR_RUN, { target_dir: targetDir });
    }, []);

    const stopOcr = useCallback(async () => {
        return apiClient.post(API_ENDPOINTS.OCR_STOP);
    }, []);

    return { status, logs, startOcr, stopOcr, refetch };
}
