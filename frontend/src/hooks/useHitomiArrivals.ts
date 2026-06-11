import { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '@/config/api_client';
import { API_ENDPOINTS } from '@/config/api';
import { errorMessage } from '@/utils/error';
import type {
    ArrivalItem,
    NewArrivalsResponse,
    RunNowResponse,
    RunStats,
    RunStatus,
} from '@/types/hitomi';

interface ArrivalsData {
    items: ArrivalItem[];
    lastRunAt: string | null;
    lastRunStatus: RunStatus;
    lastError: string | null;
}

const QUERY_KEY = ['hitomiArrivals'] as const;

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
    const queryClient = useQueryClient();
    const [running, setRunning] = useState(false);

    const query = useQuery({
        queryKey: QUERY_KEY,
        queryFn: async (): Promise<ArrivalsData> => {
            const resp = await apiClient.get<unknown, NewArrivalsResponse>(
                API_ENDPOINTS.HITOMI_NEW_ARRIVALS,
            );
            return {
                items: resp.items,
                lastRunAt: resp.last_run_at,
                lastRunStatus: resp.last_run_status,
                lastError: resp.last_error,
            };
        },
        staleTime: Infinity,
    });

    const dismissMutation = useMutation({
        mutationFn: (id: number) => apiClient.post(API_ENDPOINTS.HITOMI_DISMISS(id)),
        onMutate: (id: number) => {
            const prev = queryClient.getQueryData<ArrivalsData>(QUERY_KEY);
            queryClient.setQueryData<ArrivalsData>(QUERY_KEY, (old) =>
                old ? { ...old, items: old.items.filter((it) => it.id !== id) } : old,
            );
            return { prev };
        },
        onError: (_err, _id, context) => {
            if (context?.prev !== undefined) {
                queryClient.setQueryData(QUERY_KEY, context.prev);
            }
        },
    });

    const dismissAllMutation = useMutation({
        mutationFn: () => apiClient.post(API_ENDPOINTS.HITOMI_DISMISS_ALL),
        onMutate: () => {
            const prev = queryClient.getQueryData<ArrivalsData>(QUERY_KEY);
            queryClient.setQueryData<ArrivalsData>(QUERY_KEY, (old) =>
                old ? { ...old, items: [] } : old,
            );
            return { prev };
        },
        onError: (_err, _vars, context) => {
            if (context?.prev !== undefined) {
                queryClient.setQueryData(QUERY_KEY, context.prev);
            }
        },
    });

    const dismiss = useCallback(
        async (id: number) => {
            await dismissMutation.mutateAsync(id);
        },
        [dismissMutation],
    );

    const dismissAll = useCallback(async () => {
        await dismissAllMutation.mutateAsync();
    }, [dismissAllMutation]);

    const runNow = useCallback(async (): Promise<RunStats | null> => {
        setRunning(true);
        try {
            const resp = await apiClient.post<unknown, RunNowResponse>(
                API_ENDPOINTS.HITOMI_RUN_NOW,
                undefined,
                { timeout: 120_000 },
            );
            await queryClient.invalidateQueries({ queryKey: QUERY_KEY });
            return resp.last_run_stats;
        } finally {
            setRunning(false);
        }
    }, [queryClient]);

    const data = query.data;

    return {
        items: data?.items ?? [],
        lastRunAt: data?.lastRunAt ?? null,
        lastRunStatus: data?.lastRunStatus ?? 'never',
        lastError: data?.lastError ?? null,
        loading: query.isLoading,
        running,
        error: query.error instanceof Error ? errorMessage(query.error, '不明なエラー') : null,
        refresh: async () => {
            await query.refetch();
        },
        dismiss,
        dismissAll,
        runNow,
    };
}
