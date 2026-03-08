import { useState, useEffect, useRef } from 'react';
import apiClient from '../config/api_client';
import { API_ENDPOINTS } from '../config/api';

export function useOcrStatus() {
    const [status, setStatus] = useState<string>('idle');
    const [logs, setLogs] = useState<string[]>([]);
    const pollingRef = useRef<number | null>(null);

    const fetchStatus = async () => {
        try {
            const data = await apiClient.get<any, any>(API_ENDPOINTS.OCR_STATUS);
            setStatus(data.status);
            setLogs(data.logs);
        } catch (err) {
            console.error('Failed to fetch OCR status', err);
        }
    };

    useEffect(() => {
        fetchStatus();
        pollingRef.current = window.setInterval(fetchStatus, 1000);
        return () => {
            if (pollingRef.current) clearInterval(pollingRef.current);
        };
    }, []);

    const startOcr = async (targetDir?: string) => {
        return apiClient.post(API_ENDPOINTS.OCR_RUN, { target_dir: targetDir });
    };

    const stopOcr = async () => {
        return apiClient.post(API_ENDPOINTS.OCR_STOP);
    };

    return { status, logs, startOcr, stopOcr, refetch: fetchStatus };
}
