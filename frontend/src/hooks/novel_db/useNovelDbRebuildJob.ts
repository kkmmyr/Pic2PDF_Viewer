/**
 * 再構築ジョブの enqueue / cancel と状態 polling。
 *
 * - 5 秒間隔で `/rebuild/status` をポーリング
 * - `running → !running` の遷移検知時に `onJobCompleted` を呼ぶ（書籍一覧 refetch 用）
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { cancelRebuild, fetchRebuildStatus, postRebuild } from '../../features/novel_db/api';
import type { RebuildEnqueueRequest } from '../../features/novel_db/api';
import type { RebuildEnqueueResponse, RebuildStatus } from '../../features/novel_db/types';
import { NOVEL_DB_CONFIG } from '../../constants';

export interface UseNovelDbRebuildJob {
    status: RebuildStatus | null;
    isLoading: boolean;
    error: string | null;
    enqueue: (req: RebuildEnqueueRequest) => Promise<RebuildEnqueueResponse>;
    cancel: (jobId: number) => Promise<void>;
    refresh: () => Promise<void>;
}

export function useNovelDbRebuildJob(onJobCompleted?: () => void): UseNovelDbRebuildJob {
    const [status, setStatus] = useState<RebuildStatus | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const lastIsRunningRef = useRef(false);
    const onCompletedRef = useRef(onJobCompleted);

    useEffect(() => {
        onCompletedRef.current = onJobCompleted;
    }, [onJobCompleted]);

    const refresh = useCallback(async () => {
        setIsLoading(true);
        try {
            const s = await fetchRebuildStatus();
            setStatus(s);
            // running → !running の遷移を検知して通知
            if (lastIsRunningRef.current && !s.is_running) {
                onCompletedRef.current?.();
            }
            lastIsRunningRef.current = s.is_running;
            setError(null);
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        } finally {
            setIsLoading(false);
        }
    }, []);

    useEffect(() => {
        void refresh();
        const id = setInterval(() => {
            void refresh();
        }, NOVEL_DB_CONFIG.REBUILD_POLL_INTERVAL_MS);
        return () => clearInterval(id);
    }, [refresh]);

    const enqueue = useCallback(
        async (req: RebuildEnqueueRequest) => {
            const res = await postRebuild(req);
            await refresh();
            return res;
        },
        [refresh],
    );

    const cancel = useCallback(
        async (jobId: number) => {
            await cancelRebuild(jobId);
            await refresh();
        },
        [refresh],
    );

    return { status, isLoading, error, enqueue, cancel, refresh };
}
