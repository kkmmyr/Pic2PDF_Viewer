/**
 * 4.6 本構築専用管理画面のキュー状態フック。
 * SSE ストリームでキュー状態をリアルタイム受信し、enqueue / cancel を提供する。
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { cancelBuildJob, enqueueBuild } from '../../features/novel_build/api';
import type { BuildQueueStatus } from '../../features/novel_build/types';
import { connectBuildStream } from '../../features/novel_build/sse';

const INITIAL_STATUS: BuildQueueStatus = {
    is_running: false,
    current_job: null,
    queued_jobs: [],
    recent_finished: [],
};

export interface UseNovelBuildQueue {
    status: BuildQueueStatus;
    isEnqueuing: boolean;
    enqueueError: string | null;
    enqueue: (
        bookName: string | null,
        allBooks: boolean,
        mode?: 'full_build' | 'generate_contexts',
    ) => Promise<void>;
    cancel: (jobId: number) => Promise<void>;
}

export function useNovelBuildQueue(): UseNovelBuildQueue {
    const [status, setStatus] = useState<BuildQueueStatus>(INITIAL_STATUS);
    const [isEnqueuing, setIsEnqueuing] = useState(false);
    const [enqueueError, setEnqueueError] = useState<string | null>(null);
    const closeRef = useRef<(() => void) | null>(null);
    const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    useEffect(() => {
        function connect() {
            closeRef.current = connectBuildStream({
                onStatus: setStatus,
                onError: () => {
                    // SSE 切断時は 3 秒後に再接続（unmount 時は clearTimeout で停止）
                    reconnectTimerRef.current = setTimeout(connect, 3000);
                },
            });
        }
        connect();
        return () => {
            if (reconnectTimerRef.current !== null) {
                clearTimeout(reconnectTimerRef.current);
                reconnectTimerRef.current = null;
            }
            closeRef.current?.();
            closeRef.current = null;
        };
    }, []);

    const enqueue = useCallback(
        async (
            bookName: string | null,
            allBooks: boolean,
            mode: 'full_build' | 'generate_contexts' = 'full_build',
        ) => {
            setEnqueueError(null);
            setIsEnqueuing(true);
            try {
                await enqueueBuild(bookName, allBooks, mode);
            } catch (e: unknown) {
                const msg =
                    (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
                    (e instanceof Error ? e.message : '不明なエラー');
                setEnqueueError(msg);
            } finally {
                setIsEnqueuing(false);
            }
        },
        [],
    );

    const cancel = useCallback(async (jobId: number) => {
        try {
            await cancelBuildJob(jobId);
        } catch {
            // キャンセル失敗は無視（次の SSE 更新で状態が反映される）
        }
    }, []);

    return { status, isEnqueuing, enqueueError, enqueue, cancel };
}
