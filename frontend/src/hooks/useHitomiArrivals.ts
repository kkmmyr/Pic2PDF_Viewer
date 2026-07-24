import { useState, useCallback, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '@/config/api_client';
import { API_ENDPOINTS } from '@/config/api';
import { errorMessage } from '@/utils/error';
import type {
    ArrivalStatus,
    ArrivalItem,
    NewArrivalsResponse,
    RunNowResponse,
    RunStats,
    RunStatus,
} from '@/types/hitomi';

interface ArrivalsData {
    items: ArrivalItem[];
    total: number;
    unreadCount: number;
    readCount: number;
    offset: number;
    limit: number;
    lastRunAt: string | null;
    lastRunStatus: RunStatus;
    lastError: string | null;
}

const QUERY_ROOT = ['hitomiArrivals'] as const;

interface UseHitomiArrivalsResult {
    items: ArrivalItem[];
    total: number;
    unreadCount: number;
    readCount: number;
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
export function useHitomiArrivals(
    status: ArrivalStatus = 'unread',
    offset = 0,
    limit = 60,
): UseHitomiArrivalsResult {
    const queryClient = useQueryClient();
    const [running, setRunning] = useState(false);
    const queryKey = useMemo(
        () => [...QUERY_ROOT, status, offset, limit] as const,
        [status, offset, limit],
    );

    const query = useQuery({
        queryKey,
        queryFn: async (): Promise<ArrivalsData> => {
            const resp = await apiClient.get<unknown, NewArrivalsResponse>(
                API_ENDPOINTS.HITOMI_ARRIVALS(status, offset, limit),
            );
            return {
                items: resp.items,
                total: resp.total,
                unreadCount: resp.unread_count,
                readCount: resp.read_count,
                offset: resp.offset,
                limit: resp.limit,
                lastRunAt: resp.last_run_at ?? null,
                lastRunStatus: resp.last_run_status,
                lastError: resp.last_error ?? null,
            };
        },
        staleTime: Infinity,
    });

    const dismissMutation = useMutation({
        mutationFn: (id: number) => apiClient.post(API_ENDPOINTS.HITOMI_DISMISS(id)),
        onMutate: (id: number) => {
            const prev = queryClient.getQueryData<ArrivalsData>(queryKey);
            queryClient.setQueryData<ArrivalsData>(queryKey, (old) => {
                if (!old || status !== 'unread') return old;
                return {
                    ...old,
                    items: old.items.filter((it) => it.id !== id),
                    total: Math.max(0, old.total - 1),
                    unreadCount: Math.max(0, old.unreadCount - 1),
                    readCount: old.readCount + 1,
                };
            });
            return { prev };
        },
        onError: (_err, _id, context) => {
            if (context?.prev !== undefined) {
                queryClient.setQueryData(queryKey, context.prev);
            }
        },
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: QUERY_ROOT, refetchType: 'inactive' });
        },
    });

    const dismissAllMutation = useMutation({
        mutationFn: () => apiClient.post(API_ENDPOINTS.HITOMI_DISMISS_ALL),
        onMutate: () => {
            const prev = queryClient.getQueryData<ArrivalsData>(queryKey);
            queryClient.setQueryData<ArrivalsData>(queryKey, (old) => {
                if (!old || status !== 'unread') return old;
                return {
                    ...old,
                    items: [],
                    total: 0,
                    readCount: old.readCount + old.unreadCount,
                    unreadCount: 0,
                };
            });
            return { prev };
        },
        onError: (_err, _vars, context) => {
            if (context?.prev !== undefined) {
                queryClient.setQueryData(queryKey, context.prev);
            }
        },
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: QUERY_ROOT, refetchType: 'inactive' });
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
            // run 系フィールドをキャッシュに直接書き込む。
            // invalidateQueries の refetchType:'active' はコンポーネント非アクティブ時に
            // refetch をスキップするため、戻ってきたときに lastRunAt 等が更新されない。
            // setQueryData で先に書いておけばアンマウント中でも結果が保持される。
            queryClient.setQueryData<ArrivalsData>(queryKey, (old) =>
                old
                    ? {
                          ...old,
                          lastRunAt: resp.last_run_at ?? null,
                          lastRunStatus: resp.last_run_status as RunStatus,
                          lastError: resp.last_error ?? null,
                      }
                    : old,
            );
            await queryClient.invalidateQueries({ queryKey: QUERY_ROOT });
            return resp.last_run_stats ?? null;
        } finally {
            setRunning(false);
        }
    }, [queryClient, queryKey]);

    const data = query.data;

    return {
        items: data?.items ?? [],
        total: data?.total ?? 0,
        unreadCount: data?.unreadCount ?? 0,
        readCount: data?.readCount ?? 0,
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
