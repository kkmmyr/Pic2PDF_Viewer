import { useState, useCallback } from 'react';
import apiClient from '../config/api_client';
import { API_ENDPOINTS } from '../config/api';
import { usePolling } from './usePolling';
import { STORAGE_KEYS, API_CONFIG } from '../constants';
import { getStorageJson, setStorageJson, removeStorage } from '../utils/storage';
import type { GenerateJob } from '../types';

interface StoredJob {
    job_id: string;
    sourceDir: string;
}

const STORAGE_KEY = STORAGE_KEYS.GENERATOR_JOB;

export interface UseGenerateJobReturn {
    currentJob: GenerateJob | null;
    /** 画面遷移前に実行中だったジョブのソースディレクトリ（復元時のみ非null） */
    restoredSourceDir: string | null;
    isGenerating: boolean;
    /** 画面遷移からの復元ジョブかどうか */
    isRestoredJob: boolean;
    startJob: (jobId: string, sourceDir: string) => void;
    clearCurrentJob: () => void;
}

export function useGenerateJob(
    onCompleted: (job: GenerateJob) => void,
    onFailed: (job: GenerateJob) => void,
): UseGenerateJobReturn {
    const stored = loadStoredJob();

    const [currentJob, setCurrentJob] = useState<GenerateJob | null>(
        stored
            ? { job_id: stored.job_id, status: 'pending', current_item: null, files: [], message: '', error: null }
            : null
    );
    const [restoredSourceDir] = useState<string | null>(stored?.sourceDir ?? null);

    const isGenerating = currentJob !== null &&
        (currentJob.status === 'pending' || currentJob.status === 'running');
    const isRestoredJob = isGenerating && !!stored;

    const fetchJob = useCallback(async () => {
        if (!currentJob) return;
        try {
            const job = await apiClient.get<unknown, GenerateJob>(
                API_ENDPOINTS.GENERATE_JOB(currentJob.job_id)
            );
            setCurrentJob(job);
            if (job.status === 'completed') {
                removeStorage(STORAGE_KEY);
                onCompleted(job);
            } else if (job.status === 'failed') {
                removeStorage(STORAGE_KEY);
                onFailed(job);
            }
        } catch (e) {
            console.error('Failed to poll job status', e);
        }
    }, [currentJob, onCompleted, onFailed]);

    usePolling(fetchJob, {
        enabled: isGenerating,
        interval: API_CONFIG.JOB_POLL_INTERVAL_MS,
        immediate: false,
    });

    const startJob = useCallback((jobId: string, sourceDir: string) => {
        setStorageJson<StoredJob>(STORAGE_KEY, { job_id: jobId, sourceDir });
        setCurrentJob({ job_id: jobId, status: 'pending', current_item: null, files: [], message: '', error: null });
    }, []);

    const clearCurrentJob = useCallback(() => {
        removeStorage(STORAGE_KEY);
        setCurrentJob(null);
    }, []);

    return { currentJob, restoredSourceDir, isGenerating, isRestoredJob, startJob, clearCurrentJob };
}

function loadStoredJob(): StoredJob | null {
    return getStorageJson<StoredJob | null>(STORAGE_KEY, null);
}
