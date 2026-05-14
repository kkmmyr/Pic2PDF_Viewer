import { useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import apiClient from '../config/api_client';
import { API_ENDPOINTS } from '../config/api';
import type { StatusItem, StatusResponse } from '../types';

/**
 * PDF生成ステータスをポーリングで取得するフック。
 *
 * - `enabled` が false のときはポーリングを停止する
 * - ポーリング間隔は 2000ms
 */
export function usePdfStatus(sourceDir: string, enabled: boolean = false) {
    const { data, refetch: queryRefetch } = useQuery<StatusResponse>({
        queryKey: ['pdfStatus', sourceDir],
        queryFn: () =>
            apiClient.get<unknown, StatusResponse>(API_ENDPOINTS.STATUS, {
                params: { source_dir: sourceDir },
            }),
        enabled: enabled && !!sourceDir,
        refetchInterval: 2000,
        staleTime: 0,
        gcTime: 30_000,
        retry: false,
    });

    const statusItems: StatusItem[] = data?.items ?? [];

    const refetch = useCallback(async () => {
        if (!sourceDir) return;
        await queryRefetch();
    }, [sourceDir, queryRefetch]);

    return { statusItems, refetch };
}
