import { useCallback, useEffect, useState } from 'react';
import apiClient from '../config/api_client';
import { API_ENDPOINTS } from '../config/api';
import type { ArrivalItem, NewArrivalsResponse, RunNowResponse, RunStats, RunStatus } from '../types/hitomi';

interface UseHitomiArrivalsResult {
    items: ArrivalItem[];
    lastRunAt: string | null;
    lastRunStatus: RunStatus;
    lastError: string | null;
    loading: boolean;
    running: boolean;
    error: string | null;
    refresh: () => Promise<void>;
    dismiss: (id: number) => Promise<void>;
    dismissAll: () => Promise<void>;
    /** 監視スクリプトを同期実行する。完了後は自動で refresh され、stats を返す。 */
    runNow: () => Promise<RunStats | null>;
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
    const [running, setRunning] = useState(false);
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

    const runNow = useCallback(async () => {
        setRunning(true);
        try {
            // 監視は数秒〜数十秒かかる可能性があるためタイムアウトを延長
            const resp = await apiClient.post<unknown, RunNowResponse>(
                API_ENDPOINTS.HITOMI_RUN_NOW,
                undefined,
                { timeout: 120_000 },
            );
            await refresh();
            return resp.last_run_stats;
        } finally {
            setRunning(false);
        }
    }, [refresh]);

    useEffect(() => {
        refresh();
    }, [refresh]);

    return {
        items, lastRunAt, lastRunStatus, lastError,
        loading, running, error,
        refresh, dismiss, dismissAll, runNow,
    };
}
