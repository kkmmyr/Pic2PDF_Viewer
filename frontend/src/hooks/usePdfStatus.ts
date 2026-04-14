import { useState, useCallback } from 'react';
import apiClient from '../config/api_client';
import { API_ENDPOINTS } from '../config/api';
import { usePolling } from './usePolling';
import type { StatusItem, StatusResponse } from '../types';

/**
 * PDF生成ステータスをポーリングで取得するフック。
 *
 * - `enabled` が false のときはポーリングを停止する
 * - ポーリング間隔は 2000ms（usePolling のデフォルト）
 */
export function usePdfStatus(sourceDir: string, enabled: boolean = false) {
    const [statusItems, setStatusItems] = useState<StatusItem[]>([]);

    const fetchStatus = useCallback(async () => {
        if (!sourceDir) return;
        try {
            const data = await apiClient.get<unknown, StatusResponse>(API_ENDPOINTS.STATUS, {
                params: { source_dir: sourceDir },
            });
            setStatusItems(data.items ?? []);
        } catch (e) {
            console.error('Failed to fetch PDF status', e);
        }
    }, [sourceDir]);

    const { refetch } = usePolling(fetchStatus, { enabled });

    return { statusItems, refetch };
}
