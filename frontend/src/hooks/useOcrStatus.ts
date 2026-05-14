import { useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import apiClient from '../config/api_client';
import { API_ENDPOINTS } from '../config/api';
import type { OcrStatusResponse } from '../types';

/**
 * OCR ステータスをポーリングで取得するフック。
 *
 * - 常時ポーリングが必要なため enabled は固定で true
 * - ポーリング間隔は 2000ms
 */
export function useOcrStatus(enabled = true) {
    const { data, refetch } = useQuery<OcrStatusResponse>({
        queryKey: ['ocrStatus'],
        queryFn: () => apiClient.get<unknown, OcrStatusResponse>(API_ENDPOINTS.OCR_STATUS),
        enabled,
        refetchInterval: 2000,
        staleTime: 0,
        gcTime: 30_000,
        retry: false,
    });

    const status = data?.status ?? 'idle';
    const logs = data?.logs ?? [];

    const startOcr = useCallback(async (targetDir?: string) => {
        return apiClient.post(API_ENDPOINTS.OCR_RUN, { target_dir: targetDir });
    }, []);

    const stopOcr = useCallback(async () => {
        return apiClient.post(API_ENDPOINTS.OCR_STOP);
    }, []);

    return { status, logs, startOcr, stopOcr, refetch };
}
