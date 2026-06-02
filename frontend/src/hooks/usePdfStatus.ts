import { useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import generateApiClient from '../config/generate_api_client';
import { API_ENDPOINTS } from '../config/api';
import type { StatusItem, StatusResponse } from '../types';

export function usePdfStatus(enabled: boolean = false) {
    const { data, refetch: queryRefetch } = useQuery<StatusResponse>({
        queryKey: ['pdfStatus'],
        queryFn: () =>
            generateApiClient.get<unknown, StatusResponse>(API_ENDPOINTS.STATUS),
        enabled,
        refetchInterval: 2000,
        staleTime: 0,
        gcTime: 30_000,
        retry: false,
    });

    const statusItems: StatusItem[] = data?.items ?? [];

    const refetch = useCallback(async () => {
        await queryRefetch();
    }, [queryRefetch]);

    return { statusItems, refetch };
}
