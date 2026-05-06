import { useCallback } from 'react';
import type { LibrarySource } from '../types';
import { API_ENDPOINTS } from '../config/api';
import { useJobPolling } from './useJobPolling';

interface SeriesResolveStatus {
    status: 'idle' | 'running' | 'done' | 'error';
    total: number;
    done: number;
    created: number;
    current: string;
    error: string;
}

const IDLE_STATUS: SeriesResolveStatus = {
    status: 'idle',
    total: 0,
    done: 0,
    created: 0,
    current: '',
    error: '',
};

/** シリーズ判定ジョブの実行制御 + 進捗ポーリング */
export function useSeriesResolve(source: LibrarySource, onComplete?: () => void) {
    const { jobStatus, startJob } = useJobPolling<SeriesResolveStatus>({
        source,
        statusUrl: API_ENDPOINTS.SERIES_RESOLVE_STATUS,
        startUrl: API_ENDPOINTS.SERIES_RESOLVE,
        idleStatus: IDLE_STATUS,
        onComplete,
    });

    const startResolve = useCallback(
        (useGemma = false) => startJob({ use_gemma: useGemma }),
        [startJob]
    );

    return { jobStatus, startResolve };
}
