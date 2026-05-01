import { useCallback } from 'react';
import type { LibrarySource } from '../types';
import { API_ENDPOINTS } from '../config/api';
import { useJobPolling } from './useJobPolling';

export interface AutoFillStatus {
    status: 'idle' | 'running' | 'done' | 'error';
    total: number;
    done: number;
    skipped: number;
    current: string;
    results: Array<{ title: string; author: string }>;
    error: string;
}

const IDLE_STATUS: AutoFillStatus = {
    status: 'idle',
    total: 0,
    done: 0,
    skipped: 0,
    current: '',
    results: [],
    error: '',
};

export function useAutoFillAuthors(source: LibrarySource, onComplete?: () => void) {
    const { jobStatus, startJob } = useJobPolling<AutoFillStatus>({
        source,
        statusUrl: API_ENDPOINTS.META_AUTO_FILL_STATUS,
        startUrl: API_ENDPOINTS.META_AUTO_FILL,
        idleStatus: IDLE_STATUS,
        onComplete,
    });

    const startAutoFill = useCallback(
        (mode: 'missing_only' | 'unknown_only' | 'overwrite_all' = 'unknown_only') =>
            startJob({ mode }),
        [startJob]
    );

    return { jobStatus, startAutoFill };
}
