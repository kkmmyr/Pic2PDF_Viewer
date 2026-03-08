import { useState, useEffect, useCallback, useRef } from 'react';
import apiClient from '../config/api_client';
import { API_ENDPOINTS } from '../config/api';
import { StatusItem, StatusResponse } from '../types';

export function usePdfStatus(sourceDir: string, enabled: boolean = false) {
    const [statusItems, setStatusItems] = useState<StatusItem[]>([]);
    const pollingRef = useRef<number | null>(null);

    const fetchStatus = useCallback(async () => {
        if (!sourceDir) return;
        try {
            const data = await apiClient.get<any, StatusResponse>(API_ENDPOINTS.STATUS, {
                params: { source_dir: sourceDir }
            });
            setStatusItems(data.items || []);
        } catch (e) {
            console.error("Failed to fetch status", e);
        }
    }, [sourceDir]);

    useEffect(() => {
        if (enabled) {
            fetchStatus();
            pollingRef.current = window.setInterval(fetchStatus, 1000);
        } else {
            if (pollingRef.current) clearInterval(pollingRef.current);
        }
        return () => {
            if (pollingRef.current) clearInterval(pollingRef.current);
        };
    }, [enabled, fetchStatus]);

    return { statusItems, refetch: fetchStatus };
}
