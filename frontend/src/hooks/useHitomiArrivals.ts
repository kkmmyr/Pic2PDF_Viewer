import { useCallback, useEffect, useState } from 'react';
import apiClient from '../config/api_client';
import { API_ENDPOINTS } from '../config/api';
import type { ArrivalItem, NewArrivalsResponse, RunStatus } from '../types/hitomi';

interface UseHitomiArrivalsResult {
    items: ArrivalItem[];
    lastRunAt: string | null;
    lastRunStatus: RunStatus;
    lastError: string | null;
    loading: boolean;
    error: string | null;
    refresh: () => Promise<void>;
    dismiss: (id: number) => Promise<void>;
    dismissAll: () => Promise<void>;
}

/**
 * hitomi.la 新着一覧を取得・操作するフック。
 *
 * - マウント時に 1 回 fetch（ポーリングしない）
 * - dismiss / dismissAll は楽観的更新 + サーバ反映、失敗時はロールバック
 */
export function useHitomiArrivals(): UseHitomiArrivalsResult {
    const [items, setItems] = useState<ArrivalItem[]>([]);
    const [lastRunAt, setLastRunAt] = useState<string | null>(null);
    const [lastRunStatus, setLastRunStatus] = useState<RunStatus>('never');
    const [lastError, setLastError] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const refresh = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const resp = await apiClient.get<unknown, NewArrivalsResponse>(API_ENDPOINTS.HITOMI_NEW_ARRIVALS);
            setItems(resp.items);
            setLastRunAt(resp.last_run_at);
            setLastRunStatus(resp.last_run_status);
            setLastError(resp.last_error);
        } catch (e) {
            setError(e instanceof Error ? e.message : '不明なエラー');
        } finally {
            setLoading(false);
        }
    }, []);

    const dismiss = useCallback(async (id: number) => {
        const prev = items;
        setItems(items.filter(it => it.id !== id));
        try {
            await apiClient.post(API_ENDPOINTS.HITOMI_DISMISS(id));
        } catch (e) {
            setItems(prev);
            throw e;
        }
    }, [items]);

    const dismissAll = useCallback(async () => {
        const prev = items;
        setItems([]);
        try {
            await apiClient.post(API_ENDPOINTS.HITOMI_DISMISS_ALL);
        } catch (e) {
            setItems(prev);
            throw e;
        }
    }, [items]);

    useEffect(() => {
        refresh();
    }, [refresh]);

    return { items, lastRunAt, lastRunStatus, lastError, loading, error, refresh, dismiss, dismissAll };
}
