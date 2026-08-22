import { useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
    fetchOcrStatus,
    startOcr as requestOcrStart,
    stopOcr as requestOcrStop,
} from '@/features/ocr/api';
import type { OcrStatusResponse } from '@/features/ocr/types';

/**
 * OCR ステータスをポーリングで取得するフック。
 *
 * - 常時ポーリングが必要なため enabled は固定で true
 * - ポーリング間隔は 2000ms
 */
export function useOcrStatus(enabled = true) {
    const { data, refetch } = useQuery<OcrStatusResponse>({
        queryKey: ['ocrStatus'],
        queryFn: fetchOcrStatus,
        enabled,
        refetchInterval: 2000,
        staleTime: 0,
        gcTime: 30_000,
        retry: false,
    });

    const status = data?.status ?? 'idle';
    const logs = data?.logs ?? [];

    const startOcr = useCallback(async (targetDir?: string) => {
        return requestOcrStart(targetDir);
    }, []);

    const stopOcr = useCallback(async () => {
        return requestOcrStop();
    }, []);

    return { status, logs, startOcr, stopOcr, refetch };
}
