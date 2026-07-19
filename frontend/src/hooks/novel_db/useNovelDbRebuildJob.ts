/**
 * 再構築ジョブの enqueue / cancel と状態 polling。
 *
 * - 5 秒間隔で `/rebuild/status` をポーリング
 * - `running → !running` の遷移検知時に `onJobCompleted` を呼ぶ（書籍一覧 refetch 用）
 */
import { useCallback, useEffect, useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { cancelRebuild, fetchRebuildStatus, postRebuild } from '@/features/novel_db/api';
import { novelDbKeys } from '@/features/novel_db/queries';
import type { RebuildEnqueueRequest } from '@/features/novel_db/api';
import type { RebuildEnqueueResponse, RebuildStatus } from '@/features/novel_db/types';
import { NOVEL_DB_CONFIG } from '@/constants';

export interface UseNovelDbRebuildJob {
    status: RebuildStatus | null;
    isLoading: boolean;
    error: string | null;
    enqueue: (req: RebuildEnqueueRequest) => Promise<RebuildEnqueueResponse>;
    cancel: (jobId: number) => Promise<void>;
    refresh: () => Promise<void>;
}

export function useNovelDbRebuildJob(onJobCompleted?: () => void): UseNovelDbRebuildJob {
    const queryClient = useQueryClient();
    const lastIsRunningRef = useRef(false);
    const onCompletedRef = useRef(onJobCompleted);
    useEffect(() => {
        onCompletedRef.current = onJobCompleted;
    }, [onJobCompleted]);

    const {
        data: status,
        isLoading,
        error: queryError,
    } = useQuery<RebuildStatus>({
        queryKey: novelDbKeys.rebuildStatus(),
        queryFn: fetchRebuildStatus,
        refetchInterval: NOVEL_DB_CONFIG.REBUILD_POLL_INTERVAL_MS,
        staleTime: 0,
        gcTime: 30_000,
        retry: false,
    });

    // Detect running → !running transition
    useEffect(() => {
        if (!status) return;
        if (lastIsRunningRef.current && !status.is_running) {
            onCompletedRef.current?.();
        }
        lastIsRunningRef.current = status.is_running;
    }, [status]);

    const error = queryError instanceof Error ? queryError.message : null;

    const refresh = useCallback(async () => {
        await queryClient.invalidateQueries({ queryKey: novelDbKeys.rebuildStatus() });
    }, [queryClient]);

    const enqueue = useCallback(
        async (req: RebuildEnqueueRequest) => {
            const res = await postRebuild(req);
            await queryClient.invalidateQueries({ queryKey: novelDbKeys.rebuildStatus() });
            return res;
        },
        [queryClient],
    );

    const cancel = useCallback(
        async (jobId: number) => {
            await cancelRebuild(jobId);
            await queryClient.invalidateQueries({ queryKey: novelDbKeys.rebuildStatus() });
        },
        [queryClient],
    );

    return { status: status ?? null, isLoading, error, enqueue, cancel, refresh };
}
