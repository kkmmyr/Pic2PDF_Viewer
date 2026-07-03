import { useState, useCallback, useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ApiError } from '@/config/api_client';
import generateApiClient from '@/config/generate_api_client';
import { API_ENDPOINTS } from '@/config/api';
import { STORAGE_KEYS, API_CONFIG } from '@/constants';
import { getStorageJson, setStorageJson, removeStorage } from '@/utils/storage';
import type { GenerateJob } from '@/types';

interface StoredJob {
    job_id: string;
}

const STORAGE_KEY = STORAGE_KEYS.GENERATOR_JOB;

const pendingJob = (job_id: string): GenerateJob => ({
    job_id,
    status: 'pending',
    current_item: null,
    files: [],
    failed_items: [],
    message: '',
    error: null,
});

interface UseGenerateJobReturn {
    currentJob: GenerateJob | null;
    isGenerating: boolean;
    /** 画面遷移からの復元ジョブかどうか */
    isRestoredJob: boolean;
    startJob: (jobId: string) => void;
    clearCurrentJob: () => void;
}

export function useGenerateJob(
    onCompleted: (job: GenerateJob) => void,
    onFailed: (job: GenerateJob) => void,
): UseGenerateJobReturn {
    const stored = loadStoredJob();
    const [currentJobId, setCurrentJobId] = useState<string | null>(stored?.job_id ?? null);

    const onCompletedRef = useRef(onCompleted);
    const onFailedRef = useRef(onFailed);
    useEffect(() => {
        onCompletedRef.current = onCompleted;
    }, [onCompleted]);
    useEffect(() => {
        onFailedRef.current = onFailed;
    }, [onFailed]);

    const { data: fetchedJob, error } = useQuery<GenerateJob>({
        queryKey: ['generateJob', currentJobId],
        queryFn: () =>
            generateApiClient.get<unknown, GenerateJob>(API_ENDPOINTS.GENERATE_JOB(currentJobId!)),
        enabled: currentJobId !== null,
        refetchInterval: (query) => {
            const status = query.state.data?.status;
            if (status === 'completed' || status === 'failed') return false;
            return API_CONFIG.JOB_POLL_INTERVAL_MS;
        },
        staleTime: 0,
        gcTime: 30_000,
        retry: false,
    });

    const currentJob: GenerateJob | null =
        currentJobId === null ? null : (fetchedJob ?? pendingJob(currentJobId));

    const isGenerating =
        currentJob !== null && (currentJob.status === 'pending' || currentJob.status === 'running');
    const isRestoredJob = isGenerating && !!stored;

    // Detect terminal status transitions
    useEffect(() => {
        if (!fetchedJob) return;
        if (fetchedJob.status === 'completed') {
            removeStorage(STORAGE_KEY);
            onCompletedRef.current(fetchedJob);
        } else if (fetchedJob.status === 'failed') {
            removeStorage(STORAGE_KEY);
            onFailedRef.current(fetchedJob);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps -- status 変化時のみ発火させる（ポーリングで fetchedJob が丸ごと更新される他のフィールド変化では再実行しない）。onCompleted/onFailed は ref 経由で最新を参照
    }, [fetchedJob?.status]);

    // Handle 404 (job disappeared, e.g. server restart)
    useEffect(() => {
        if (error instanceof ApiError && error.status === 404) {
            removeStorage(STORAGE_KEY);
            setCurrentJobId(null);
        }
    }, [error]);

    const startJob = useCallback((jobId: string) => {
        setStorageJson<StoredJob>(STORAGE_KEY, { job_id: jobId });
        setCurrentJobId(jobId);
    }, []);

    const clearCurrentJob = useCallback(() => {
        removeStorage(STORAGE_KEY);
        setCurrentJobId(null);
    }, []);

    return {
        currentJob,
        isGenerating,
        isRestoredJob,
        startJob,
        clearCurrentJob,
    };
}

function loadStoredJob(): StoredJob | null {
    return getStorageJson<StoredJob | null>(STORAGE_KEY, null);
}
